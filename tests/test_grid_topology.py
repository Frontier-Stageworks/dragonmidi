"""Tests for the Grid runtime topology model: snapshot assembly, structural-change
detection, settle semantics, and USB-root normalization
(docs/llds/intech-grid.md § Runtime Topology Model).

@spec GRID-TOPO-005, GRID-TOPO-006, GRID-TOPO-007, GRID-TOPO-008, GRID-TOPO-009
@spec GRID-TOPO-010, GRID-TOPO-011
"""

from __future__ import annotations

from dragonmidi.grid_modules import ModuleType
from dragonmidi.grid_protocol import GridHeartbeat
from dragonmidi.grid_topology import DISCONNECT_TIMEOUT_SECONDS, GridTopologyBuilder, normalize_linear_order, validate_single_row

# --- Immediate (not settle-gated) staleness detection, used by the lifecycle
# --- layer to mark an already-built controller stale the instant anything
# --- structural changes, rather than waiting another settle window ---


def test_has_changed_since_is_false_with_no_structural_change() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    heartbeat = _hb(1, 49, x=0, page=0)
    builder.observe(heartbeat, now=0.0)
    builder.observe(heartbeat, now=0.2)  # ordinary refresh
    assert builder.has_changed_since(baseline=0.0, now=0.3) is False


def test_has_changed_since_is_true_immediately_on_a_new_module_no_settle_wait() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    gridmaster = _hb(1, 49, x=0, page=0)
    builder.observe(gridmaster, now=0.0)
    baseline = 0.2
    builder.observe(_hb(0, 64, x=1), now=0.3)  # a new module appears
    assert builder.has_changed_since(baseline=baseline, now=0.31) is True  # true right away, no settle window needed


SETTLE = 0.5
HEARTBEAT_INTERVAL = 0.2  # well under DISCONNECT_TIMEOUT_SECONDS, matching Grid's real ~250ms cadence


def _hb(heartbeat_type, hwcfg, x, y=0, rotation=0, port_rotation=0, page=None):
    return GridHeartbeat(heartbeat_type=heartbeat_type, hwcfg=hwcfg, x=x, y=y, rotation=rotation, port_rotation=port_rotation, page=page)


def _keep_alive(builder: GridTopologyBuilder, heartbeat: GridHeartbeat, start: float, end: float, interval: float = HEARTBEAT_INTERVAL) -> None:
    """Re-observes `heartbeat` every `interval` seconds from `start` to `end`
    (inclusive-ish), simulating Grid's real periodic heartbeat stream so a
    module under test doesn't spuriously hit its own disconnect timeout while
    the test is waiting for something else (e.g. a settle window) to elapse."""
    t = start
    while t <= end:
        builder.observe(heartbeat, now=t)
        t += interval


# --- Settle semantics (GRID-TOPO-007, GRID-TOPO-008) ---


def test_no_gridmaster_seen_never_settles() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    heartbeat = _hb(0, 64, x=0)  # TYPE=0 only, no gridmaster
    _keep_alive(builder, heartbeat, 0.0, 10.0)
    assert builder.settled(now=10.0) is None


def test_settles_after_window_once_gridmaster_seen_and_stable() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    heartbeat = _hb(1, 49, x=0, page=0)
    builder.observe(heartbeat, now=0.0)
    assert builder.settled(now=0.1) is None  # too soon
    _keep_alive(builder, heartbeat, 0.0, SETTLE + 0.1)
    topology = builder.settled(now=SETTLE + 0.1)
    assert topology is not None
    assert topology.current_page == 0
    assert len(topology.modules) == 1


def test_repeated_unchanged_heartbeat_does_not_restart_the_settle_window() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    heartbeat = _hb(1, 49, x=0, page=0)
    builder.observe(heartbeat, now=0.0)
    builder.observe(heartbeat, now=0.1)  # same module, same fields - ordinary refresh
    builder.observe(heartbeat, now=0.2)
    # Had either refresh restarted the window (based on last_changed, not last_seen),
    # settling would require waiting a further SETTLE past t=0.2 instead of t=0.0.
    assert builder.settled(now=SETTLE + 0.01) is not None


def test_a_structural_change_restarts_the_settle_window() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    gridmaster = _hb(1, 49, x=0, page=0)
    new_module = _hb(0, 64, x=1)
    _keep_alive(builder, gridmaster, 0.0, 1.5)
    _keep_alive(builder, new_module, 0.4, 1.5)  # a genuinely new module, appearing at t=0.4 - structural change
    assert builder.settled(now=0.4 + SETTLE - 0.02) is None  # window restarted at 0.4, not elapsed yet
    assert builder.settled(now=0.4 + SETTLE + 0.01) is not None


def test_a_hwcfg_change_at_an_existing_position_is_a_structural_change() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    gridmaster = _hb(1, 49, x=0, page=0)
    other = _hb(0, 64, x=1)
    builder.observe(gridmaster, now=0.0)
    builder.observe(other, now=0.0)
    _keep_alive(builder, gridmaster, 0.0, 2.0)
    _keep_alive(builder, other, 0.0, SETTLE + 0.01)
    assert builder.settled(now=SETTLE + 0.01) is not None
    # Same (x,y)=(1,0) slot, different hwcfg now - must restart the window.
    builder.observe(_hb(0, 65, x=1), now=SETTLE + 0.02)
    assert builder.settled(now=SETTLE + 0.03) is None


def test_a_page_change_is_a_structural_change() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    gridmaster_page0 = _hb(1, 49, x=0, page=0)
    builder.observe(gridmaster_page0, now=0.0)
    _keep_alive(builder, gridmaster_page0, 0.0, SETTLE + 0.01)
    assert builder.settled(now=SETTLE + 0.01) is not None
    gridmaster_page1 = _hb(1, 49, x=0, page=1)
    builder.observe(gridmaster_page1, now=SETTLE + 0.02)
    assert builder.settled(now=SETTLE + 0.03) is None
    _keep_alive(builder, gridmaster_page1, SETTLE + 0.02, 2 * SETTLE + 0.1)
    settled = builder.settled(now=2 * SETTLE + 0.1)
    assert settled is not None
    assert settled.current_page == 1


def test_a_module_timing_out_is_a_structural_change() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    gridmaster = _hb(1, 49, x=0, page=0)
    other = _hb(0, 64, x=1)
    builder.observe(gridmaster, now=0.0)
    builder.observe(other, now=0.0)
    _keep_alive(builder, gridmaster, 0.0, 3.0)  # gridmaster stays alive for the whole test
    _keep_alive(builder, other, 0.0, 0.4)  # the module at x=1 goes silent after t=0.4
    assert builder.settled(now=SETTLE + 0.01) is not None

    just_after_timeout = 0.4 + DISCONNECT_TIMEOUT_SECONDS + 0.01  # measured from x=1's last heartbeat
    assert builder.settled(now=just_after_timeout) is None  # the expiry itself is a fresh structural change
    settled = builder.settled(now=just_after_timeout + SETTLE + 0.01)
    assert settled is not None
    assert len(settled.modules) == 1  # the timed-out module is gone, the gridmaster remains


# --- Snapshot contents ---


def test_settled_topology_includes_module_type_for_recognized_hwcfg() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    heartbeat = _hb(1, 64, x=0, page=0)
    _keep_alive(builder, heartbeat, 0.0, SETTLE + 0.1)
    topology = builder.settled(now=SETTLE + 0.1)
    assert topology.modules[0].module_type is ModuleType.PBF4


def test_settled_topology_keeps_unrecognized_module_with_none_type() -> None:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    gridmaster = _hb(1, 49, x=0, page=0)
    unknown = _hb(0, 1, x=1)  # hwcfg=1 is not a known module
    _keep_alive(builder, gridmaster, 0.0, SETTLE + 0.1)
    _keep_alive(builder, unknown, 0.0, SETTLE + 0.1)
    topology = builder.settled(now=SETTLE + 0.1)
    unrecognized = [m for m in topology.modules if m.x == 1][0]
    assert unrecognized.module_type is None
    assert unrecognized.hwcfg == 1


# --- USB-root normalization (GRID-TOPO-009) ---


def _settle_three(heartbeats: list[GridHeartbeat]) -> tuple:
    builder = GridTopologyBuilder(settle_window=SETTLE)
    for hb in heartbeats:
        _keep_alive(builder, hb, 0.0, SETTLE + 0.1)
    return builder.settled(now=SETTLE + 0.1)


def test_normalize_linear_order_sorts_by_absolute_x() -> None:
    topology = _settle_three([_hb(1, 64, x=1, page=0), _hb(0, 49, x=0), _hb(0, 64, x=2)])
    ordered = normalize_linear_order(topology.modules)
    assert [m.x for m in ordered] == [0, 1, 2]


def test_normalize_linear_order_is_invariant_to_a_constant_x_offset() -> None:
    topo_a = _settle_three([_hb(1, 64, x=-1, page=0), _hb(0, 49, x=0), _hb(0, 64, x=1)])
    topo_b = _settle_three([_hb(1, 64, x=0, page=0), _hb(0, 49, x=1), _hb(0, 64, x=2)])

    ordered_a = normalize_linear_order(topo_a.modules)
    ordered_b = normalize_linear_order(topo_b.modules)
    assert [m.hwcfg for m in ordered_a] == [m.hwcfg for m in ordered_b] == [64, 49, 64]


# --- Single-row validation (GRID-TOPO-010, GRID-TOPO-011) ---


def test_validate_single_row_passes_when_every_module_shares_y() -> None:
    topology = _settle_three([_hb(1, 64, x=0, y=0, page=0), _hb(0, 49, x=1, y=0)])
    assert validate_single_row(topology) is True


def test_validate_single_row_fails_if_any_module_recognized_or_not_differs_in_y() -> None:
    topology = _settle_three([_hb(1, 64, x=0, y=0, page=0), _hb(0, 1, x=0, y=1)])  # hwcfg=1 unrecognized, still checked
    assert validate_single_row(topology) is False
