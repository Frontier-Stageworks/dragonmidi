"""Grid module definitions (docs/llds/intech-grid.md § Module Definitions).

PBF4/VSN1 are module *templates*, never user-selectable Controller Profiles -
composed at runtime by `grid_controller.py` from whatever `module_type_from_hwcfg()`
resolves. The HWCFG and element-index tables below are protocol facts,
independently reimplemented from Intech Studio's `grid-protocol` source
(`src/grid-protocol.ts`'s `moduleElements[ModuleType.PBF4]` /
`[ModuleType.VSN1L]` / `[ModuleType.VSN1R]`, GPL-3.0-only) - no source lines
copied; see docs/llds/intech-grid.md § Licensing / Provenance.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModuleType(Enum):
    PBF4 = "PBF4"
    VSN1 = "VSN1"


@dataclass(frozen=True)
class GridElement:
    """One element within a module, numbered exactly as Intech's own firmware
    numbers it. `role` is one of
    "fader"/"potentiometer"/"button"/"endless"/"jog_button"/"lcd"."""

    index: int
    role: str


@dataclass(frozen=True)
class GridModuleDefinition:
    name: str
    hwcfg_values: frozenset[int]
    elements: tuple[GridElement, ...]


# PBF4: 0-3 potentiometers, 4-7 faders, 8-11 buttons. Index 255 ("system") is
# not a real I/O control and is not part of this definition.
PBF4_DEFINITION = GridModuleDefinition(
    name="PBF4",
    hwcfg_values=frozenset({64, 65, 67, 75}),  # RevA, RevD, RevH, CD RevH
    elements=tuple(
        [GridElement(i, "potentiometer") for i in range(0, 4)]
        + [GridElement(i, "fader") for i in range(4, 8)]
        + [GridElement(i, "button") for i in range(8, 12)]
    ),
)

# VSN1: 0-7 buttons, 8 endless jog (which also carries its own push-button,
# confirmed at the same index via real hardware - 2026-11-04 validation:
# turning it sends CC on this index, pressing it straight down sends Note
# On/Off on the same index, distinguished by message type like every other
# role here), 9-12 buttons, 13 LCD (not an input control in Phase 1). Index
# 255 ("system") is not part of this definition. VSN1L/VSN1R share this one
# definition - their element tables are identical.
VSN1_DEFINITION = GridModuleDefinition(
    name="VSN1",
    hwcfg_values=frozenset({49, 81, 57, 89, 59, 91}),  # VSN1L/VSN1R x RevA/RevB/RevH
    elements=tuple(
        [GridElement(i, "button") for i in range(0, 8)]
        + [GridElement(8, "endless"), GridElement(8, "jog_button")]
        + [GridElement(i, "button") for i in range(9, 13)]
        + [GridElement(13, "lcd")]
    ),
)

MODULE_DEFINITIONS: tuple[GridModuleDefinition, ...] = (PBF4_DEFINITION, VSN1_DEFINITION)

_HWCFG_TO_TYPE: dict[int, ModuleType] = {
    **{hwcfg: ModuleType.PBF4 for hwcfg in PBF4_DEFINITION.hwcfg_values},
    **{hwcfg: ModuleType.VSN1 for hwcfg in VSN1_DEFINITION.hwcfg_values},
}

_TYPE_TO_DEFINITION: dict[ModuleType, GridModuleDefinition] = {
    ModuleType.PBF4: PBF4_DEFINITION,
    ModuleType.VSN1: VSN1_DEFINITION,
}


def module_type_from_hwcfg(hwcfg: int) -> ModuleType | None:
    """An unrecognized `hwcfg` returns `None` - not an error; the caller
    (`grid_topology.py`) excludes that module from element enumeration without
    failing topology construction by itself.

    @spec GRID-TOPO-004
    """
    return _HWCFG_TO_TYPE.get(hwcfg)


def definition_for_type(module_type: ModuleType) -> GridModuleDefinition:
    return _TYPE_TO_DEFINITION[module_type]
