# Agent Guide

## Purpose

This repository benchmarks LLM knowledge of Twilight Imperium 4 with
[Promptfoo](https://www.promptfoo.dev/) and OpenRouter. Keep benchmark changes
reproducible, keep credentials private, and distinguish source files from generated
results.

## Repository map

- `promptfooconfig.reasoning.yaml`: compares reasoning settings and a non-OpenAI
  reference model.
- `promptfooconfig.models.yaml`: compares the selected model set.
- `results.reasoning.json` and `results.models.json`: raw Promptfoo outputs.
- `generate-report.mjs`: turns one raw result file into a self-contained HTML report.
- `generate-site.mjs`: regenerates both detail reports and `benchmark-site.html`.
- `bench-and-view.ps1`: runs the default benchmark and starts the Promptfoo UI.
- `configured_llms.txt`: catalog/selection notes; it is not currently consumed by
  the npm scripts or Promptfoo configs.

The two Promptfoo YAML files are the benchmark source of truth. HTML reports and
result JSON files are generated artifacts; do not hand-edit them.

## OpenRouter provider convention

Follow the current
[Promptfoo OpenRouter provider documentation](https://www.promptfoo.dev/docs/providers/openrouter/).
For new providers, use Promptfoo's native OpenRouter ID:

```yaml
providers:
  - id: openrouter:openai/gpt-4.1-mini
    label: gpt-4.1-mini
    config:
      temperature: 0.1
      max_tokens: 1000
```

The maintained configs use `openrouter:<model-id>`. Do not reintroduce the older
compatible form `openai:chat:<model-id>` with an OpenRouter `apiBaseUrl`, and do not
mix both forms within one config without a documented compatibility reason.

- Read credentials from `OPENROUTER_API_KEY`.
- Never commit `.env`, API keys, bearer tokens, or key-bearing logs/results.
- Use `config.apiKeyEnvar` only when a deliberately different environment variable
  is required.
- Use `config.apiBaseUrl` only for an OpenRouter-compatible proxy or gateway. The
  native provider already defaults to `https://openrouter.ai/api/v1`.
- Do not rely on `OPENAI_API_BASE_URL` or `OPENAI_BASE_URL`; the native OpenRouter
  provider does not use those fallbacks.
- OpenRouter model IDs and context limits change. Verify model IDs against the live
  OpenRouter catalog before adding or replacing a model.
- For models that return thinking content, set `showThinking: false` when reasoning
  text would break the benchmark's JSON-only response contract. Its documented
  default is `true`.
- Preserve model-specific settings such as reasoning effort only after confirming
  that the selected model and current Promptfoo/OpenRouter path support them.

## Benchmark rules

- Keep prompts deterministic and require one valid JSON object with no Markdown.
- Set a low temperature unless the experiment explicitly measures variability.
- Give every test stable `metadata.name` and `metadata.description` values.
- Validate structure first, then validate individual fields.
- Assertions should tolerate harmless formatting variants but must not weaken the
  factual expectation being measured.
- When adding a testcase, add it to both configs unless it intentionally belongs to
  only one experiment; document intentional differences.
- Keep provider labels unique and stable because the report generators group results
  by provider label.
- Do not change benchmark questions, expected answers, providers, and scoring logic
  in one opaque edit. Make the experimental variable clear.

## Commands

Run from the repository root in PowerShell:

```powershell
npm run bench:reasoning
npm run bench:models
npm run view
npm run report:reasoning
npm run report:models
npm run report:site
```

`npm run bench` is an alias for the reasoning benchmark. Benchmark commands make
paid network calls through OpenRouter and may reuse Promptfoo's disk cache. Do not
run them merely to validate formatting, and do not add `--no-cache` unless a fresh
paid run is explicitly required.

Promptfoo may return exit code `100` when an evaluation completes with failed
assertions. `bench-and-view.ps1` intentionally treats exit codes `0` and `100` as
completed runs.

## Verification

Use the smallest verification appropriate to the change:

1. For report-generator changes, run the affected `npm run report:*` command and
   inspect the generated HTML.
2. For site aggregation changes, run `npm run report:site`.
3. For Promptfoo config changes, validate the YAML/config without making provider
   calls when possible.
4. Run a live benchmark only when requested or when fresh results are necessary to
   verify the change; state that it can incur cost.
5. Run only the benchmark config requested by the user. Treat model exclusions as
   applying to exact model IDs unless the user explicitly excludes a model family.
6. Review `git diff` and do not overwrite unrelated working-tree changes.

When a benchmark is intentionally rerun, keep the matching raw JSON and generated
HTML reports synchronized.
