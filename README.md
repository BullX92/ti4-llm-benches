# ti4-llm-benches

Eigenes privates Repo für TI4/AsyncTI4-bezogene LLM-Benchmarks.

## Ziel

Dieses Repo trennt die LLM-Benchmark-Arbeit sauber vom übrigen TI4/Hermes-Code.
Die Pipeline bleibt absichtlich simpel:
1. konfigurierte Provider lesen
2. konfigurierte Modelle je Provider laden
3. alle YAML-Testcases durchgehen
4. nur fehlende oder invalide Ergebnisse erneut ausführen

## OpenRouter Setup

`.env` kann direkt einen OpenRouter-Provider bootstrappen:

```dotenv
OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY_HERE
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_PROVIDER_NAME=OpenRouter
```

Die Benchmark-Auswahl kommt aus `configured_llms.txt` oder alternativ aus `LLM_BENCH_CONFIGURED_LLMS`.
Eine Zeile pro exakter Modell-ID, zum Beispiel:

```text
openai/gpt-4.1-nano
```

Nur diese konfigurierten Modelle werden ausgeführt. Bereits vorhandene valide `pass`- oder `fail`-Ergebnisse werden aus dem Cache übersprungen.

## Top-Level-Struktur

- `testpipeline/`
  - `server.py` – Benchmark-Server
  - `tests/` – Python-Tests
- `testcases/`
  - YAML-Testfälle
- `testresults/`
  - `manual_results/` – exportierte Beispiel-/Manualläufe
  - `testcase_results/` – publizierte JSON-Ergebnisse zur Laufzeit
  - `runs/` – Laufmetadaten zur Laufzeit
  - `llm_bench.sqlite3` – lokale Cache-DB zur Laufzeit
- `visualize/`
  - `site/` – Browser-UI
- `docs/`
  - `plans/` – Architektur-/Umsetzungsnotizen

## Lauflogik

Ein Cache-Eintrag gilt nur dann als **valide**, wenn er ein fachlich ausgewertetes Ergebnis ist:
- `pass`
- `fail`

Provider-/Transportfehler (`error`) werden **nicht** als valide behandelt und beim nächsten Lauf erneut ausgeführt.

## Start

```bash
cd /opt/data/ti4-llm-benches
/opt/hermes/.venv/bin/python testpipeline/server.py
```

## Hinweis

Die Default-Pfade des Servers zeigen jetzt auf diese Top-Level-Ordner:
- Pipeline-Code: `testpipeline/`
- Testcases: `testcases/`
- Laufzeit-Ergebnisse: `testresults/`
- UI: `visualize/site/`
- Doku/Pläne: `docs/`
