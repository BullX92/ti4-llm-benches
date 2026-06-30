from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from evals.llm_bench import server as llm_bench_server
from evals.llm_bench.server import (
    BENCHMARK_ASSERTIONS,
    BENCHMARK_PROMPT,
    BENCHMARK_QUESTION,
    build_keyed_json_prompt,
    build_promptfoo_config,
    classify_result_detail,
    classify_result_kind,
    classify_result_label,
    compute_case_execution_trace,
    extract_model_names,
    get_latest_run_payload,
    init_db,
    list_testcases,
    load_last_run,
    load_results_manifest,
    load_testcase_result_payload,
    load_yaml_testcase_specs,
    normalize_assertions,
    normalize_base_url,
    normalize_models_url,
    plan_benchmark_matrix,
    publish_testcase_result_artifacts,
    record_case_result,
    save_last_run,
    save_selected_models,
    upsert_testcase,
    upsert_provider,
)


def test_normalize_base_url_adds_scheme_and_v1() -> None:
    assert normalize_base_url("ollama.internal:11434") == "http://ollama.internal:11434/v1"


def test_normalize_models_url_reuses_v1_base() -> None:
    assert normalize_models_url("https://bench.example.com/v1") == "https://bench.example.com/models"


def test_extract_model_names_supports_openai_and_ollama_shapes() -> None:
    payload = {
        "data": [{"id": "llama3.2"}, {"id": "qwen2.5"}],
        "models": [{"name": "gemma2"}, "phi4"],
    }

    assert extract_model_names(payload) == ["gemma2", "llama3.2", "phi4", "qwen2.5"]


def test_build_promptfoo_config_uses_openai_compatible_provider_ids_for_ollama_configs() -> None:
    testcases = [
        {
            "id": 7,
            "name": "Sol flagship",
            "prompt_text": BENCHMARK_PROMPT,
            "assertions": BENCHMARK_ASSERTIONS,
            "content_hash": "case-hash-1",
        }
    ]
    config_text = build_promptfoo_config(
        [
            {
                "provider_type": "ollama",
                "provider_name": "Remote Ollama",
                "base_url": "https://ollama.example.com",
                "api_key": "secret-key",
                "model_name": "llama3.2",
            },
            {
                "provider_type": "ollama",
                "provider_name": "Remote Ollama",
                "base_url": "https://ollama.example.com",
                "api_key": "secret-key",
                "model_name": "qwen2.5",
            },
        ],
        testcases,
    )

    payload = json.loads(config_text)

    assert payload["prompts"] == ["{{prompt}}"]
    assert [provider["id"] for provider in payload["providers"]] == [
        "openai:chat:llama3.2",
        "openai:chat:qwen2.5",
    ]
    assert payload["providers"][0]["config"]["apiBaseUrl"] == "https://ollama.example.com/v1"
    assert payload["providers"][0]["config"]["apiKey"] == "secret-key"
    assert payload["tests"][0]["vars"] == {"prompt": BENCHMARK_PROMPT}
    assert payload["tests"][0]["metadata"] == {"testcase_id": 7, "testcase_name": "Sol flagship", "content_hash": "case-hash-1"}
    assert all(assertion["type"] == "javascript" for assertion in payload["tests"][0]["assert"])
    assert payload["tests"][0]["assert"][0]["config"] == {"path": "name", "matcher": "equals", "expected": "Genesis"}
    assert "parseStructuredOutput" in payload["tests"][0]["assert"][0]["value"]
    assert "Output was not valid JSON object text." in payload["tests"][0]["assert"][0]["value"]


def test_classify_result_kind_treats_assertion_runtime_json_errors_as_failures() -> None:
    result = {
        "response": {"output": "Thinking: I am going to reason first"},
        "error": "Custom function threw error: Unexpected token 'T', \"Thinking:\" is not valid JSON",
        "success": False,
    }

    assert classify_result_kind(result) == "fail"
    assert classify_result_label("fail", result["error"], result["response"]["output"]) == "Invalid JSON output"
    assert "clean JSON object" in classify_result_detail("fail", result["error"], result["response"]["output"])


def test_classify_result_kind_keeps_provider_blocks_as_errors() -> None:
    result = {
        "response": {"output": ""},
        "error": "API error: 403 Forbidden {\"error\":\"this model requires a subscription\"}",
        "success": False,
    }

    assert classify_result_kind(result) == "error"
    assert classify_result_label("error", result["error"], result["response"]["output"]) == "Subscription required"


def test_classify_result_label_distinguishes_missing_keys_vs_wrong_answers() -> None:
    missing_keys_error = "Custom function returned false Missing key path: flagship.name"
    assert classify_result_label("fail", missing_keys_error, '{"flagship": {}}') == "Missing required JSON keys"
    assert classify_result_label("fail", "", '{"name":"Not Genesis"}') == "Wrong answer"


def test_normalize_assertions_supports_keyed_matchers() -> None:
    assertions = normalize_assertions(
        [
            {"key": "unit.name", "type": "equals", "value": "Genesis"},
            {"key": "unit.ability", "type": "contains", "value": "infantry"},
            {"type": "contains", "value": "fallback plain text"},
        ]
    )

    assert assertions == [
        {"key": "unit.name", "type": "equals", "value": "Genesis"},
        {"key": "unit.ability", "type": "contains", "value": "infantry"},
        {"type": "contains", "value": "fallback plain text"},
    ]


def test_build_keyed_json_prompt_lists_required_keys() -> None:
    prompt = build_keyed_json_prompt(BENCHMARK_QUESTION, BENCHMARK_ASSERTIONS)

    assert "Answer ONLY with a JSON object" in prompt
    assert "- name" in prompt
    assert "- sustain_damage" in prompt
    assert "- ability" in prompt
    assert prompt.count("- ability") == 1


def test_load_yaml_testcase_specs_generates_keyed_sol_prompt(tmp_path: Path) -> None:
    original_dir = llm_bench_server.TESTCASES_DIR
    original_file = llm_bench_server.DEFAULT_TESTCASE_FILE
    try:
        llm_bench_server.TESTCASES_DIR = tmp_path / "testcases"
        llm_bench_server.DEFAULT_TESTCASE_FILE = llm_bench_server.TESTCASES_DIR / "sol-flagship.yaml"
        specs = load_yaml_testcase_specs()
        assert len(specs) == 1
        spec = specs[0]
        assert spec["name"] == llm_bench_server.DEFAULT_TESTCASE_NAME
        assert spec["assertions"] == BENCHMARK_ASSERTIONS
        assert "- name" in spec["prompt_text"]
        assert "- cost" in spec["prompt_text"]
        assert "JSON object" in spec["prompt_text"]
    finally:
        llm_bench_server.TESTCASES_DIR = original_dir
        llm_bench_server.DEFAULT_TESTCASE_FILE = original_file


def test_list_testcases_includes_yaml_source_path(tmp_path: Path) -> None:
    original_db_path = llm_bench_server.DB_PATH
    original_dir = llm_bench_server.TESTCASES_DIR
    original_file = llm_bench_server.DEFAULT_TESTCASE_FILE
    try:
        llm_bench_server.DB_PATH = tmp_path / "llm_bench.sqlite3"
        llm_bench_server.TESTCASES_DIR = tmp_path / "testcases"
        llm_bench_server.DEFAULT_TESTCASE_FILE = llm_bench_server.TESTCASES_DIR / "sol-flagship.yaml"
        init_db()
        seeded = list_testcases()
        assert len(seeded) == 1
        assert seeded[0]["source_path"].endswith("sol-flagship.yaml")
        assert seeded[0]["source_description"]
        assert seeded[0]["source_yaml"]
    finally:
        llm_bench_server.DB_PATH = original_db_path
        llm_bench_server.TESTCASES_DIR = original_dir
        llm_bench_server.DEFAULT_TESTCASE_FILE = original_file


def test_build_promptfoo_config_compiles_keyed_assertions_to_javascript() -> None:
    testcases = [
        {
            "id": 8,
            "name": "JSON flagship facts",
            "prompt_text": "Return a JSON object with flagship facts.",
            "assertions": [
                {"key": "name", "type": "equals", "value": "Genesis"},
                {"key": "ability", "type": "contains", "value": "infantry"},
            ],
            "content_hash": "case-hash-json",
        }
    ]
    config_text = build_promptfoo_config(
        [
            {
                "provider_type": "ollama",
                "provider_name": "Remote Ollama",
                "base_url": "https://ollama.example.com",
                "api_key": "secret-key",
                "model_name": "llama3.2",
            }
        ],
        testcases,
    )

    payload = json.loads(config_text)
    assertions = payload["tests"][0]["assert"]

    assert assertions[0]["type"] == "javascript"
    assert assertions[0]["config"] == {"path": "name", "matcher": "equals", "expected": "Genesis"}
    assert "context.config.path" in assertions[0]["value"]
    assert "parseStructuredOutput" in assertions[0]["value"]
    assert assertions[1]["type"] == "javascript"
    assert assertions[1]["config"] == {"path": "ability", "matcher": "contains", "expected": "infantry"}


def test_upsert_testcase_rejects_duplicate_content_under_new_name(tmp_path: Path) -> None:
    original_db_path = llm_bench_server.DB_PATH
    original_dir = llm_bench_server.TESTCASES_DIR
    original_file = llm_bench_server.DEFAULT_TESTCASE_FILE
    llm_bench_server.DB_PATH = tmp_path / "llm_bench.sqlite3"
    try:
        llm_bench_server.TESTCASES_DIR = tmp_path / "testcases"
        llm_bench_server.DEFAULT_TESTCASE_FILE = llm_bench_server.TESTCASES_DIR / "sol-flagship.yaml"
        init_db()
        seeded = list_testcases()
        assert len(seeded) == 1
        assert seeded[0]["name"] == llm_bench_server.DEFAULT_TESTCASE_NAME

        try:
            upsert_testcase(
                name="Duplicate content",
                prompt_text=BENCHMARK_PROMPT,
                assertions=BENCHMARK_ASSERTIONS,
            )
        except ValueError as exc:
            assert "already exists" in str(exc)
        else:
            raise AssertionError("upsert_testcase should reject duplicate testcase content")
    finally:
        llm_bench_server.DB_PATH = original_db_path
        llm_bench_server.TESTCASES_DIR = original_dir
        llm_bench_server.DEFAULT_TESTCASE_FILE = original_file


def test_plan_benchmark_matrix_skips_cached_case_results(tmp_path: Path) -> None:
    original_db_path = llm_bench_server.DB_PATH
    try:
        llm_bench_server.DB_PATH = tmp_path / "llm_bench.sqlite3"
        init_db()
        provider = upsert_provider("Remote Ollama", "https://ollama.example.com", "secret", provider_type="ollama")
        save_selected_models(provider["id"], ["llama3.2"])
        testcase_a = upsert_testcase(
            name="Case A",
            prompt_text="Prompt A",
            assertions=[{"type": "contains", "value": "Alpha"}],
        )
        testcase_b = upsert_testcase(
            name="Case B",
            prompt_text="Prompt B",
            assertions=[{"type": "contains", "value": "Beta"}],
        )

        selected = llm_bench_server.list_selected_models()
        trace = compute_case_execution_trace(testcase_a, selected[0])
        record_case_result(
            testcase=testcase_a,
            selected_model=selected[0],
            execution_trace=trace,
            result={
                "provider": {"label": "Remote Ollama / llama3.2", "id": "openai:chat:llama3.2"},
                "prompt": {"raw": "Prompt A"},
                "response": {"output": "Alpha"},
                "success": True,
                "score": 1,
                "latencyMs": 12,
                "testCase": {"metadata": {"testcase_id": testcase_a["id"]}},
            },
            run_id=None,
        )

        plan = plan_benchmark_matrix(selected_models=selected, testcases=[testcase_a, testcase_b])
        assert len(plan["cached_results"]) == 1
        assert plan["cached_results"][0]["testcase_id"] == testcase_a["id"]
        assert len(plan["pending_by_model"]) == 1
        assert plan["pending_by_model"][0]["selected_model"]["model_name"] == "llama3.2"
        assert [item["id"] for item in plan["pending_by_model"][0]["testcases"]] == [testcase_b["id"]]
    finally:
        llm_bench_server.DB_PATH = original_db_path


def test_record_case_result_is_available_from_latest_run_payload(tmp_path: Path) -> None:
    original_db_path = llm_bench_server.DB_PATH
    try:
        llm_bench_server.DB_PATH = tmp_path / "llm_bench.sqlite3"
        init_db()
        provider = upsert_provider("Remote Ollama", "https://ollama.example.com", "secret", provider_type="ollama")
        save_selected_models(provider["id"], ["llama3.2"])
        testcase = upsert_testcase(
            name="Case A",
            prompt_text="Prompt A",
            assertions=[{"type": "contains", "value": "Alpha"}],
        )
        selected = llm_bench_server.list_selected_models()
        record_case_result(
            testcase=testcase,
            selected_model=selected[0],
            execution_trace=compute_case_execution_trace(testcase, selected[0]),
            result={
                "provider": {"label": "Remote Ollama / llama3.2", "id": "openai:chat:llama3.2"},
                "prompt": {"raw": "Prompt A"},
                "response": {"output": "Alpha"},
                "success": True,
                "score": 1,
                "latencyMs": 12,
                "testCase": {"metadata": {"testcase_id": testcase["id"]}},
            },
            run_id=None,
        )

        latest = get_latest_run_payload(selected_models=selected, testcases=[testcase])
        assert latest is not None
        assert latest["matrix_results"][0]["testcase_name"] == "Case A"
        assert latest["matrix_results"][0]["model_name"] == "llama3.2"
        assert latest["matrix_results"][0]["success"] is True
    finally:
        llm_bench_server.DB_PATH = original_db_path


def test_save_selected_models_rejects_unknown_provider(tmp_path: Path) -> None:
    original_db_path = llm_bench_server.DB_PATH
    llm_bench_server.DB_PATH = tmp_path / "llm_bench.sqlite3"
    try:
        init_db()
        provider = upsert_provider("Remote Ollama", "http://127.0.0.1:11434", "", provider_type="ollama")
        assert provider["provider_type"] == "ollama"

        try:
            save_selected_models(999, ["llama3.2"])
        except ValueError as exc:
            assert "does not exist" in str(exc)
        else:
            raise AssertionError("save_selected_models should reject unknown providers")

        with sqlite3.connect(llm_bench_server.DB_PATH) as conn:
            count = conn.execute("SELECT COUNT(*) FROM selected_models").fetchone()[0]
        assert count == 0
    finally:
        llm_bench_server.DB_PATH = original_db_path


def test_init_db_cleans_orphaned_selected_models(tmp_path: Path) -> None:
    original_db_path = llm_bench_server.DB_PATH
    llm_bench_server.DB_PATH = tmp_path / "llm_bench.sqlite3"
    try:
        init_db()
        with sqlite3.connect(llm_bench_server.DB_PATH) as conn:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("INSERT INTO selected_models (provider_id, model_name) VALUES (?, ?)", (999, "orphan-model"))
            conn.commit()

        init_db()

        with sqlite3.connect(llm_bench_server.DB_PATH) as conn:
            count = conn.execute("SELECT COUNT(*) FROM selected_models").fetchone()[0]
        assert count == 0
    finally:
        llm_bench_server.DB_PATH = original_db_path


def test_save_last_run_round_trips_payload(tmp_path: Path) -> None:
    original_last_run_path = llm_bench_server.LAST_RUN_PATH
    llm_bench_server.LAST_RUN_PATH = tmp_path / "runs" / "last_run.json"
    try:
        payload = {
            "exit_code": 0,
            "saved_at": "2026-06-04T12:00:00Z",
            "selected_models": [{"provider_name": "Ollama Cloud", "model_name": "gemma4:31b"}],
        }
        save_last_run(payload)
        assert load_last_run() == payload
    finally:
        llm_bench_server.LAST_RUN_PATH = original_last_run_path
