# TI4 Promptfoo Benchmark

Minimales `promptfoo`-Setup fuer TI4-Flagship-Benchmarks via OpenRouter.
Die Antwort wird per `response_format: json_schema` als strukturiertes JSON erzwungen und feldweise geprueft.

## Voraussetzungen

- `OPENROUTER_API_KEY` in `.env`
- Node.js / npm
- Internetzugriff fuer `npx promptfoo@latest`

## Start

```powershell
npm run bench
npm run bench:reasoning
npm run bench:models
npm run view
```

`npm run bench` und `npm run bench:reasoning` verwenden `promptfooconfig.reasoning.yaml`.
`npm run bench:models` verwendet `promptfooconfig.models.yaml`.
`npm run bench` und `npm run bench:reasoning` schreiben nach `results.reasoning.json`.
`npm run bench:models` schreibt nach `results.models.json`.
Alle Runs landen zusaetzlich in der Promptfoo-UI-Historie.
`npm run view` startet die lokale Promptfoo-UI auf Port `15500`.

## Ein-Klick-Start

```powershell
.\bench-and-view.ps1
```

Das Script fuehrt zuerst den Benchmark aus, startet danach `promptfoo view` im Hintergrund und oeffnet die UI im Browser.
Wenn die lokale Promptfoo-Datenbank defekt ist, legt das Script automatisch ein Backup an und versucht den Lauf mit einer frischen DB erneut.

## Beschlossene Entscheidungen

- Benchmark-Runner: `promptfoo` via `npx promptfoo@latest`
- Provider: OpenRouter ueber `OPENROUTER_API_KEY`
- Ergebnisformat: strukturiertes JSON per `response_format: json_schema`
- Validierung: feldweise Assertions in den Promptfoo-Configs
- `promptfooconfig.reasoning.yaml`:
  - `openai/gpt-5.4` mit `reasoning.effort=low`
  - `openai/gpt-5.4` mit `reasoning.effort=medium`
  - `openai/gpt-5.4` mit `reasoning.effort=high`
- `promptfooconfig.models.yaml`:
  - `openai/gpt-4.1-nano`
  - `openai/gpt-4.1-mini`
  - `openai/gpt-5.4-mini`
  - `openai/gpt-5.4`

## Aktuelle Testfaelle

- Federation of Sol flagship: `Genesis`
- Argent Flight flagship: `Quetzecoatl`
- Crimson Rebellion flagship: `Quietus`

Jeder Test erwartet aktuell diese JSON-Felder:

- `faction`
- `expansion`
- `name`
- `cost`
- `combat`
- `move`
- `capacity`
- `sustain_damage`
- `ability`

## Quellenbasis

- Sol: Base Game Referenz aus unserem Benchmark-Setup
- Argent Flight: [argent.tex](https://raw.githubusercontent.com/LemonSorcerer/TI4_faction_reference/master/factions/argent.tex)
- Crimson Rebellion: [crimson.tex](https://raw.githubusercontent.com/LemonSorcerer/TI4_faction_reference/master/factions/crimson.tex)

## Ergebnisse Und Cache

- `results.reasoning.json` enthaelt den letzten Reasoning-Run.
- `results.models.json` enthaelt den letzten Modellvergleichs-Run.
- Die eigentliche Run-Historie fuer `promptfoo view` liegt in `.promptfoo/promptfoo.db`.
- Promptfoo verwendet standardmaessig Disk-Cache fuer identische Evaluations-Eingaben.
- Wenn sich Prompt, Testdaten, Modell oder relevante Config aendern, entstehen neue Provider-Calls statt Cache-Treffer.
- Fuer frische Live-Runs gegen das Modell koennte spaeter `--no-cache` ergaenzt werden. Aktuell ist Caching aktiv.
