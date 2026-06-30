#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import time
from contextlib import contextmanager
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
SITE = REPO_ROOT / "visualize" / "site"
TESTCASES_DIR = REPO_ROOT / "testcases"
RESULTS_DIR = Path(os.environ.get("LLM_BENCH_RESULTS_DIR", str(REPO_ROOT / "testresults" / "testcase_results"))).expanduser()
DB_PATH = Path(os.environ.get("LLM_BENCH_DB_PATH", str(REPO_ROOT / "testresults" / "llm_bench.sqlite3"))).expanduser()
RUNS_DIR = Path(os.environ.get("LLM_BENCH_RUNS_DIR", str(REPO_ROOT / "testresults" / "runs"))).expanduser()
LAST_RUN_PATH = Path(os.environ.get("LLM_BENCH_LAST_RUN_PATH", str(RUNS_DIR / "last_run.json"))).expanduser()
PROMPTFOO_CMD = ["npx", "-y", "promptfoo@latest", "eval", "--config"]
PORT = int(os.environ.get("PORT", "8642"))
VIEW_PORT = int(os.environ.get("PROMPTFOO_VIEW_PORT", "9119"))
PROMPTFOO_VIEW_CMD = ["npx", "-y", "promptfoo@latest", "view", "--port", str(VIEW_PORT), "--no"]
VIEW_PREFIX = "/promptfoo"
VIEWER_ROOT_PATHS = {"/favicon.png", "/manifest.json", "/robots.txt"}
LOCAL_API_PATHS = {"/api/status", "/api/run", "/api/providers", "/api/testcases", "/api/results/manifest"}
DEFAULT_PROVIDER_TYPE = "ollama"
RESULTS_SCHEMA_VERSION = 1
EVALUATOR_TRACE_VERSION = "2026-06-04-json-contract-v2"
BIND_HOST = os.environ.get("BIND_HOST", "127.0.0.1")
DEFAULT_TESTCASE_NAME = "Sol flagship reference"
DEFAULT_TESTCASE_FILE = TESTCASES_DIR / "sol-flagship.yaml"

BENCHMARK_QUESTION = (
    "What is the name of the Federation of Sol flagship in Twilight Imperium 4, "
    "and what are its stats and ability?"
)
BENCHMARK_ASSERTIONS = [
    {"key": "name", "type": "equals", "value": "Genesis"},
    {"key": "cost", "type": "equals", "value": "8"},
    {"key": "combat", "type": "equals", "value": "5"},
    {"key": "move", "type": "equals", "value": "1"},
    {"key": "capacity", "type": "equals", "value": "12"},
    {"key": "sustain_damage", "type": "equals", "value": "yes"},
    {"key": "ability", "type": "contains", "value": "place 1 infantry"},
    {"key": "ability", "type": "contains", "value": "status phase"},
    {"key": "ability", "type": "contains", "value": "space area"},
]
BENCHMARK_EXPECTED = [item["value"] for item in BENCHMARK_ASSERTIONS]


def _json_canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or "testcase"


def _normalized_sensitive_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key or "").lower())


def sanitize_public_payload(value: object) -> object:
    if isinstance(value, dict):
        cleaned: dict[object, object] = {}
        for key, item in value.items():
            if _normalized_sensitive_key(str(key)) in {"apikey", "authorization"}:
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = sanitize_public_payload(item)
        return cleaned
    if isinstance(value, list):
        return [sanitize_public_payload(item) for item in value]
    return value


def selected_model_public_dict(selected_model: dict) -> dict:
    return {
        "provider_id": selected_model.get("provider_id"),
        "provider_name": selected_model.get("provider_name"),
        "provider_type": selected_model.get("provider_type"),
        "base_url": normalize_base_url(str(selected_model.get("base_url") or "")) if selected_model.get("base_url") else "",
        "model_name": selected_model.get("model_name"),
    }


def testcase_expected_result(assertions: list[dict]) -> dict:
    expected: dict[str, object] = {}
    for assertion in assertions:
        key = str(assertion.get("key") or "").strip()
        matcher = str(assertion.get("type") or "contains").strip().lower()
        value = str(assertion.get("value") or "").strip()
        if not key or not value:
            continue
        if key == "ability":
            expected.setdefault("ability_must_contain", [])
            if matcher in {"contains", "icontains"}:
                ability_values = expected["ability_must_contain"]
                if isinstance(ability_values, list) and value not in ability_values:
                    ability_values.append(value)
            continue
        if matcher == "equals":
            expected[key] = value
    return expected


def build_keyed_json_prompt(question: str, assertions: list[dict]) -> str:
    keyed_assertions = [item for item in assertions if str(item.get("key", "")).strip()]
    keys = list(dict.fromkeys(str(item["key"]).strip() for item in keyed_assertions))
    if not keys:
        return str(question).strip()
    key_lines = "\n".join(f"- {key}" for key in keys)
    return (
        f"{str(question).strip()}\n\n"
        "Answer ONLY with a JSON object. Do not include markdown, explanations, or code fences.\n"
        "Use exactly these keys and no others:\n"
        f"{key_lines}\n"
        "Return each value as a string using the correct TI4 fact for that key."
    )


BENCHMARK_PROMPT = build_keyed_json_prompt(BENCHMARK_QUESTION, BENCHMARK_ASSERTIONS)


def normalize_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("base_url is required")
    if "://" not in value:
        value = f"http://{value}"
    if value.endswith("/v1"):
        return value
    return f"{value}/v1"


def normalize_models_url(base_url: str) -> str:
    api_base = normalize_base_url(base_url)
    return api_base[:-3] + "/models" if api_base.endswith("/v1") else f"{api_base}/models"


def extract_model_names(payload: object) -> list[str]:
    names: set[str] = set()
    if not isinstance(payload, dict):
        return []

    def add_from_entry(entry: object) -> None:
        if isinstance(entry, dict):
            model_id = entry.get("id") or entry.get("name")
            if model_id:
                names.add(str(model_id))
        elif isinstance(entry, str):
            names.add(entry)

    data = payload.get("data")
    if isinstance(data, list):
        for entry in data:
            add_from_entry(entry)

    models = payload.get("models")
    if isinstance(models, list):
        for entry in models:
            add_from_entry(entry)

    return sorted(names)


def json_response(handler: SimpleHTTPRequestHandler, status: int, payload: dict) -> None:
    data = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def load_last_run() -> dict | None:
    try:
        if not LAST_RUN_PATH.exists():
            return None
        payload = json.loads(LAST_RUN_PATH.read_text(encoding="utf-8"))
        return sanitize_public_payload(payload) if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_last_run(payload: dict) -> None:
    LAST_RUN_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_RUN_PATH.write_text(json.dumps(sanitize_public_payload(payload), indent=2, ensure_ascii=False), encoding="utf-8")


@contextmanager
def db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()


def mask_secret(value: str | None) -> str:
    secret = (value or "").strip()
    if not secret:
        return ""
    if len(secret) <= 4:
        return "*" * len(secret)
    return f"{secret[:2]}{'*' * (len(secret) - 4)}{secret[-2:]}"


ALLOWED_ASSERTION_TYPES = {"equals", "contains", "icontains", "regex"}


def normalize_assertions(assertions: object) -> list[dict]:
    if not isinstance(assertions, list) or not assertions:
        raise ValueError("assertions must be a non-empty list")

    cleaned: list[dict] = []
    for item in assertions:
        if not isinstance(item, dict):
            raise ValueError("each assertion must be an object")
        assertion_type = str(item.get("type", "")).strip().lower() or "contains"
        if assertion_type not in ALLOWED_ASSERTION_TYPES:
            raise ValueError(f"unsupported assertion type: {assertion_type}")
        value = str(item.get("value", "")).strip()
        if not value:
            raise ValueError("assertion value is required")
        assertion: dict[str, str] = {"type": assertion_type, "value": value}
        key = str(item.get("key", "")).strip()
        if key:
            assertion["key"] = key
        cleaned.append(assertion)
    return cleaned


def build_promptfoo_assertion(assertion: dict) -> dict:
    assertion_type = str(assertion.get("type", "contains")).strip().lower() or "contains"
    value = str(assertion.get("value", "")).strip()
    key = str(assertion.get("key", "")).strip()
    if not key:
        return {"type": assertion_type, "value": value}

    js_value = r"""
function parseStructuredOutput(raw) {
  if (raw && typeof raw === 'object') {
    return { ok: true, value: raw };
  }
  const text = String(raw ?? '').trim();
  if (!text) {
    return { ok: false, reason: 'Empty output; expected a JSON object.' };
  }
  const candidates = [];
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fenced && fenced[1]) {
    candidates.push(fenced[1].trim());
  }
  candidates.push(text);
  const firstBrace = text.indexOf('{');
  const lastBrace = text.lastIndexOf('}');
  if (firstBrace != -1 && lastBrace > firstBrace) {
    candidates.push(text.slice(firstBrace, lastBrace + 1));
  }
  for (const candidate of candidates) {
    try {
      const parsed = JSON.parse(candidate);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return { ok: true, value: parsed };
      }
    } catch {}
  }
  return { ok: false, reason: 'Output was not valid JSON object text.' };
}
const parsed = parseStructuredOutput(output);
if (!parsed.ok) {
  return { pass: false, score: 0, reason: parsed.reason };
}
const source = parsed.value;
const path = String(context.config.path || '').split('.').filter(Boolean);
let current = source;
for (const segment of path) {
  if (current == null || !(segment in current)) {
    return { pass: false, score: 0, reason: `Missing key path: ${context.config.path}` };
  }
  current = current[segment];
}
const actual = current == null ? '' : String(current);
const expected = String(context.config.expected ?? '');
switch (context.config.matcher) {
  case 'equals':
    return actual === expected;
  case 'contains':
    return actual.includes(expected);
  case 'icontains':
    return actual.toLowerCase().includes(expected.toLowerCase());
  case 'regex':
    return new RegExp(expected).test(actual);
  default:
    throw new Error(`Unsupported matcher: ${context.config.matcher}`);
}
""".strip()
    return {
        "type": "javascript",
        "value": js_value,
        "config": {
            "path": key,
            "matcher": assertion_type,
            "expected": value,
        },
    }


def testcase_content_hash(prompt_text: str, assertions: object) -> str:
    prompt_value = str(prompt_text or "").strip()
    if not prompt_value:
        raise ValueError("prompt_text is required")
    payload = {
        "prompt_text": prompt_value,
        "assertions": normalize_assertions(assertions),
    }
    return _sha256_text(_json_canonical(payload))


def testcase_row_to_dict(
    row: sqlite3.Row,
    source_path: str | None = None,
    source_question: str | None = None,
    source_description: str | None = None,
    source_yaml: str | None = None,
) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "prompt_text": row["prompt_text"],
        "assertions": json.loads(row["assertions_json"]),
        "content_hash": row["content_hash"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "source_path": source_path,
        "source_question": source_question,
        "source_description": source_description,
        "source_yaml": source_yaml,
    }


def ensure_default_testcase_file() -> None:
    TESTCASES_DIR.mkdir(parents=True, exist_ok=True)
    if DEFAULT_TESTCASE_FILE.exists():
        return
    DEFAULT_TESTCASE_FILE.write_text(
        yaml.safe_dump(
            {
                "name": DEFAULT_TESTCASE_NAME,
                "description": (
                    "Baseline flagship testcase for a classic base-game faction. "
                    "The model should return the Sol flagship identity, core stats, "
                    "and infantry-placement ability as strict keyed JSON."
                ),
                "question": BENCHMARK_QUESTION,
                "assertions": BENCHMARK_ASSERTIONS,
            },
            sort_keys=False,
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


def testcase_payload_from_spec(spec: object, source_path: Path) -> dict:
    if not isinstance(spec, dict):
        raise ValueError(f"{source_path.name}: testcase spec must be a mapping")
    name = str(spec.get("name", "")).strip()
    if not name:
        raise ValueError(f"{source_path.name}: name is required")
    assertions = normalize_assertions(spec.get("assertions", []))
    question = str(spec.get("question", "")).strip()
    description = str(spec.get("description", "")).strip()
    prompt_text = str(spec.get("prompt_text", "")).strip()
    if not prompt_text:
        if not question:
            raise ValueError(f"{source_path.name}: question or prompt_text is required")
        prompt_text = build_keyed_json_prompt(question, assertions)
    return {
        "name": name,
        "prompt_text": prompt_text,
        "assertions": assertions,
        "question": question,
        "description": description,
        "source_path": str(source_path),
        "source_yaml": source_path.read_text(encoding="utf-8"),
    }


def load_yaml_testcase_specs() -> list[dict]:
    ensure_default_testcase_file()
    specs: list[dict] = []
    for path in sorted(TESTCASES_DIR.glob("*.y*ml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        specs.append(testcase_payload_from_spec(payload, path))
    return specs


def yaml_testcase_source_map() -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for spec in load_yaml_testcase_specs():
        mapping[testcase_content_hash(spec["prompt_text"], spec["assertions"])] = {
            "source_path": spec["source_path"],
            "source_question": spec.get("question") or None,
            "source_description": spec.get("description") or None,
            "source_yaml": spec.get("source_yaml") or None,
        }
    return mapping


def sync_yaml_testcases_to_db() -> None:
    for spec in load_yaml_testcase_specs():
        upsert_testcase(name=spec["name"], prompt_text=spec["prompt_text"], assertions=spec["assertions"])


def provider_row_to_dict(row: sqlite3.Row) -> dict:
    normalized_base = normalize_base_url(row["base_url"])
    return {
        "id": row["id"],
        "name": row["name"],
        "provider_type": row["provider_type"],
        "base_url": row["base_url"],
        "api_base_url": normalized_base,
        "models_url": normalize_models_url(row["base_url"]),
        "api_key_masked": mask_secret(row["api_key"]),
        "promptfoo_provider_id": _provider_id_for_promptfoo(row["provider_type"], "<model>"),
        "selected_models": [],
    }


def init_db() -> None:
    with db_conn() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                provider_type TEXT NOT NULL DEFAULT 'ollama',
                base_url TEXT NOT NULL,
                api_key TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS selected_models (
                provider_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (provider_id, model_name),
                FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS testcases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                prompt_text TEXT NOT NULL,
                assertions_json TEXT NOT NULL,
                content_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS benchmark_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS benchmark_case_results (
                execution_trace TEXT PRIMARY KEY,
                run_id INTEGER,
                testcase_id INTEGER NOT NULL,
                testcase_name TEXT NOT NULL,
                prompt_text TEXT NOT NULL,
                assertions_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                provider_id INTEGER,
                provider_name TEXT NOT NULL,
                provider_type TEXT NOT NULL,
                base_url TEXT NOT NULL,
                model_name TEXT NOT NULL,
                provider_trace TEXT NOT NULL,
                success INTEGER,
                score REAL,
                result_kind TEXT NOT NULL,
                response_output TEXT NOT NULL DEFAULT '',
                error_text TEXT NOT NULL DEFAULT '',
                latency_ms INTEGER,
                token_usage_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES benchmark_runs(id) ON DELETE SET NULL,
                FOREIGN KEY (testcase_id) REFERENCES testcases(id) ON DELETE CASCADE,
                FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE SET NULL
            );
            """
        )
        conn.execute(
            "UPDATE providers SET provider_type = COALESCE(NULLIF(provider_type, ''), ?) WHERE provider_type IS NULL OR provider_type = ''",
            (DEFAULT_PROVIDER_TYPE,),
        )
        conn.execute("DELETE FROM selected_models WHERE provider_id NOT IN (SELECT id FROM providers)")
        conn.execute("DELETE FROM benchmark_case_results WHERE provider_id IS NOT NULL AND provider_id NOT IN (SELECT id FROM providers)")
        conn.commit()
    ensure_default_testcase_exists()


def ensure_default_testcase_exists() -> None:
    sync_yaml_testcases_to_db()


def list_providers() -> list[dict]:
    with db_conn() as conn:
        providers = conn.execute(
            "SELECT id, name, provider_type, base_url, api_key FROM providers ORDER BY datetime(updated_at) DESC, id DESC"
        ).fetchall()
        selections = conn.execute(
            "SELECT provider_id, model_name FROM selected_models ORDER BY provider_id, model_name"
        ).fetchall()

    selected_map: dict[int, list[str]] = {}
    for row in selections:
        selected_map.setdefault(row["provider_id"], []).append(row["model_name"])

    data = []
    for row in providers:
        item = provider_row_to_dict(row)
        item["selected_models"] = selected_map.get(row["id"], [])
        item["selected_count"] = len(item["selected_models"])
        data.append(item)
    return data


def upsert_provider(name: str, base_url: str, api_key: str, provider_type: str = DEFAULT_PROVIDER_TYPE) -> dict:
    normalized = normalize_base_url(base_url)
    normalized_provider_type = (provider_type or DEFAULT_PROVIDER_TYPE).strip().lower()
    provider_name = name.strip()
    if not provider_name:
        raise ValueError("name is required")
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO providers (name, provider_type, base_url, api_key, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
              provider_type = excluded.provider_type,
              base_url = excluded.base_url,
              api_key = excluded.api_key,
              updated_at = CURRENT_TIMESTAMP
            """,
            (provider_name, normalized_provider_type, normalized, api_key or ""),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, provider_type, base_url, api_key FROM providers WHERE name = ?",
            (provider_name,),
        ).fetchone()
    if row is None:
        raise RuntimeError("provider row missing after upsert")
    return provider_row_to_dict(row)


def delete_provider(provider_id: int) -> None:
    with db_conn() as conn:
        conn.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
        conn.commit()


def save_selected_models(provider_id: int, model_names: list[str]) -> list[str]:
    cleaned = sorted({name.strip() for name in model_names if name and name.strip()})
    with db_conn() as conn:
        provider_exists = conn.execute("SELECT 1 FROM providers WHERE id = ?", (provider_id,)).fetchone()
        if provider_exists is None:
            raise ValueError(f"provider {provider_id} does not exist")
        conn.execute("DELETE FROM selected_models WHERE provider_id = ?", (provider_id,))
        conn.executemany(
            "INSERT INTO selected_models (provider_id, model_name) VALUES (?, ?)",
            [(provider_id, model_name) for model_name in cleaned],
        )
        conn.commit()
    return cleaned


def list_selected_models() -> list[dict]:
    with db_conn() as conn:
        rows = conn.execute(
            """
            SELECT p.id AS provider_id, p.name AS provider_name, p.provider_type, p.base_url, p.api_key, s.model_name
            FROM selected_models s
            JOIN providers p ON p.id = s.provider_id
            ORDER BY p.id, s.model_name
            """
        ).fetchall()
    return [
        {
            "provider_id": row["provider_id"],
            "provider_name": row["provider_name"],
            "provider_type": row["provider_type"],
            "base_url": row["base_url"],
            "api_key": row["api_key"],
            "model_name": row["model_name"],
        }
        for row in rows
    ]


def list_available_models(providers: list[dict] | None = None) -> list[dict]:
    if providers is None:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT id, name, provider_type, base_url, api_key FROM providers ORDER BY datetime(updated_at) DESC, id DESC"
            ).fetchall()
        provider_rows = [dict(row) for row in rows]
    else:
        provider_rows = providers
    available: list[dict] = []
    seen: set[tuple[int | None, str]] = set()
    for provider in provider_rows:
        model_names = remote_model_names(str(provider.get("base_url") or ""), str(provider.get("api_key") or ""))
        for model_name in model_names:
            normalized_model = str(model_name or "").strip()
            if not normalized_model:
                continue
            dedupe_key = (provider.get("id"), normalized_model)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            available.append(
                {
                    "provider_id": provider.get("id"),
                    "provider_name": str(provider.get("name") or ""),
                    "provider_type": str(provider.get("provider_type") or DEFAULT_PROVIDER_TYPE),
                    "base_url": str(provider.get("base_url") or ""),
                    "api_key": str(provider.get("api_key") or ""),
                    "model_name": normalized_model,
                }
            )
    available.sort(key=lambda item: (str(item.get("provider_name") or "").lower(), str(item.get("model_name") or "").lower()))
    return available


def list_testcases() -> list[dict]:
    sync_yaml_testcases_to_db()
    source_map = yaml_testcase_source_map()
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, prompt_text, assertions_json, content_hash, created_at, updated_at FROM testcases ORDER BY datetime(updated_at) DESC, id DESC"
        ).fetchall()
    items = []
    for row in rows:
        metadata = source_map.get(row["content_hash"], {})
        items.append(
            testcase_row_to_dict(
                row,
                source_path=metadata.get("source_path"),
                source_question=metadata.get("source_question"),
                source_description=metadata.get("source_description"),
                source_yaml=metadata.get("source_yaml"),
            )
        )
    return items


def upsert_testcase(name: str, prompt_text: str, assertions: object, testcase_id: int | None = None) -> dict:
    testcase_name = str(name or "").strip()
    prompt_value = str(prompt_text or "").strip()
    if not testcase_name:
        raise ValueError("name is required")
    if not prompt_value:
        raise ValueError("prompt_text is required")
    cleaned_assertions = normalize_assertions(assertions)
    content_hash = testcase_content_hash(prompt_value, cleaned_assertions)
    assertions_json = json.dumps(cleaned_assertions, ensure_ascii=False)

    with db_conn() as conn:
        existing = None
        if testcase_id is not None:
            existing = conn.execute(
                "SELECT id, name, prompt_text, assertions_json, content_hash, created_at, updated_at FROM testcases WHERE id = ?",
                (testcase_id,),
            ).fetchone()
        if existing is None:
            existing = conn.execute(
                "SELECT id, name, prompt_text, assertions_json, content_hash, created_at, updated_at FROM testcases WHERE name = ?",
                (testcase_name,),
            ).fetchone()

        if existing is not None and existing["prompt_text"] == prompt_value and existing["assertions_json"] == assertions_json:
            return testcase_row_to_dict(existing)

        existing_id = existing["id"] if existing is not None else testcase_id
        duplicate = conn.execute(
            "SELECT id, name FROM testcases WHERE content_hash = ? AND (? IS NULL OR id != ?)",
            (content_hash, existing_id, existing_id),
        ).fetchone()
        if duplicate is not None:
            raise ValueError(f"testcase content already exists as {duplicate['name']}")

        if testcase_id is None:
            conn.execute(
                """
                INSERT INTO testcases (name, prompt_text, assertions_json, content_hash, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                  prompt_text = excluded.prompt_text,
                  assertions_json = excluded.assertions_json,
                  content_hash = excluded.content_hash,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (testcase_name, prompt_value, assertions_json, content_hash),
            )
            row = conn.execute(
                "SELECT id, name, prompt_text, assertions_json, content_hash, created_at, updated_at FROM testcases WHERE name = ?",
                (testcase_name,),
            ).fetchone()
        else:
            conn.execute(
                """
                UPDATE testcases
                SET name = ?, prompt_text = ?, assertions_json = ?, content_hash = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (testcase_name, prompt_value, assertions_json, content_hash, testcase_id),
            )
            row = conn.execute(
                "SELECT id, name, prompt_text, assertions_json, content_hash, created_at, updated_at FROM testcases WHERE id = ?",
                (testcase_id,),
            ).fetchone()
        conn.commit()
    if row is None:
        raise ValueError("testcase not found")
    return testcase_row_to_dict(row)


def delete_testcase(testcase_id: int) -> None:
    with db_conn() as conn:
        conn.execute("DELETE FROM testcases WHERE id = ?", (testcase_id,))
        conn.commit()
    ensure_default_testcase_exists()


def compute_selected_model_trace(selected_model: dict) -> str:
    payload = {
        "provider_type": str(selected_model.get("provider_type") or DEFAULT_PROVIDER_TYPE).strip().lower(),
        "base_url": normalize_base_url(str(selected_model.get("base_url") or "")),
        "api_key": str(selected_model.get("api_key") or ""),
        "model_name": str(selected_model.get("model_name") or "").strip(),
    }
    return _sha256_text(_json_canonical(payload))


def compute_case_execution_trace(testcase: dict, selected_model: dict) -> str:
    testcase_hash = str(testcase.get("content_hash") or testcase_content_hash(testcase.get("prompt_text", ""), testcase.get("assertions", [])))
    payload = {
        "evaluator": EVALUATOR_TRACE_VERSION,
        "testcase": testcase_hash,
        "provider": compute_selected_model_trace(selected_model),
    }
    return _sha256_text(_json_canonical(payload))


def _provider_id_for_promptfoo(provider_type: str, model_name: str) -> str:
    normalized = (provider_type or DEFAULT_PROVIDER_TYPE).strip().lower()
    if normalized in {"ollama", "openai"}:
        return f"openai:chat:{model_name}"
    return f"openai:chat:{model_name}"


def build_promptfoo_config(selected_models: list[dict], testcases: list[dict]) -> str:
    if not selected_models:
        raise ValueError("At least one selected model is required")
    if not testcases:
        raise ValueError("At least one testcase is required")

    providers = []
    for item in selected_models:
        provider_type = str(item.get("provider_type") or DEFAULT_PROVIDER_TYPE)
        providers.append(
            {
                "id": _provider_id_for_promptfoo(provider_type, str(item["model_name"])),
                "label": f"{item['provider_name']} / {item['model_name']}",
                "config": {
                    "apiBaseUrl": normalize_base_url(str(item["base_url"])),
                    "apiKey": item.get("api_key", ""),
                    "temperature": 0,
                },
            }
        )

    tests = []
    for testcase in testcases:
        tests.append(
            {
                "vars": {"prompt": testcase["prompt_text"]},
                "assert": [build_promptfoo_assertion(assertion) for assertion in normalize_assertions(testcase["assertions"])],
                "metadata": {
                    "testcase_id": testcase["id"],
                    "testcase_name": testcase["name"],
                    "content_hash": testcase["content_hash"],
                },
            }
        )

    config = {
        "description": "TI4 benchmark matrix",
        "prompts": ["{{prompt}}"],
        "providers": providers,
        "tests": tests,
    }
    return json.dumps(config, indent=2, ensure_ascii=False)


def remote_model_names(base_url: str, api_key: str) -> list[str]:
    candidates = [normalize_models_url(base_url)]
    normalized = normalize_base_url(base_url)
    candidates.append(normalized[:-3] + "/api/tags")

    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    last_error: Exception | None = None
    for url in candidates:
        req = Request(url, headers=headers, method="GET")
        try:
            with urlopen(req, timeout=20) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            names = extract_model_names(payload)
            if names:
                return names
        except HTTPError as e:
            last_error = e
            if e.code in {401, 403}:
                raise RuntimeError(f"Authentication failed for {url}: {e.code} {e.reason}") from e
        except (URLError, TimeoutError, json.JSONDecodeError) as e:
            last_error = e

    raise RuntimeError(f"Could not load models from provider: {last_error}")


def classify_result_kind(result: dict) -> str:
    error_text = str(result.get("error") or ((result.get("response") or {}).get("error")) or "")
    lower_error = error_text.lower()
    if error_text and not any(
        marker in lower_error
        for marker in (
            "custom function returned false",
            "custom function threw error",
            "missing key path:",
            "not valid json",
            "json.parse",
            "unexpected token",
            "empty output; expected a json object",
            "output was not valid json object text",
        )
    ):
        return "error"
    if bool(result.get("success")):
        return "pass"
    return "fail"


def try_extract_json_object(response_output: str) -> dict | None:
    text = str(response_output or "").strip()
    if not text:
        return None
    candidates: list[str] = []
    fence_start = text.find("```")
    if fence_start != -1:
        fence_end = text.find("```", fence_start + 3)
        if fence_end != -1:
            fenced = text[fence_start + 3 : fence_end].strip()
            if fenced.lower().startswith("json"):
                fenced = fenced[4:].strip()
            if fenced:
                candidates.append(fenced)
    candidates.append(text)
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidates.append(text[first_brace : last_brace + 1])
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def detect_failure_mode(error_text: str, response_output: str) -> str:
    lower_error = str(error_text or "").lower()
    parsed_output = try_extract_json_object(response_output)
    if "429" in lower_error or "rate limit" in lower_error:
        return "rate_limited"
    if "403 forbidden" in lower_error or "requires a subscription" in lower_error:
        return "subscription_required"
    if "500" in lower_error or "internal server error" in lower_error:
        return "provider_internal_error"
    if "missing key path:" in lower_error:
        return "missing_keys"
    if parsed_output is None:
        return "invalid_json"
    return "wrong_answer"


def classify_result_subtype(result_kind: str, error_text: str, response_output: str) -> str:
    if result_kind == "pass":
        return "pass"
    return detect_failure_mode(error_text, response_output)


def classify_result_label(result_kind: str, error_text: str, response_output: str) -> str:
    failure_mode = classify_result_subtype(result_kind, error_text, response_output)
    if failure_mode == "pass":
        return "Pass"
    if failure_mode == "subscription_required":
        return "Subscription required"
    if failure_mode == "rate_limited":
        return "Rate limited"
    if failure_mode == "provider_internal_error":
        return "Provider internal error"
    if failure_mode == "invalid_json":
        return "Invalid JSON output"
    if failure_mode == "missing_keys":
        return "Missing required JSON keys"
    return "Wrong answer" if result_kind == "fail" else "Provider error"


def classify_result_detail(result_kind: str, error_text: str, response_output: str) -> str:
    failure_mode = classify_result_subtype(result_kind, error_text, response_output)
    if failure_mode == "subscription_required":
        return "This model is listed by Ollama Cloud, but the current account tier cannot access it."
    if failure_mode == "rate_limited":
        return "The provider rejected the request due to rate limiting; stop or retry later."
    if failure_mode == "provider_internal_error":
        return "The provider returned an internal server error for this testcase/model run."
    if failure_mode == "pass":
        return "Promptfoo marked this model as passing the testcase."
    if failure_mode == "invalid_json":
        return "The model did not return a clean JSON object, so the testcase could not validate the expected keys and values."
    if failure_mode == "missing_keys":
        return "The model returned JSON, but one or more required keys were missing from the response object."
    if result_kind == "error":
        return error_text or "Promptfoo reported a provider-side error for this testcase."
    return "The model returned parseable output, but one or more expected facts or values did not match the testcase assertions."


def result_row_to_payload(row: sqlite3.Row) -> dict:
    result = sanitize_public_payload(json.loads(row["result_json"]))
    response_output = row["response_output"] or ""
    error_text = row["error_text"] or ""
    result_kind = classify_result_kind(result)
    return {
        "execution_trace": row["execution_trace"],
        "testcase_id": row["testcase_id"],
        "testcase_name": row["testcase_name"],
        "prompt_text": row["prompt_text"],
        "assertions": json.loads(row["assertions_json"]),
        "content_hash": row["content_hash"],
        "provider_id": row["provider_id"],
        "provider_name": row["provider_name"],
        "provider_type": row["provider_type"],
        "base_url": row["base_url"],
        "model_name": row["model_name"],
        "provider_trace": row["provider_trace"],
        "success": None if row["success"] is None else bool(row["success"]),
        "score": row["score"],
        "result_kind": result_kind,
        "result_subtype": classify_result_subtype(result_kind, error_text, response_output),
        "label": classify_result_label(result_kind, error_text, response_output),
        "detail": classify_result_detail(result_kind, error_text, response_output),
        "response_output": response_output,
        "error_text": error_text,
        "latency_ms": row["latency_ms"],
        "token_usage": json.loads(row["token_usage_json"]),
        "result": result,
        "saved_at": row["updated_at"],
    }


def get_cached_case_results(execution_traces: list[str]) -> dict[str, dict]:
    if not execution_traces:
        return {}
    placeholders = ", ".join("?" for _ in execution_traces)
    with db_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM benchmark_case_results WHERE execution_trace IN ({placeholders})",
            execution_traces,
        ).fetchall()
    return {row["execution_trace"]: result_row_to_payload(row) for row in rows}


def is_valid_cached_result(result: dict | None) -> bool:
    if not isinstance(result, dict):
        return False
    return str(result.get("result_kind") or "").strip().lower() in {"pass", "fail"}


def plan_benchmark_matrix(selected_models: list[dict], testcases: list[dict]) -> dict:
    traces = [compute_case_execution_trace(testcase, selected_model) for selected_model in selected_models for testcase in testcases]
    cached_map = get_cached_case_results(traces)

    cached_results: list[dict] = []
    pending_by_model: list[dict] = []
    for selected_model in selected_models:
        pending_cases: list[dict] = []
        for testcase in testcases:
            execution_trace = compute_case_execution_trace(testcase, selected_model)
            cached = cached_map.get(execution_trace)
            if cached is not None and is_valid_cached_result(cached):
                cached_results.append(cached)
            else:
                pending_cases.append(testcase)
        if pending_cases:
            pending_by_model.append({"selected_model": selected_model, "testcases": pending_cases})

    cached_results.sort(key=lambda item: (item["testcase_name"].lower(), item["model_name"].lower()))
    return {
        "cached_results": cached_results,
        "pending_by_model": pending_by_model,
        "cached_count": len(cached_results),
        "pending_count": sum(len(item["testcases"]) for item in pending_by_model),
    }


def record_case_result(testcase: dict, selected_model: dict, execution_trace: str, result: dict, run_id: int | None = None) -> dict:
    provider_trace = compute_selected_model_trace(selected_model)
    result_kind = classify_result_kind(result)
    response = result.get("response") or {}
    response_output = str(response.get("output") or result.get("output") or "")
    error_text = str(result.get("error") or response.get("error") or "")
    token_usage = result.get("tokenUsage") or {}
    success = result.get("success")
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO benchmark_case_results (
                execution_trace, run_id, testcase_id, testcase_name, prompt_text, assertions_json, content_hash,
                provider_id, provider_name, provider_type, base_url, model_name, provider_trace,
                success, score, result_kind, response_output, error_text, latency_ms, token_usage_json,
                result_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(execution_trace) DO UPDATE SET
                run_id = excluded.run_id,
                testcase_name = excluded.testcase_name,
                prompt_text = excluded.prompt_text,
                assertions_json = excluded.assertions_json,
                content_hash = excluded.content_hash,
                provider_id = excluded.provider_id,
                provider_name = excluded.provider_name,
                provider_type = excluded.provider_type,
                base_url = excluded.base_url,
                model_name = excluded.model_name,
                provider_trace = excluded.provider_trace,
                success = excluded.success,
                score = excluded.score,
                result_kind = excluded.result_kind,
                response_output = excluded.response_output,
                error_text = excluded.error_text,
                latency_ms = excluded.latency_ms,
                token_usage_json = excluded.token_usage_json,
                result_json = excluded.result_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                execution_trace,
                run_id,
                testcase["id"],
                testcase["name"],
                testcase["prompt_text"],
                json.dumps(normalize_assertions(testcase["assertions"]), ensure_ascii=False),
                testcase["content_hash"],
                selected_model.get("provider_id"),
                selected_model["provider_name"],
                str(selected_model.get("provider_type") or DEFAULT_PROVIDER_TYPE),
                normalize_base_url(str(selected_model["base_url"])),
                selected_model["model_name"],
                provider_trace,
                None if success is None else int(bool(success)),
                result.get("score"),
                result_kind,
                response_output,
                error_text,
                result.get("latencyMs"),
                json.dumps(token_usage, ensure_ascii=False),
                json.dumps(result, ensure_ascii=False),
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM benchmark_case_results WHERE execution_trace = ?",
            (execution_trace,),
        ).fetchone()
    if row is None:
        raise RuntimeError("case result row missing after insert")
    return result_row_to_payload(row)


def save_benchmark_run_payload(payload: dict) -> int:
    with db_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO benchmark_runs (payload_json) VALUES (?)",
            (json.dumps(payload, ensure_ascii=False),),
        )
        conn.commit()
        return int(cursor.lastrowid)


def build_latest_run_payload(
    *,
    selected_models: list[dict],
    testcases: list[dict],
    matrix_results: list[dict],
    stdout_chunks: list[str],
    stderr_chunks: list[str],
    exit_code: int,
    skipped_count: int,
    fresh_count: int,
    run_state: str,
) -> dict:
    pass_count = sum(1 for item in matrix_results if item["result_kind"] == "pass")
    fail_count = sum(1 for item in matrix_results if item["result_kind"] == "fail")
    error_count = sum(1 for item in matrix_results if item["result_kind"] == "error")
    total_latency_ms = sum(int(item.get("latency_ms") or 0) for item in matrix_results)

    return {
        "exit_code": exit_code,
        "stdout": "\n\n".join(chunk for chunk in stdout_chunks if chunk),
        "stderr": "\n\n".join(chunk for chunk in stderr_chunks if chunk),
        "selected_models": [selected_model_public_dict(item) for item in selected_models],
        "testcases": [
            {
                "id": testcase["id"],
                "name": testcase["name"],
                "prompt_text": testcase["prompt_text"],
                "assertions": testcase["assertions"],
                "content_hash": testcase["content_hash"],
            }
            for testcase in testcases
        ],
        "matrix_results": sanitize_public_payload(sorted(matrix_results, key=lambda item: (item["testcase_name"].lower(), item["model_name"].lower()))),
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "report_summary": {
            "selected_model_count": len(selected_models),
            "testcase_count": len(testcases),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "error_count": error_count,
            "fresh_count": fresh_count,
            "skipped_count": skipped_count,
            "duration": f"{max(total_latency_ms // 1000, 0)}s",
        },
        "run_state": run_state,
    }


def get_latest_run_payload(selected_models: list[dict] | None = None, testcases: list[dict] | None = None) -> dict | None:
    if selected_models is not None and testcases is not None:
        plan = plan_benchmark_matrix(selected_models=selected_models, testcases=testcases)
        if plan["cached_results"]:
            return build_latest_run_payload(
                selected_models=selected_models,
                testcases=testcases,
                matrix_results=plan["cached_results"],
                stdout_chunks=[f"Served {len(plan['cached_results'])} cached testcase/model results from SQLite."],
                stderr_chunks=[],
                exit_code=0,
                skipped_count=len(plan["cached_results"]),
                fresh_count=0,
                run_state="cached",
            )

    with db_conn() as conn:
        row = conn.execute("SELECT payload_json FROM benchmark_runs ORDER BY id DESC LIMIT 1").fetchone()
    if row is not None:
        try:
            payload = json.loads(row["payload_json"])
            if isinstance(payload, dict):
                return sanitize_public_payload(payload)
        except json.JSONDecodeError:
            pass

    return load_last_run()


def build_testcase_manifest_entry(aggregate: dict) -> dict:
    summary = aggregate.get("summary") or {}
    testcase = aggregate.get("testcase") or {}
    return {
        "name": testcase.get("name"),
        "slug": testcase.get("slug"),
        "content_hash": testcase.get("content_hash"),
        "file": aggregate.get("file_name"),
        "model_count": summary.get("model_count", 0),
        "pass_count": summary.get("pass_count", 0),
        "fail_count": summary.get("fail_count", 0),
        "error_count": summary.get("error_count", 0),
        "last_updated": summary.get("last_updated"),
    }


def build_testcase_aggregate_payload(testcase: dict, model_results: list[dict]) -> dict:
    ordered_results = sorted(model_results, key=lambda item: str(item.get("model_name") or "").lower())
    pass_count = sum(1 for item in ordered_results if item.get("result_kind") == "pass")
    fail_count = sum(1 for item in ordered_results if item.get("result_kind") == "fail")
    error_count = sum(1 for item in ordered_results if item.get("result_kind") == "error")
    last_updated = max((str(item.get("saved_at") or "") for item in ordered_results), default="")
    aggregate = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "testcase": {
            "id": testcase.get("id"),
            "name": testcase.get("name"),
            "slug": slugify(str(testcase.get("name") or "")),
            "content_hash": testcase.get("content_hash"),
            "source_path": testcase.get("source_path"),
            "question": testcase.get("source_question") or testcase.get("prompt_text"),
            "description": testcase.get("source_description") or "",
            "prompt_text": testcase.get("prompt_text"),
            "assertions": sanitize_public_payload(testcase.get("assertions") or []),
            "expected_result": testcase_expected_result(testcase.get("assertions") or []),
            "created_at": testcase.get("created_at"),
            "updated_at": testcase.get("updated_at"),
        },
        "summary": {
            "model_count": len(ordered_results),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "error_count": error_count,
            "last_updated": last_updated,
        },
        "models": sanitize_public_payload(ordered_results),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    file_name = f"{aggregate['testcase']['slug']}__{aggregate['testcase']['content_hash'][:12]}.json"
    aggregate["file_name"] = file_name
    return aggregate


def publish_testcase_result_artifacts(testcases: list[dict], matrix_results: list[dict]) -> dict:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    results_by_hash: dict[str, list[dict]] = {}
    for result in matrix_results:
        results_by_hash.setdefault(str(result.get("content_hash") or ""), []).append(result)

    aggregates: list[dict] = []
    keep_files = {"manifest.json"}
    for testcase in testcases:
        content_hash = str(testcase.get("content_hash") or "")
        aggregate = build_testcase_aggregate_payload(testcase, results_by_hash.get(content_hash, []))
        aggregates.append(aggregate)
        file_name = str(aggregate["file_name"])
        keep_files.add(file_name)
        (RESULTS_DIR / file_name).write_text(json.dumps(sanitize_public_payload(aggregate), indent=2, ensure_ascii=False), encoding="utf-8")

    manifest = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "testcases": sorted((build_testcase_manifest_entry(item) for item in aggregates), key=lambda item: str(item.get("name") or "").lower()),
    }
    (RESULTS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    for child in RESULTS_DIR.glob("*.json"):
        if child.name not in keep_files:
            child.unlink()
    return manifest


def load_results_manifest() -> dict:
    manifest_path = RESULTS_DIR / "manifest.json"
    if not manifest_path.exists():
        return {"schema_version": RESULTS_SCHEMA_VERSION, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "testcases": []}
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return sanitize_public_payload(payload) if isinstance(payload, dict) else {"schema_version": RESULTS_SCHEMA_VERSION, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "testcases": []}


def load_testcase_result_payload(identifier: str) -> dict | None:
    manifest = load_results_manifest()
    for item in manifest.get("testcases", []):
        if identifier in {str(item.get("content_hash") or ""), str(item.get("slug") or ""), str(item.get("file") or "")}:
            file_name = str(item.get("file") or "")
            if not file_name:
                return None
            target = RESULTS_DIR / file_name
            if not target.exists():
                return None
            payload = json.loads(target.read_text(encoding="utf-8"))
            return sanitize_public_payload(payload) if isinstance(payload, dict) else None
    return None


def run_promptfoo_for_model(selected_model: dict, testcases: list[dict]) -> dict:
    temp_config: str | None = None
    temp_output: str | None = None
    try:
        config_text = build_promptfoo_config([selected_model], testcases)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tmp:
            tmp.write(config_text)
            temp_config = tmp.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as out_file:
            temp_output = out_file.name
        cmd = PROMPTFOO_CMD + [temp_config, "--output", temp_output, "--no-table"]
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=900,
        )
        eval_payload = None
        if temp_output and Path(temp_output).exists():
            eval_payload = json.loads(Path(temp_output).read_text(encoding="utf-8"))
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "command": cmd,
            "eval_payload": eval_payload,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return {
            "exit_code": 124,
            "stdout": stdout,
            "stderr": stderr + "\nTimed out after 900s",
            "command": PROMPTFOO_CMD,
            "eval_payload": None,
        }
    finally:
        if temp_config:
            Path(temp_config).unlink(missing_ok=True)
        if temp_output:
            Path(temp_output).unlink(missing_ok=True)


def extract_promptfoo_case_results(eval_payload: dict, testcase_lookup: dict[int, dict], selected_model: dict, run_id: int | None = None) -> list[dict]:
    payload_results = (((eval_payload or {}).get("results") or {}).get("results") or [])
    saved: list[dict] = []
    for item in payload_results:
        metadata = (((item.get("testCase") or {}).get("metadata") or {}))
        testcase_id = metadata.get("testcase_id")
        testcase_key: int | None = int(testcase_id) if isinstance(testcase_id, int) or (isinstance(testcase_id, str) and testcase_id.isdigit()) else None
        testcase = testcase_lookup.get(testcase_key) if testcase_key is not None else None
        if testcase is None:
            continue
        execution_trace = compute_case_execution_trace(testcase, selected_model)
        saved.append(record_case_result(testcase, selected_model, execution_trace, item, run_id=run_id))
    return saved


def _is_local_api_path(path: str) -> bool:
    if path in LOCAL_API_PATHS:
        return True
    parts = [part for part in path.split("/") if part]
    if len(parts) == 3 and parts[:2] in (["api", "providers"], ["api", "testcases"]) and parts[2].isdigit():
        return True
    if len(parts) == 4 and parts[:2] == ["api", "providers"] and parts[2].isdigit() and parts[3] == "models":
        return True
    if len(parts) == 4 and parts[:3] == ["api", "results", "testcases"]:
        return True
    return False


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(SITE), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _provider_id_from_path(self, path: str) -> int | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) < 3 or parts[0] != "api" or parts[1] != "providers":
            return None
        try:
            return int(parts[2])
        except ValueError:
            return None

    def _testcase_id_from_path(self, path: str) -> int | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) < 3 or parts[0] != "api" or parts[1] != "testcases":
            return None
        try:
            return int(parts[2])
        except ValueError:
            return None

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/status":
            providers = list_providers()
            selected = list_selected_models()
            testcases = list_testcases()
            primary = testcases[0] if testcases else {
                "prompt_text": BENCHMARK_PROMPT,
                "assertions": BENCHMARK_ASSERTIONS,
            }
            payload = {
                "ok": True,
                "provider_count": len(providers),
                "selected_model_count": len(selected),
                "testcase_count": len(testcases),
                "benchmark_prompt": primary["prompt_text"],
                "expected_results": primary["assertions"],
                "expected_signals": [assertion["value"] for assertion in primary["assertions"]],
                "promptfoo_cmd": PROMPTFOO_CMD + ["<generated-config.json>", "--output", "<generated-results.json>", "--no-table"],
                "viewer_url": f"http://127.0.0.1:{VIEW_PORT}",
                "viewer_path": VIEW_PREFIX,
                "last_run": get_latest_run_payload(selected_models=selected, testcases=testcases),
            }
            json_response(self, HTTPStatus.OK, payload)
            return

        if path == "/api/providers":
            json_response(self, HTTPStatus.OK, {"providers": list_providers()})
            return

        if path == "/api/testcases":
            json_response(self, HTTPStatus.OK, {"testcases": list_testcases()})
            return

        if path == "/api/results/manifest":
            testcases = list_testcases()
            selected = list_selected_models()
            publish_testcase_result_artifacts(testcases, (get_latest_run_payload(selected_models=selected, testcases=testcases) or {}).get("matrix_results", []))
            json_response(self, HTTPStatus.OK, load_results_manifest())
            return

        if path.startswith("/api/results/testcases/"):
            identifier = path.rsplit("/", 1)[-1]
            testcases = list_testcases()
            selected = list_selected_models()
            publish_testcase_result_artifacts(testcases, (get_latest_run_payload(selected_models=selected, testcases=testcases) or {}).get("matrix_results", []))
            payload = load_testcase_result_payload(identifier)
            if payload is None:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": "testcase result not found"})
            else:
                json_response(self, HTTPStatus.OK, payload)
            return

        provider_id = self._provider_id_from_path(path)
        if path.endswith("/models") and provider_id is not None:
            with db_conn() as conn:
                row = conn.execute(
                    "SELECT id, name, provider_type, base_url, api_key FROM providers WHERE id = ?",
                    (provider_id,),
                ).fetchone()
            if row is None:
                json_response(self, HTTPStatus.NOT_FOUND, {"error": "provider not found"})
                return
            try:
                models = remote_model_names(row["base_url"], row["api_key"])
            except Exception as exc:
                json_response(self, HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
                return
            json_response(
                self,
                HTTPStatus.OK,
                {
                    "provider": {
                        "id": row["id"],
                        "name": row["name"],
                        "provider_type": row["provider_type"],
                        "base_url": row["base_url"],
                        "api_key_masked": mask_secret(row["api_key"]),
                    },
                    "models": models,
                },
            )
            return

        if path == VIEW_PREFIX:
            self.send_response(HTTPStatus.MOVED_PERMANENTLY)
            self.send_header("Location", f"{VIEW_PREFIX}/")
            self.end_headers()
            return
        if self._should_proxy_viewer(path):
            self._proxy_to_viewer()
            return
        return super().do_GET()

    def do_HEAD(self):
        path = urlparse(self.path).path
        if self._should_proxy_viewer(path):
            self._proxy_to_viewer(send_body=False)
            return
        return super().do_HEAD()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/providers":
            try:
                payload = self._read_json()
                item = upsert_provider(
                    str(payload.get("name", "")).strip(),
                    str(payload.get("base_url", "")).strip(),
                    str(payload.get("api_key", "")),
                    provider_type=str(payload.get("provider_type", DEFAULT_PROVIDER_TYPE)).strip().lower(),
                )
                json_response(self, HTTPStatus.OK, {"provider": item, "providers": list_providers()})
            except Exception as exc:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if path == "/api/testcases":
            try:
                payload = self._read_json()
                testcase_id = payload.get("id")
                item = upsert_testcase(
                    name=str(payload.get("name", "")).strip(),
                    prompt_text=str(payload.get("prompt_text", "")).strip(),
                    assertions=payload.get("assertions", []),
                    testcase_id=int(testcase_id) if testcase_id is not None else None,
                )
                json_response(self, HTTPStatus.OK, {"testcase": item, "testcases": list_testcases()})
            except Exception as exc:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        provider_id = self._provider_id_from_path(path)
        if provider_id is not None and path.endswith("/models"):
            try:
                payload = self._read_json()
                model_names = payload.get("model_names", [])
                if not isinstance(model_names, list):
                    raise ValueError("model_names must be a list")
                saved = save_selected_models(provider_id, [str(name) for name in model_names])
                json_response(self, HTTPStatus.OK, {"provider_id": provider_id, "selected_models": saved})
            except Exception as exc:
                json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return

        if path == "/api/run":
            try:
                providers = list_providers()
                if not providers:
                    raise ValueError("Add at least one provider before running the benchmark")
                available_models = list_available_models()
                if not available_models:
                    raise ValueError("No models were returned by the configured providers")
                testcases = list_testcases()
                if not testcases:
                    raise ValueError("Create at least one testcase before running the benchmark")

                plan = plan_benchmark_matrix(selected_models=available_models, testcases=testcases)
                matrix_results = list(plan["cached_results"])
                stdout_chunks: list[str] = []
                stderr_chunks: list[str] = []
                exit_code = 0
                testcase_lookup = {item["id"]: item for item in testcases}
                fresh_count = 0

                for item in plan["pending_by_model"]:
                    selected_model = item["selected_model"]
                    pending_cases = item["testcases"]
                    run_result = run_promptfoo_for_model(selected_model, pending_cases)
                    stdout_chunks.append(run_result.get("stdout", ""))
                    stderr_chunks.append(run_result.get("stderr", ""))
                    if run_result["exit_code"] not in {0, 100}:
                        exit_code = max(exit_code, int(run_result["exit_code"]))
                    elif run_result["exit_code"] == 100 and exit_code == 0:
                        exit_code = 100

                    eval_payload = run_result.get("eval_payload")
                    if eval_payload:
                        fresh_rows = extract_promptfoo_case_results(
                            eval_payload=eval_payload,
                            testcase_lookup=testcase_lookup,
                            selected_model=selected_model,
                        )
                        matrix_results.extend(fresh_rows)
                        fresh_count += len(fresh_rows)

                run_state = "cached" if fresh_count == 0 else ("mixed" if plan["cached_count"] else "fresh")
                payload = build_latest_run_payload(
                    selected_models=available_models,
                    testcases=testcases,
                    matrix_results=matrix_results,
                    stdout_chunks=stdout_chunks or [f"Served {plan['cached_count']} valid cached testcase/model results from SQLite."],
                    stderr_chunks=stderr_chunks,
                    exit_code=exit_code,
                    skipped_count=plan["cached_count"],
                    fresh_count=fresh_count,
                    run_state=run_state,
                )
                save_last_run(payload)
                save_benchmark_run_payload(payload)
                publish_testcase_result_artifacts(testcases, payload.get("matrix_results", []))
                json_response(self, HTTPStatus.OK, payload)
            except Exception as exc:
                payload = {"error": str(exc)}
                json_response(self, HTTPStatus.BAD_REQUEST, payload)
            return

        if self._should_proxy_viewer(path):
            self._proxy_to_viewer()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        path = urlparse(self.path).path
        provider_id = self._provider_id_from_path(path)
        if provider_id is not None:
            delete_provider(provider_id)
            json_response(self, HTTPStatus.OK, {"ok": True, "providers": list_providers()})
            return
        testcase_id = self._testcase_id_from_path(path)
        if testcase_id is not None:
            delete_testcase(testcase_id)
            json_response(self, HTTPStatus.OK, {"ok": True, "testcases": list_testcases()})
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self):
        if self._should_proxy_viewer(urlparse(self.path).path):
            self._proxy_to_viewer()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_PATCH(self):
        if self._should_proxy_viewer(urlparse(self.path).path):
            self._proxy_to_viewer()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def _should_proxy_viewer(self, path: str) -> bool:
        if path.startswith(f"{VIEW_PREFIX}/"):
            return True
        if path.startswith("/assets/"):
            return True
        if path in VIEWER_ROOT_PATHS:
            return True
        if path.startswith("/api/") and not _is_local_api_path(path):
            return True
        return False

    def _proxy_to_viewer(self, send_body: bool = True) -> None:
        parsed = urlparse(self.path)
        upstream_path = parsed.path
        if upstream_path.startswith(f"{VIEW_PREFIX}/"):
            upstream_path = upstream_path[len(VIEW_PREFIX):]
            if not upstream_path:
                upstream_path = "/"
        query = f"?{parsed.query}" if parsed.query else ""
        upstream_target = f"{upstream_path}{query}"

        body = None
        if send_body:
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                body = self.rfile.read(length)

        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in {"host", "content-length", "connection", "accept-encoding"}
        }

        last_error: Exception | None = None
        for attempt in range(8):
            conn = http.client.HTTPConnection("127.0.0.1", VIEW_PORT, timeout=5)
            try:
                conn.request(self.command, upstream_target, body=body, headers=headers)
                upstream = conn.getresponse()
                payload = upstream.read()
                self.send_response(upstream.status, upstream.reason)
                for key, value in upstream.getheaders():
                    if key.lower() in {"transfer-encoding", "connection", "content-encoding", "content-length"}:
                        continue
                    self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if self.command != "HEAD":
                    try:
                        self.wfile.write(payload)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                return
            except (ConnectionRefusedError, ConnectionResetError, TimeoutError, OSError) as exc:
                last_error = exc
                time.sleep(0.25 * (attempt + 1))
            finally:
                conn.close()

        message = f"Promptfoo viewer unavailable on 127.0.0.1:{VIEW_PORT}: {last_error}"
        data = message.encode()
        self.send_response(HTTPStatus.SERVICE_UNAVAILABLE)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass


def main() -> None:
    SITE.mkdir(exist_ok=True)
    init_db()
    viewer = start_promptfoo_viewer()
    server = ThreadingHTTPServer((BIND_HOST, PORT), Handler)
    print(f"Serving TI4 benchmark UI on http://{BIND_HOST}:{PORT}")
    print(f"Promptfoo viewer proxied at http://{BIND_HOST}:{PORT}{VIEW_PREFIX}/")
    print(f"SQLite database: {DB_PATH}")
    try:
        server.serve_forever()
    finally:
        viewer.terminate()
        try:
            viewer.wait(timeout=5)
        except subprocess.TimeoutExpired:
            viewer.kill()


def start_promptfoo_viewer() -> subprocess.Popen[str]:
    return subprocess.Popen(
        PROMPTFOO_VIEW_CMD,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


if __name__ == "__main__":
    main()
