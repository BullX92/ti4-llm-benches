# ti4-llm-benches

Eigenes privates Repo für TI4/AsyncTI4-bezogene LLM-Benchmarks.

## Ziel

Dieses Repo trennt die LLM-Benchmark-Arbeit sauber vom übrigen TI4/Hermes-Code.

Enthalten sind insbesondere:
- Benchmark-Server und UI
- testcase-basierte TI4-Benchmarks
- manuelle Ergebnisartefakte
- Pläne zur testcase-first JSON-/Web-Architektur
- Tests für die llm_bench-Logik

## Struktur

- `evals/llm_bench/`
  - `server.py` – Benchmark-Server
  - `site/` – Browser-UI
  - `testcases/` – Benchmark-Testfälle
  - `manual_results/` – exportierte Beispiel-/Manualläufe
  - `plans/` – Architektur-/Umsetzungsnotizen
- `tests/`
  - `test_llm_bench.py` – Tests

## Nicht migriert

Bewusst **nicht** übernommen werden laufzeitnahe oder lokale Artefakte:
- SQLite-Datenbanken
- `runs_*`-Statusdateien
- `__pycache__/`
- lokale Secrets / Tokens / Env-Dateien

## Start

```bash
cd /opt/data/ti4-llm-benches
/opt/hermes/.venv/bin/python evals/llm_bench/server.py
```

## Nächste sinnvolle Schritte

1. Test- und Start-Workflow im neuen Repo validieren
2. ggf. `requirements.txt`/`pyproject.toml` ergänzen
3. testcase-first JSON-Output und UI hier fertigziehen
4. später getrennt deployen
