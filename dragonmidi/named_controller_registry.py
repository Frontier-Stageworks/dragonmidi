"""The Named Controller Registry (docs/llds/named-controller.md).

Three distinct concepts, kept distinct by construction: a Hardware Definition
(a module/device's physical capabilities - `grid_modules.py`'s
`GridModuleDefinition`, or a `ControllerProfile`'s `controls:` block) is not a
Named Controller (a particular physical arrangement, this module) is not a
Mapping Preset (the (Bank, Group) axis table a Named Controller's `id` keys in
`preset_store.py`, unchanged by this module).

Grid's heartbeat protocol carries no per-module serial number
(`grid_topology.py`'s own docstring) - a module's only identity within a
session is its settled `(x, y)` position, already non-persistent by design
(the existing USB-root normalization treats raw position as non-identity).
This module therefore never claims per-module identity: Grid matching keys on
the coarser, but actually stable, `module_shape` (the ordered sequence of
recognized module-type names) - accurate enough to distinguish different
*kinds* of arrangement, not to distinguish two physically distinct rigs that
happen to share one. A shape matching more than one saved Named Controller is
always surfaced as ambiguous, never resolved by a heuristic.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_GRID_ID_PATTERN = re.compile(r"^grid-(\d+)$")
_LEGACY_GRID_PRESET_NAME = "Intech Grid"


@dataclass(frozen=True)
class NamedController:
    """@spec NAMEDCTRL-DATA-001"""

    id: str
    display_name: str
    kind: str  # "static" | "grid"
    profile_name: str | None = None
    module_shape: tuple[str, ...] | None = None
    created_at: str = ""


@dataclass(frozen=True)
class Activated:
    controller: NamedController


@dataclass(frozen=True)
class Ambiguous:
    candidates: tuple[NamedController, ...]


def _file_path(named_controllers_dir: Path, id_: str) -> Path:
    return named_controllers_dir / f"{id_}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_named_controller(raw: object) -> NamedController | None:
    if not isinstance(raw, dict):
        return None
    id_ = raw.get("id")
    display_name = raw.get("display_name")
    kind = raw.get("kind")
    if not isinstance(id_, str) or not isinstance(display_name, str) or kind not in ("static", "grid"):
        return None
    profile_name = raw.get("profile_name")
    if profile_name is not None and not isinstance(profile_name, str):
        return None
    raw_shape = raw.get("module_shape")
    module_shape: tuple[str, ...] | None = None
    if raw_shape is not None:
        if not isinstance(raw_shape, list) or not all(isinstance(item, str) for item in raw_shape):
            return None
        module_shape = tuple(raw_shape)
    created_at = raw.get("created_at")
    return NamedController(
        id=id_,
        display_name=display_name,
        kind=kind,
        profile_name=profile_name,
        module_shape=module_shape,
        created_at=created_at if isinstance(created_at, str) else "",
    )


def load_registry(named_controllers_dir: Path) -> tuple[NamedController, ...]:
    """Discovers every `*.json` file in `named_controllers_dir`, creating the
    folder if absent. A file that fails to parse is skipped with a logged
    warning, never raised - the rest of the folder still loads.

    @spec NAMEDCTRL-DATA-002, NAMEDCTRL-DATA-003
    """
    named_controllers_dir.mkdir(parents=True, exist_ok=True)
    results: list[NamedController] = []
    for path in sorted(named_controllers_dir.glob("*.json")):
        try:
            with path.open("r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Skipping unreadable Named Controller file %s: %s", path, exc)
            continue
        parsed = _parse_named_controller(raw)
        if parsed is None:
            logger.warning("Skipping malformed Named Controller file %s", path)
            continue
        results.append(parsed)
    return tuple(results)


def save_named_controller(named_controllers_dir: Path, controller: NamedController) -> None:
    """One file per Named Controller, named after its `id`. Fails silently on
    a write error, matching `preset_store.py`'s precedent - in-memory state
    stays authoritative for the running session regardless.
    """
    path = _file_path(named_controllers_dir, controller.id)
    payload = {
        "id": controller.id,
        "display_name": controller.display_name,
        "kind": controller.kind,
        "profile_name": controller.profile_name,
        "module_shape": list(controller.module_shape) if controller.module_shape is not None else None,
        "created_at": controller.created_at,
    }
    try:
        named_controllers_dir.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
    except OSError as exc:
        logger.warning("Failed to save Named Controller file %s: %s", path, exc)


def ensure_static_named_controller(named_controllers_dir: Path, profile_name: str) -> NamedController:
    """Korg: a transparent 1:1 wrapper, `id == profile_name` always - the
    Preset Store key this produces is byte-identical to the bare profile name
    used before this feature existed, so existing Korg configuration files
    load unchanged.

    @spec NAMEDCTRL-STATIC-001, NAMEDCTRL-STATIC-002
    """
    for existing in load_registry(named_controllers_dir):
        if existing.id == profile_name and existing.kind == "static":
            return existing
    controller = NamedController(
        id=profile_name,
        display_name=profile_name,
        kind="static",
        profile_name=profile_name,
        created_at=_now_iso(),
    )
    save_named_controller(named_controllers_dir, controller)
    return controller


def default_display_name(module_shape: tuple[str, ...]) -> str:
    return f"Intech Grid ({'+'.join(module_shape)})"


def next_grid_id(named_controllers_dir: Path) -> str:
    """`grid-{n}`, `n` one greater than the *highest existing numeric suffix*
    among `kind == "grid"` entries matching that form - not a count, which
    could collide with a surviving higher-numbered entry after a lower one
    was deleted. The legacy-migration `"Intech Grid"` id never matches this
    pattern and is ignored by this scan.

    @spec NAMEDCTRL-MATCH-005
    """
    highest = 0
    for controller in load_registry(named_controllers_dir):
        if controller.kind != "grid":
            continue
        match = _GRID_ID_PATTERN.match(controller.id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"grid-{highest + 1}"


def create_grid_named_controller(named_controllers_dir: Path, module_shape: tuple[str, ...], display_name: str) -> NamedController:
    """Explicit creation under a user-supplied `display_name`, used when the
    Named Controller Ambiguous dialog's "Create new configuration" choice is
    taken (`NAMEDCTRL-AMBIG-002`) - the same `id`-generation scheme
    `resolve_grid_named_controller`'s zero-candidate path uses, but with the
    caller's name instead of the shape-derived default.
    """
    created = NamedController(
        id=next_grid_id(named_controllers_dir),
        display_name=display_name,
        kind="grid",
        module_shape=module_shape,
        created_at=_now_iso(),
    )
    save_named_controller(named_controllers_dir, created)
    return created


def resolve_grid_named_controller(
    named_controllers_dir: Path,
    configurations_dir: Path,
    module_shape: tuple[str, ...],
) -> Activated | Ambiguous:
    """Grid's shape-based zero/one/many matching, after the one-time legacy
    migration check. Never guesses between two or more candidates sharing
    `module_shape` - returns `Ambiguous` instead, and creates nothing.

    @spec NAMEDCTRL-MATCH-001 through NAMEDCTRL-MATCH-006
    @spec NAMEDCTRL-MIGRATE-001, NAMEDCTRL-MIGRATE-002, NAMEDCTRL-MIGRATE-003
    """
    registry = load_registry(named_controllers_dir)
    grid_entries = [c for c in registry if c.kind == "grid"]

    if not grid_entries and (configurations_dir / f"{_LEGACY_GRID_PRESET_NAME}.json").is_file():
        migrated = NamedController(
            id=_LEGACY_GRID_PRESET_NAME,
            display_name=_LEGACY_GRID_PRESET_NAME,
            kind="grid",
            module_shape=module_shape,
            created_at=_now_iso(),
        )
        save_named_controller(named_controllers_dir, migrated)
        return Activated(migrated)

    candidates = [c for c in grid_entries if c.module_shape == module_shape]
    if len(candidates) == 1:
        return Activated(candidates[0])
    if len(candidates) >= 2:
        return Ambiguous(tuple(candidates))

    created = NamedController(
        id=next_grid_id(named_controllers_dir),
        display_name=default_display_name(module_shape),
        kind="grid",
        module_shape=module_shape,
        created_at=_now_iso(),
    )
    save_named_controller(named_controllers_dir, created)
    return Activated(created)


def rename_named_controller(named_controllers_dir: Path, id_: str, new_display_name: str) -> NamedController:
    """Changes only `display_name`; `id`/`kind`/`profile_name`/`module_shape`
    are unchanged, written back to the same file. Raises `ValueError` if no
    record with `id_` exists - a programming-error case, since the UI only
    ever renames a Named Controller it just read from the registry.

    @spec NAMEDCTRL-DATA-004
    """
    for existing in load_registry(named_controllers_dir):
        if existing.id == id_:
            renamed = NamedController(
                id=existing.id,
                display_name=new_display_name,
                kind=existing.kind,
                profile_name=existing.profile_name,
                module_shape=existing.module_shape,
                created_at=existing.created_at,
            )
            save_named_controller(named_controllers_dir, renamed)
            return renamed
    raise ValueError(f"No Named Controller with id {id_!r}")
