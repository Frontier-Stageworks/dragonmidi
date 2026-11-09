"""Controller Profile dropdown choice representation (docs/llds/intech-grid.md
§ Active Grid Controller). A loaded `ControllerProfile` is available
immediately; "Intech Grid" must be offerable in the dropdown *before* a
`GridRuntimeController` exists at all (its shape isn't known until topology
settles) - a `GridChoice` is a bare selection marker, never a fabricated
static profile standing in for one.
"""

from __future__ import annotations

from dataclasses import dataclass

from .controller_profile import ControllerProfile
from .grid_controller import GRID_PROFILE_NAME as GRID_CHOICE_NAME


@dataclass(frozen=True)
class StaticChoice:
    profile: ControllerProfile

    @property
    def name(self) -> str:
        return self.profile.name


@dataclass(frozen=True)
class GridChoice:
    name: str = GRID_CHOICE_NAME


ControllerChoice = StaticChoice | GridChoice


def build_controller_choices(profiles: tuple[ControllerProfile, ...]) -> tuple[ControllerChoice, ...]:
    """Every discovered static profile, in their existing order, with the
    built-in Intech Grid choice appended last."""
    return tuple(StaticChoice(profile=p) for p in profiles) + (GridChoice(),)
