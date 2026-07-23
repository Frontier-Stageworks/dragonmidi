from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MIN_BANK_INDEX = 1
_MAX_BANK_INDEX = 8
_MIN_GROUP_INDEX = 1
_MAX_GROUP_INDEX = 5


def _file_path(configurations_dir: Path, profile_name: str) -> Path:
    return configurations_dir / f"{profile_name}.json"


def _parse_index(raw: object, low: int, high: int) -> "int | None":
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if isinstance(raw, bool) or not (low <= value <= high):
        return None
    return value


def _validate_entry(entry: object) -> "dict[str, object] | None":
    if not isinstance(entry, dict):
        return None
    axis_name = entry.get("axis_name")
    min_value = entry.get("min")
    max_value = entry.get("max")
    if not isinstance(axis_name, str):
        return None
    if isinstance(min_value, bool) or not isinstance(min_value, (int, float)):
        return None
    if isinstance(max_value, bool) or not isinstance(max_value, (int, float)):
        return None
    return {"axis_name": axis_name, "min": float(min_value), "max": float(max_value)}


def load_group_axis_targets(configurations_dir: Path, profile_name: str) -> "dict[int, dict[int, dict]]":
    """Loads and validates a Controller Profile's persisted (Bank, Group)
    axis-assignment table. Bounds-checks each entry's Bank index (1-8) and Group
    index (1-5) before use - closing a negative-indexing bug an unvalidated Bank
    index of `0` would otherwise cause downstream (`bank_fader_keys[-1]`
    resolving to the *last* Bank instead of erroring). An entry failing
    validation (bad index, wrong shape) is skipped with a logged warning; the
    file's other valid entries still load. A missing or unparseable file is
    treated as an empty table, not an error.

    @spec MAP-STORE-001, MAP-STORE-002, MAP-STORE-003
    """
    path = _file_path(configurations_dir, profile_name)
    if not path.is_file():
        return {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skipping unreadable Preset Store file %s: %s", path, exc)
        return {}

    bank_axes = raw.get("bank_axes") if isinstance(raw, dict) else None
    if not isinstance(bank_axes, dict):
        return {}

    result: dict[int, dict[int, dict]] = {}
    for raw_bank_index, groups in bank_axes.items():
        bank_index = _parse_index(raw_bank_index, _MIN_BANK_INDEX, _MAX_BANK_INDEX)
        if bank_index is None or not isinstance(groups, dict):
            logger.warning("Skipping invalid bank index %r in %s", raw_bank_index, path)
            continue
        for raw_group_index, entry in groups.items():
            group_index = _parse_index(raw_group_index, _MIN_GROUP_INDEX, _MAX_GROUP_INDEX)
            validated = _validate_entry(entry) if group_index is not None else None
            if group_index is None or validated is None:
                logger.warning("Skipping invalid group entry (bank %r, group %r) in %s", raw_bank_index, raw_group_index, path)
                continue
            result.setdefault(bank_index, {})[group_index] = validated
    return result


def save_group_axis_targets(configurations_dir: Path, profile_name: str, bank_axes: "dict[int, dict[int, dict]]") -> None:
    """Writes a Controller Profile's complete (Bank, Group) axis-assignment table,
    replacing any previous contents entirely (full rewrite, not a diff/merge).
    Creates `configurations_dir` if it doesn't exist. Fails silently on a write
    error (disk full, permissions, or the directory path being blocked by a
    non-directory file) - logged, not raised, matching the Keystroke/WebSocket
    output adapters' precedent; in-memory engine state stays authoritative for
    the running session regardless of whether the write succeeded.

    @spec MAP-STORE-001, MAP-STORE-004, MAP-STORE-005, MAP-STORE-006
    """
    path = _file_path(configurations_dir, profile_name)
    payload = {
        "bank_axes": {str(bank_index): {str(group_index): entry for group_index, entry in groups.items()} for bank_index, groups in bank_axes.items()}
    }
    try:
        configurations_dir.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
    except OSError as exc:
        logger.warning("Failed to save Preset Store file %s: %s", path, exc)
