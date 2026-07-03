import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
ORIGINAL_PATH = ROOT / "results.models.json"
NORMALIZED_PATH = ROOT / "results.models_normalized.json"


FLAGSHIP_NULL = {
    "faction": None,
    "expansion": None,
    "flagship": {
        "name": None,
        "stats": {
            "cost": None,
            "combat": None,
            "move": None,
            "capacity": None,
            "sustainDamage": None,
        },
        "ability": None,
    },
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_json_loads(value: str) -> Any | None:
    try:
        cleaned = re.sub(r"^```json\s*|^```\s*|\s*```$", "", value.strip(), flags=re.IGNORECASE | re.DOTALL)
        return json.loads(cleaned)
    except Exception:
        return None


def normalize_text(value: str) -> str:
    text = value.replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", text.strip()).lower()


def canonical_name(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    text = normalize_text(value)
    text = text.replace("'", "")
    return text


def canonical_combat(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)) and value:
        scalars = [str(v).strip() for v in value]
        if len(set(scalars)) == 1:
            return f"{scalars[0]}x{len(scalars)}".lower()
        return ",".join(s.lower() for s in scalars)
    text = normalize_text(str(value))
    match = re.fullmatch(r"(\d+)\s*\(?x\s*(\d+)\)?", text.replace(" ", ""))
    if match:
        return f"{match.group(1)}x{match.group(2)}"
    text = text.replace(" ", "")
    return text


def canonical_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    match = re.fullmatch(r"\s*(\d+)\s*", str(value))
    if match:
        return int(match.group(1))
    return None


def canonical_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = normalize_text(str(value))
    if text in {"true", "yes", "y"}:
        return True
    if text in {"false", "no", "n"}:
        return False
    return None


def flatten_scalars(value: Any) -> Iterable[Any]:
    if isinstance(value, dict):
        for inner in value.values():
            yield from flatten_scalars(inner)
        return
    if isinstance(value, list):
        for inner in value:
            yield from flatten_scalars(inner)
        return
    yield value


def dict_get_case_insensitive(payload: dict[str, Any], *keys: str) -> Any:
    lowered = {str(k).lower(): v for k, v in payload.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def extract_original_candidates(raw_output: str, parsed_output: Any) -> dict[str, set[Any]]:
    candidates: dict[str, set[Any]] = {
        "faction": set(),
        "expansion": set(),
        "name": set(),
        "cost": set(),
        "combat": set(),
        "move": set(),
        "capacity": set(),
        "sustainDamage": set(),
        "ability": set(),
        "base_game": set(),
        "pok": set(),
        "thunders_edge": set(),
    }

    if isinstance(parsed_output, dict):
        nested_flagship = dict_get_case_insensitive(parsed_output, "flagship")
        nested_stats = dict_get_case_insensitive(parsed_output, "stats")

        def add(key: str, value: Any) -> None:
            if value is not None:
                if isinstance(value, list):
                    value = tuple(value)
                elif isinstance(value, dict):
                    value = json.dumps(value, ensure_ascii=False, sort_keys=True)
                candidates[key].add(value)

        add("faction", dict_get_case_insensitive(parsed_output, "faction"))
        add("expansion", dict_get_case_insensitive(parsed_output, "expansion", "expansion_source"))
        add("name", dict_get_case_insensitive(parsed_output, "name", "flagship_name", "flagship name"))
        add("cost", dict_get_case_insensitive(parsed_output, "cost"))
        add("combat", dict_get_case_insensitive(parsed_output, "combat"))
        add("move", dict_get_case_insensitive(parsed_output, "move", "movement"))
        add("capacity", dict_get_case_insensitive(parsed_output, "capacity"))
        add(
            "sustainDamage",
            dict_get_case_insensitive(
                parsed_output,
                "sustain_damage",
                "sustaindamage",
                "sustain_damage_status",
                "sustain damage",
            ),
        )
        add("ability", dict_get_case_insensitive(parsed_output, "ability", "flagship_ability"))

        if isinstance(nested_flagship, str):
            add("name", nested_flagship)
        elif isinstance(nested_flagship, dict):
            add("name", dict_get_case_insensitive(nested_flagship, "name"))
            add("cost", dict_get_case_insensitive(nested_flagship, "cost"))
            add("combat", dict_get_case_insensitive(nested_flagship, "combat"))
            add("move", dict_get_case_insensitive(nested_flagship, "move", "movement"))
            add("capacity", dict_get_case_insensitive(nested_flagship, "capacity"))
            add(
                "sustainDamage",
                dict_get_case_insensitive(
                    nested_flagship,
                    "sustain_damage",
                    "sustaindamage",
                    "sustain_damage_status",
                ),
            )
            add("ability", dict_get_case_insensitive(nested_flagship, "ability", "flagship_ability"))
            nested_stats = dict_get_case_insensitive(nested_flagship, "stats") or nested_stats

        if isinstance(nested_stats, dict):
            add("cost", dict_get_case_insensitive(nested_stats, "cost"))
            add("combat", dict_get_case_insensitive(nested_stats, "combat"))
            add("move", dict_get_case_insensitive(nested_stats, "move", "movement"))
            add("capacity", dict_get_case_insensitive(nested_stats, "capacity"))
            add(
                "sustainDamage",
                dict_get_case_insensitive(
                    nested_stats,
                    "sustain_damage",
                    "sustaindamage",
                    "sustain_damage_status",
                ),
            )
            nested_combat = dict_get_case_insensitive(nested_stats, "combat")
            nested_combat_dice = dict_get_case_insensitive(nested_stats, "combat_dice")
            if nested_combat is not None and nested_combat_dice is not None:
                candidates["combat"].add(f"{nested_combat}x{nested_combat_dice}")

        combat = dict_get_case_insensitive(parsed_output, "combat")
        combat_dice = dict_get_case_insensitive(parsed_output, "combat_dice")
        if combat is not None and combat_dice is not None:
            candidates["combat"].add(f"{combat}x{combat_dice}")

        keywords = dict_get_case_insensitive(parsed_output, "keywords")
        if isinstance(keywords, list):
            for item in keywords:
                if isinstance(item, str) and "sustain damage" in normalize_text(item):
                    candidates["sustainDamage"].add(True)

        for group in ("base_game", "pok", "thunders_edge"):
            values = dict_get_case_insensitive(parsed_output, group)
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, str):
                        candidates[group].add(item)

    raw_normalized = normalize_text(raw_output)
    if "sustain damage" in raw_normalized:
        candidates["sustainDamage"].add(True)

    return candidates


def compare_scalar(path: str, normalized_value: Any, original_candidates: dict[str, set[Any]], raw_output: str) -> bool:
    if normalized_value is None:
        return True

    field = path.split(".")[-1]
    if path == "flagship.name":
        field = "name"
    elif path == "flagship.ability":
        field = "ability"
    elif path == "flagship.stats.sustainDamage":
        field = "sustainDamage"

    candidates = original_candidates.get(field, set())
    if field in {"faction", "expansion", "name", "ability"}:
        target = canonical_name(normalized_value)
        if any(canonical_name(candidate) == target for candidate in candidates if candidate is not None):
            return True
        return target in canonical_name(raw_output)
    if field in {"cost", "move", "capacity"}:
        target = canonical_int(normalized_value)
        if any(canonical_int(candidate) == target for candidate in candidates):
            return True
        return target is not None and re.search(rf'(?<!\d){target}(?!\d)', raw_output) is not None
    if field == "combat":
        target = canonical_combat(normalized_value)
        if any(canonical_combat(candidate) == target for candidate in candidates):
            return True
        if target is None:
            return False
        simple_target = target.replace("(", "").replace(")", "")
        simple_raw = normalize_text(raw_output).replace(" ", "")
        return simple_target in simple_raw
    if field == "sustainDamage":
        target = canonical_bool(normalized_value)
        if any(canonical_bool(candidate) == target for candidate in candidates):
            return True
        raw_norm = normalize_text(raw_output)
        if target is True:
            return "true" in raw_norm or "yes" in raw_norm or "sustain damage" in raw_norm
        if target is False:
            return "false" in raw_norm or "no" in raw_norm
        return False
    return False


def compare_array(path: str, normalized_items: list[Any], original_candidates: dict[str, set[Any]], raw_output: str) -> tuple[bool, list[Any]]:
    if not normalized_items:
        return True, []
    field = path
    original_names = {canonical_name(item) for item in original_candidates.get(field, set())}
    raw_canonical = canonical_name(raw_output)
    failures = [
        item for item in normalized_items
        if canonical_name(item) not in original_names and canonical_name(item) not in raw_canonical
    ]
    return not failures, failures


def iter_flagship_checks(normalized: dict[str, Any]) -> list[tuple[str, Any]]:
    flagship = normalized.get("flagship") or {}
    stats = flagship.get("stats") or {}
    return [
        ("faction", normalized.get("faction")),
        ("expansion", normalized.get("expansion")),
        ("flagship.name", flagship.get("name")),
        ("flagship.stats.cost", stats.get("cost")),
        ("flagship.stats.combat", stats.get("combat")),
        ("flagship.stats.move", stats.get("move")),
        ("flagship.stats.capacity", stats.get("capacity")),
        ("flagship.stats.sustainDamage", stats.get("sustainDamage")),
        ("flagship.ability", flagship.get("ability")),
    ]


def validate_entry(index: int, original_entry: dict[str, Any], normalized_entry: dict[str, Any]) -> list[str]:
    raw_original = original_entry["response"].get("output", "")
    raw_normalized = normalized_entry["response"].get("output", "")
    parsed_original = safe_json_loads(raw_original) if isinstance(raw_original, str) else raw_original
    parsed_normalized = safe_json_loads(raw_normalized) if isinstance(raw_normalized, str) else raw_normalized

    if not isinstance(parsed_normalized, dict):
        return [f"entry {index}: normalized output is not valid JSON object"]

    original_candidates = extract_original_candidates(str(raw_original), parsed_original)
    question = original_entry["vars"]["question"]
    errors: list[str] = []

    if "list the faction names grouped by source" in question.lower():
        for field in ("base_game", "pok", "thunders_edge"):
            value = parsed_normalized.get(field)
            if not isinstance(value, list):
                errors.append(f"entry {index}: {field} is not an array in normalized output")
                continue
            ok, failures = compare_array(field, value, original_candidates, str(raw_original))
            if not ok:
                errors.append(f"entry {index}: {field} contains values not supported by original output: {failures}")
        return errors

    for path, value in iter_flagship_checks(parsed_normalized):
        if not compare_scalar(path, value, original_candidates, str(raw_original)):
            errors.append(f"entry {index}: {path}={value!r} not supported by original output")
    return errors


def main() -> int:
    original = load_json(ORIGINAL_PATH)
    normalized = load_json(NORMALIZED_PATH)
    original_results = original["results"]["results"]
    normalized_results = normalized["results"]["results"]

    if len(original_results) != len(normalized_results):
        print(
            f"Length mismatch: original has {len(original_results)} results, normalized has {len(normalized_results)} results."
        )
        return 1

    issues: list[str] = []
    for index, (original_entry, normalized_entry) in enumerate(zip(original_results, normalized_results)):
        issues.extend(validate_entry(index, original_entry, normalized_entry))

    print(f"Validated {len(original_results)} result entries.")
    if issues:
        print(f"FAILED: {len(issues)} validation issue(s) found.")
        for issue in issues:
            print(issue)
        return 1

    print("PASS: all normalized fields are supported by the original outputs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
