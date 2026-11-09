from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MIN_BANK_INDEX = 1
_MIN_GROUP_INDEX = 1
_MAX_GROUP_INDEX = 5


def _file_path(configurations_dir: Path, profile_name: str) -> Path:
    return configurations_dir / f"{profile_name}.json"


def _parse_index(raw: object, low: int, high: int) -> int | None:
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if isinstance(raw, bool) or not (low <= value <= high):
        return None
    return value


def _validate_entry(entry: object) -> dict[str, object] | None:
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


def _validate_action_entry(entry: object) -> dict[str, str] | None:
    """Shape validation only (`"rotary"`/`"button"` must be strings if
    present) - the specific action vocabulary (`ROTARY_ACTIONS`/
    `BUTTON_ACTIONS`) is validated by `MappingEngine.load_bank_control_actions`
    instead, so this module stays decoupled from `mapping.py`'s domain
    constants, same separation `_validate_entry` already draws for axis
    targets.

    @spec MAP-BTNACT-005
    """
    if not isinstance(entry, dict):
        return None
    result: dict[str, str] = {}
    for role in ("rotary", "button"):
        value = entry.get(role)
        if value is None:
            continue
        if not isinstance(value, str):
            return None
        result[role] = value
    return result


def load_bank_actions(configurations_dir: Path, profile_name: str, bank_count: int) -> dict[int, dict[str, str]]:
    """Loads a Controller Profile's persisted per-Bank Rotary/Button action
    overrides (Phase 1.2) - the independent-assignment counterpart to
    `load_group_axis_targets`, stored under its own `bank_actions` key in the
    same per-profile file. Bounds-checked the same way; a missing file or
    missing key is an empty table, not an error.

    @spec MAP-STORE-001, MAP-STORE-002, MAP-STORE-003, MAP-BTNACT-005
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

    bank_actions = raw.get("bank_actions") if isinstance(raw, dict) else None
    if not isinstance(bank_actions, dict):
        return {}

    result: dict[int, dict[str, str]] = {}
    for raw_bank_index, entry in bank_actions.items():
        bank_index = _parse_index(raw_bank_index, _MIN_BANK_INDEX, bank_count)
        validated = _validate_action_entry(entry) if bank_index is not None else None
        if bank_index is None or validated is None:
            logger.warning("Skipping invalid action entry (bank %r) in %s", raw_bank_index, path)
            continue
        if validated:
            result[bank_index] = validated
    return result


def load_group_axis_targets(configurations_dir: Path, profile_name: str, bank_count: int) -> dict[int, dict[int, dict]]:
    """Loads and validates a Controller Profile's persisted (Bank, Group)
    axis-assignment table. Bounds-checks each entry's Bank index (1 through the
    caller-supplied `bank_count` - the active profile's own `ControllerProfile.
    bank_count`, not a fixed global) and Group index (1-5) before use - closing a
    negative-indexing bug an unvalidated Bank index of `0` would otherwise cause
    downstream (`bank_fader_keys[-1]` resolving to the *last* Bank instead of
    erroring). An entry failing validation (bad index, wrong shape) is skipped
    with a logged warning; the file's other valid entries still load. A missing
    or unparseable file is treated as an empty table, not an error.

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
        bank_index = _parse_index(raw_bank_index, _MIN_BANK_INDEX, bank_count)
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


def save_group_axis_targets(
    configurations_dir: Path,
    profile_name: str,
    bank_axes: dict[int, dict[int, dict]],
    bank_actions: dict[int, dict[str, str]] | None = None,
) -> None:
    """Writes a Controller Profile's complete (Bank, Group) axis-assignment table
    and, as of Phase 1.2, its per-Bank Rotary/Button action overrides - both in one
    atomic full rewrite of the same file, replacing any previous contents entirely
    (not a diff/merge): a caller who only has one of the two pieces at hand must
    still pass the other (`MappingEngine.dump_group_axis_targets`/
    `dump_bank_control_actions` together, always re-dumped fresh from the engine)
    rather than this function merging with the file's existing contents, which
    would reintroduce the staleness/race this module's full-rewrite design
    deliberately avoids. `bank_actions` defaults to an empty table for a caller
    that hasn't adopted it yet - unchanged behavior, just an added empty key.
    Creates `configurations_dir` if it doesn't exist. Fails silently on a write
    error (disk full, permissions, or the directory path being blocked by a
    non-directory file) - logged, not raised, matching the Keystroke/WebSocket
    output adapters' precedent; in-memory engine state stays authoritative for
    the running session regardless of whether the write succeeded.

    @spec MAP-STORE-001, MAP-STORE-004, MAP-STORE-005, MAP-STORE-006, MAP-BTNACT-005
    """
    path = _file_path(configurations_dir, profile_name)
    payload = {
        "bank_axes": {
            str(bank_index): {str(group_index): entry for group_index, entry in groups.items()} for bank_index, groups in bank_axes.items()
        },
        "bank_actions": {str(bank_index): dict(actions) for bank_index, actions in (bank_actions or {}).items()},
    }
    try:
        configurations_dir.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
    except OSError as exc:
        logger.warning("Failed to save Preset Store file %s: %s", path, exc)
