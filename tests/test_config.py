"""Tests for the editable host/port config controller (docs/specs/app-ui.md § Status UI).

@spec UI-CONFIG-001
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dragonmidi.config import ConfigController, EndpointConfig

port_strategy = st.integers(min_value=1, max_value=65535)


@given(
    hosts=st.lists(st.text(min_size=1, max_size=15), min_size=1, max_size=5),
    ports=st.lists(port_strategy, min_size=1, max_size=5),
)
# @spec UI-CONFIG-001
def test_edits_never_take_effect_before_apply(hosts: list[str], ports: list[int]) -> None:
    applied_calls: list = []
    controller = ConfigController(EndpointConfig(), on_apply=lambda cfg, changed: applied_calls.append(cfg))
    initial = controller.applied

    for host, port in zip(hosts, ports):
        controller.edit(host=host, dragonframe_port=port)
        assert controller.applied == initial  # editing alone must never mutate the applied config

    assert applied_calls == []


# @spec UI-CONFIG-001
def test_apply_commits_pending_edits() -> None:
    applied_calls = []
    controller = ConfigController(EndpointConfig(), on_apply=lambda cfg, changed: applied_calls.append(cfg))
    controller.edit(host="10.0.0.5", dragonframe_port=9000, listen_port=9001)
    controller.apply()
    assert controller.applied.host == "10.0.0.5"
    assert controller.applied.dragonframe_port == 9000
    assert len(applied_calls) == 1


# @spec UI-CONFIG-001, OSC-CONFIG-002
def test_apply_with_equal_ports_is_rejected_and_does_not_change_applied_config() -> None:
    applied_calls = []
    controller = ConfigController(EndpointConfig(), on_apply=lambda cfg, changed: applied_calls.append(cfg))
    original = controller.applied
    controller.edit(dragonframe_port=8000, listen_port=8000)

    try:
        controller.apply()
        raised = False
    except ValueError:
        raised = True

    assert raised
    assert controller.applied == original  # rollback: invalid apply must not take effect
    assert applied_calls == []


@given(new_listen_port=port_strategy)
# @spec UI-CONFIG-001, OSC-LISTEN-006
def test_apply_reports_whether_listen_port_actually_changed(new_listen_port: int) -> None:
    initial = EndpointConfig(host="127.0.0.1", dragonframe_port=7010, listen_port=7011)
    changed_flags = []
    controller = ConfigController(initial, on_apply=lambda cfg, changed: changed_flags.append(changed))

    controller.edit(listen_port=new_listen_port)
    if new_listen_port == initial.dragonframe_port:
        try:
            controller.apply()
        except ValueError:
            return  # equal-ports case is covered by a dedicated test; not this property's concern
    else:
        controller.apply()

    expected_changed = new_listen_port != initial.listen_port
    assert changed_flags == [expected_changed]


# @spec UI-CONFIG-001, OSC-LISTEN-006
def test_apply_with_only_host_changed_reports_listen_port_unchanged() -> None:
    initial = EndpointConfig(host="127.0.0.1", dragonframe_port=7010, listen_port=7011)
    changed_flags = []
    controller = ConfigController(initial, on_apply=lambda cfg, changed: changed_flags.append(changed))
    controller.edit(host="192.168.1.50")
    controller.apply()
    assert changed_flags == [False]
