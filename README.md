# TI4 Promptfoo Benchmark

Minimales `promptfoo`-Setup fuer TI4-Benchmarks via OpenRouter.
Die Modelle werden per Prompt zu JSON-Ausgaben gezwungen, die Assertions parsen und pruefen dieses JSON feldweise.

## Voraussetzungen

- `OPENROUTER_API_KEY` in `.env`
- Node.js / npm
- Internetzugriff fuer `npx promptfoo@latest`

## Start

```powershell
npx --yes promptfoo@latest eval --config promptfooconfig.reasoning.yaml --env-file .env --output results.reasoning.json
npx --yes promptfoo@latest eval --config promptfooconfig.models.yaml --env-file .env --output results.models.json
npx --yes promptfoo@latest view --no
```

`promptfooconfig.reasoning.yaml` schreibt nach `results.reasoning.json`.
`promptfooconfig.models.yaml` schreibt nach `results.models.json`.
Alle Runs landen zusaetzlich in der Promptfoo-UI-Historie.
`promptfoo view` startet die lokale Promptfoo-UI auf Port `15500`.

Optional gibt es weiterhin die npm-Wrapper:

```powershell
npm run bench:reasoning
npm run bench:models
npm run view
```

Es gibt bewusst nur zwei gepflegte Promptfoo-Configs:

- `promptfooconfig.reasoning.yaml` fuer den Vergleich mit und ohne Reasoning
- `promptfooconfig.models.yaml` fuer den Modellvergleich

## Ein-Klick-Start

```powershell
.\bench-and-view.ps1
```

Das Script fuehrt zuerst den Benchmark aus, startet danach `promptfoo view` im Hintergrund und oeffnet die UI im Browser.
Wenn die lokale Promptfoo-Datenbank defekt ist, legt das Script automatisch ein Backup an und versucht den Lauf mit einer frischen DB erneut.

## Beschlossene Entscheidungen

- Benchmark-Runner: `promptfoo eval` via `npx promptfoo@latest`
- Provider: OpenRouter ueber `OPENROUTER_API_KEY`
- Ergebnisformat: JSON per Promptvorgabe
- Validierung: feldweise Assertions in den Promptfoo-Configs
- `promptfooconfig.reasoning.yaml`:
  - `openai/gpt-5.4` mit `reasoning.effort=low`
  - `openai/gpt-5.4` mit `reasoning.effort=medium`
  - `openai/gpt-5.4` mit `reasoning.effort=high`
  - `anthropic/claude-sonnet-5`
- `promptfooconfig.models.yaml`:
  - `openai/gpt-4.1-nano`
  - `openai/gpt-4.1-mini`
  - `openai/gpt-5.4-mini`
  - `anthropic/claude-sonnet-5`
  - `google/gemini-3.5-flash`
  - `deepseek/deepseek-v3.2`
  - `qwen/qwen3.7-plus`
  - `mistralai/mistral-small-2603`
  - `x-ai/grok-4.20`
  - `deepseek/deepseek-v4-flash`
  - `minimax/minimax-m3`
  - `deepseek/deepseek-v4-pro`
  - `z-ai/glm-5.2`
  - `xiaomi/mimo-v2.5`
  - `google/gemini-3.1-pro-preview`
  - `qwen/qwen3.7-max`
  - `moonshotai/kimi-k2.6`
  - `anthropic/claude-opus-4.8`
  - `openai/gpt-5.5` (most expensive requested model; configured last)

## Aktuelle Testfaelle

- Federation of Sol flagship: `Genesis`
- Argent Flight flagship: `Quetzecoatl`
- Crimson Rebellion flagship: `Quietus`
- Faction roster grouped by source: `base_game`, `pok`, `thunders_edge`

Die Flagship-Tests erwarten aktuell diese JSON-Felder:

- `faction`
- `expansion`
- `name`
- `cost`
- `combat`
- `move`
- `capacity`
- `sustain_damage`
- `ability`

Der Roster-Test erwartet diese JSON-Felder:

- `base_game`
- `pok`
- `thunders_edge`

## Ergebnisse Und Cache

- `results.reasoning.json` enthaelt den letzten Reasoning-Run.
- `results.models.json` enthaelt den letzten Modellvergleichs-Run.
- Die eigentliche Run-Historie fuer `promptfoo view` liegt in `.promptfoo/promptfoo.db`.
- Promptfoo verwendet standardmaessig Disk-Cache fuer identische Evaluations-Eingaben.
- Wenn sich Prompt, Testdaten, Modell oder relevante Config aendern, entstehen neue Provider-Calls statt Cache-Treffer.
- Fuer frische Live-Runs gegen das Modell koennte spaeter `--no-cache` ergaenzt werden. Aktuell ist Caching aktiv.
