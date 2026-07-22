from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

from .controller_profile import ControllerProfile
from .mapping import ControlsConfig, ControlsConfigError, build_profile

logger = logging.getLogger(__name__)

_EXTENSIONS = (".yaml", ".yml")

_REQUIRED_FIELDS = (
    "name",
    "match_substring",
    "has_native_mode",
    "default_channel",
    "has_jog_wheel",
    "has_scene_button",
    "controls",
)

_README_TEXT = """# DragonMIDI Controller Profiles

Drop a `.yaml` (or `.yml`) file in this folder to add a new MIDI control surface to
DragonMIDI's Controller Profile dropdown - no code changes, no rebuild. Relaunch
DragonMIDI after adding, editing, or removing a file here for the change to take
effect.

A file here with the same `name` as one of DragonMIDI's bundled profiles overrides
it entirely.

See the Controller Profile authoring guide for the full config file schema.
`nanokontrol2.yaml.example` in this folder is a working example - rename it (drop
the trailing `.example`) to try it.
"""

_EXAMPLE_SUFFIX = ".example"


@dataclass(frozen=True)
class LoadFailure:
    path: Path
    reason: str


@dataclass(frozen=True)
class LoadResult:
    profiles: tuple[ControllerProfile, ...]
    failures: tuple[LoadFailure, ...]


def _discover_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix in _EXTENSIONS)


def _ensure_user_dir_seeded(user_dir: Path) -> None:
    """@spec PROFILE-LOAD-007"""
    if user_dir.exists():
        return
    user_dir.mkdir(parents=True)
    (user_dir / "README.md").write_text(_README_TEXT, encoding="utf-8")
    example_path = user_dir / f"nanokontrol2.yaml{_EXAMPLE_SUFFIX}"
    example_content = yaml.safe_dump(
        {
            "name": "nanoKONTROL2",
            "match_substring": "nanokontrol2",
            "has_native_mode": False,
            "default_channel": 1,
            "has_jog_wheel": False,
            "has_scene_button": False,
            "setup_hint": "Hold SET MARKER + CYCLE while powering on for CC mode",
            "controls": {
                "faders": list(range(8)),
                "knobs": list(range(16, 24)),
                "mutes": list(range(48, 56)),
                "solos": list(range(32, 40)),
                "transport": {
                    "record": 45,
                    "play": 41,
                    "stop": 42,
                    "rewind": 43,
                    "fast_forward": 44,
                    "cycle": 46,
                    "previous_marker": 61,
                    "next_marker": 62,
                    "previous_track": 58,
                    "next_track": 59,
                },
            },
        },
        sort_keys=False,
    )
    example_path.write_text(example_content, encoding="utf-8")


def _parse_controls(raw: object, path: Path) -> ControlsConfig:
    if not isinstance(raw, dict):
        raise ControlsConfigError(f"{path}: 'controls' must be a mapping")
    try:
        return ControlsConfig(
            faders=tuple(raw["faders"]),
            knobs=tuple(raw["knobs"]),
            mutes=tuple(raw["mutes"]),
            solos=tuple(raw["solos"]),
            transport=dict(raw.get("transport") or {}),
            jog_wheel=raw.get("jog_wheel"),
        )
    except KeyError as exc:
        raise ControlsConfigError(f"{path}: 'controls' missing required field {exc}") from exc


def _validate_top_level_fields(raw: dict, path: Path) -> None:
    """@spec PROFILE-LOAD-010"""
    for field_name in _REQUIRED_FIELDS:
        if field_name not in raw:
            raise ControlsConfigError(f"{path}: missing required field '{field_name}'")

    if not isinstance(raw["name"], str) or not isinstance(raw["match_substring"], str):
        raise ControlsConfigError(f"{path}: 'name' and 'match_substring' must be strings")

    for flag in ("has_native_mode", "has_jog_wheel", "has_scene_button"):
        if not isinstance(raw[flag], bool):
            raise ControlsConfigError(f"{path}: '{flag}' must be a boolean")

    channel = raw["default_channel"]
    if isinstance(channel, bool) or not isinstance(channel, int) or not (1 <= channel <= 16):
        raise ControlsConfigError(f"{path}: 'default_channel' must be an integer from 1 to 16")

    setup_hint = raw.get("setup_hint")
    if setup_hint is not None and not isinstance(setup_hint, str):
        raise ControlsConfigError(f"{path}: 'setup_hint' must be a string or omitted")


def _parse_profile_file(path: Path) -> ControllerProfile:
    """@spec PROFILE-LOAD-002, PROFILE-LOAD-008, PROFILE-LOAD-009, PROFILE-LOAD-010"""
    with path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)

    if not isinstance(raw, dict):
        raise ControlsConfigError(f"{path}: file must contain a YAML mapping at the top level")

    _validate_top_level_fields(raw, path)
    controls = _parse_controls(raw["controls"], path)

    return build_profile(
        name=raw["name"],
        match_substring=raw["match_substring"],
        has_native_mode=raw["has_native_mode"],
        default_channel=raw["default_channel"] - 1,  # 1-based in file -> 0-based (@spec PROFILE-LOAD-008)
        has_jog_wheel=raw["has_jog_wheel"],
        has_scene_button=raw["has_scene_button"],
        controls=controls,
        setup_hint=raw.get("setup_hint"),
    )


def _load_directory(directory: Path) -> tuple[list[ControllerProfile], list[LoadFailure]]:
    profiles: list[ControllerProfile] = []
    failures: list[LoadFailure] = []
    for path in _discover_files(directory):
        try:
            profiles.append(_parse_profile_file(path))
        except (ControlsConfigError, yaml.YAMLError, TypeError, ValueError) as exc:
            logger.warning("Skipping invalid Controller Profile config %s: %s", path, exc)
            failures.append(LoadFailure(path=path, reason=str(exc)))
    return profiles, failures


def _warn_on_match_substring_collisions(profiles: list[ControllerProfile]) -> None:
    """@spec PROFILE-LOAD-006"""
    for i, a in enumerate(profiles):
        for b in profiles[i + 1 :]:
            if a.name == b.name:
                continue  # same-name override collisions are handled by the merge itself
            if a.match_substring in b.match_substring or b.match_substring in a.match_substring:
                logger.warning(
                    "Controller Profiles %r and %r have overlapping match_substring values (%r, %r)",
                    a.name,
                    b.name,
                    a.match_substring,
                    b.match_substring,
                )


def load_controller_profiles(bundled_dir: Path, user_dir: Path) -> LoadResult:
    """Discovers Controller Profiles from the bundled folder (shipped inside the app
    build) and the user-local folder (read directly off disk, no rebuild needed),
    merging them with user-local profiles taking precedence - and ordered first - on
    a `name` collision.

    @spec PROFILE-LOAD-001, PROFILE-LOAD-003, PROFILE-LOAD-004, PROFILE-LOAD-005
    @spec PROFILE-LOAD-011
    """
    _ensure_user_dir_seeded(user_dir)

    bundled_profiles, bundled_failures = _load_directory(bundled_dir)
    user_profiles, user_failures = _load_directory(user_dir)

    user_names = {p.name for p in user_profiles}
    merged = list(user_profiles) + [p for p in bundled_profiles if p.name not in user_names]

    _warn_on_match_substring_collisions(merged)

    return LoadResult(profiles=tuple(merged), failures=tuple(bundled_failures + user_failures))
