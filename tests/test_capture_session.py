"""Tests for the Guided Capture and Guided Verify sessions' Qt-free domain
logic (docs/specs/midi-monitor.md § Guided Capture, § Guided Verify).

@spec MON-GUIDE-001, MON-GUIDE-002, MON-GUIDE-003, MON-GUIDE-004, MON-GUIDE-005
@spec MON-GUIDE-006, MON-GUIDE-007, MON-GUIDE-008, MON-GUIDE-010, MON-GUIDE-012
@spec MON-VERIFY-001 through MON-VERIFY-009
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dragonmidi.capture_session import (
    CaptureStep,
    GuidedCaptureSession,
    GuidedVerifySession,
    VerifyStep,
    build_capture_steps,
    build_report,
    build_verify_report,
    build_verify_steps,
    save_capture_session,
    save_verify_session,
)
from dragonmidi.control_descriptor import ControlDescriptor
from dragonmidi.controller_profile_loader import load_controller_profiles
from dragonmidi.events import MidiEvent
from dragonmidi.midi_monitor import MonitorEvent


@dataclass
class _FakeController:
    bank_count: int
    unconfirmed_channel_controls: tuple[str, ...] = ()
    unconfirmed_global_controls: tuple[str, ...] = ()


@dataclass
class _ControllerWithoutUnconfirmedFields:
    """Stands in for a Grid-style controller with no such concept at all."""

    bank_count: int = 8


def _bundled_controllers_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "dragonmidi" / "controllers"


def _cc(number: int = 36, channel: int = 15, raw_value: int = 127) -> MidiEvent:
    return MidiEvent(type="cc", channel=channel, number=number, raw_value=raw_value, normalized=raw_value / 127, is_press=True, is_release=False)


def _entry(raw: MidiEvent, device_name: str | None = "nanoKONTROL Studio SOUND") -> MonitorEvent:
    return MonitorEvent(timestamp=0.0, device_name=device_name, raw=raw, resolved=None, module=None, captured=False)


# --- Building steps from a controller's declared gaps (MON-GUIDE-001, 002) ---


def test_build_capture_steps_expands_channel_controls_per_bank_then_global_controls() -> None:
    controller = _FakeController(
        bank_count=3, unconfirmed_channel_controls=("Record", "Select"), unconfirmed_global_controls=("Set Marker", "Return to Zero")
    )

    steps = build_capture_steps(controller)

    assert steps == [
        CaptureStep("Record 1"),
        CaptureStep("Record 2"),
        CaptureStep("Record 3"),
        CaptureStep("Select 1"),
        CaptureStep("Select 2"),
        CaptureStep("Select 3"),
        CaptureStep("Set Marker"),
        CaptureStep("Return to Zero"),
    ]


def test_build_capture_steps_is_empty_for_a_fully_confirmed_controller() -> None:
    controller = _FakeController(bank_count=8)
    assert build_capture_steps(controller) == []


def test_build_capture_steps_handles_a_controller_with_no_such_attributes_at_all() -> None:
    """Matches setup_hint's existing duck-typed, Protocol-absent precedent -
    a Grid-style controller simply produces zero steps, not an AttributeError."""
    controller = _ControllerWithoutUnconfirmedFields()
    assert build_capture_steps(controller) == []


def test_build_capture_steps_is_empty_for_the_real_nanokontrol_studio_profile(tmp_path) -> None:
    """Exercises the real ControllerProfile/YAML, not a fake. Record/Select/
    Set Marker/Return to Zero were confirmed via a real Guided Capture
    session (Phase 1.6.1, 2026-11-12) and removed from the Studio's
    unconfirmed_channel_controls/unconfirmed_global_controls - this is the
    direct regression guard that Guided Capture no longer prompts for them."""
    result = load_controller_profiles(bundled_dir=_bundled_controllers_dir(), user_dir=tmp_path / "controllers")
    studio = next(p for p in result.profiles if p.name == "nanoKONTROL Studio")

    assert build_capture_steps(studio) == []


def test_build_capture_steps_against_the_real_nanokontrol2_profile(tmp_path) -> None:
    """nanoKONTROL2 still has real, unconfirmed controls (no capture
    evidence gathered for it yet) - guards against this feature and
    static-mapping.md's declarations drifting apart silently."""
    result = load_controller_profiles(bundled_dir=_bundled_controllers_dir(), user_dir=tmp_path / "controllers")
    nk2 = next(p for p in result.profiles if p.name == "nanoKONTROL2")

    steps = build_capture_steps(nk2)

    labels = [s.label for s in steps]
    assert labels == [f"Record {n}" for n in range(1, 9)] + ["Set Marker"]


# --- Session state machine (MON-GUIDE-003 through 008) ---


def test_session_starts_at_the_first_step_with_nothing_pending() -> None:
    session = GuidedCaptureSession("nanoKONTROL Studio", [CaptureStep("Record 1"), CaptureStep("Record 2")])
    assert session.current_step == CaptureStep("Record 1")
    assert session.pending is None
    assert session.finished is False


def test_offer_sets_pending_and_a_second_offer_replaces_it_not_accumulates() -> None:
    session = GuidedCaptureSession("p", [CaptureStep("Record 1")])
    first = _entry(_cc(number=34))
    second = _entry(_cc(number=35))

    session.offer(first)
    assert session.pending is first

    session.offer(second)
    assert session.pending is second  # replaced, not accumulated


def test_confirm_locks_in_pending_and_advances_clearing_pending() -> None:
    session = GuidedCaptureSession("p", [CaptureStep("Record 1"), CaptureStep("Record 2")])
    entry = _entry(_cc(number=34, raw_value=127))
    session.offer(entry)

    session.confirm()

    assert len(session.results) == 1
    result = session.results[0]
    assert result.label == "Record 1"
    assert result.skipped is False
    assert result.raw is entry.raw
    assert result.device_name == entry.device_name
    assert session.current_step == CaptureStep("Record 2")
    assert session.pending is None


def test_confirm_with_nothing_pending_records_no_raw_but_still_advances() -> None:
    """Defensive: the dialog disables Confirm while nothing is pending
    (MON-GUIDE-004), but the domain object itself stays correct either way."""
    session = GuidedCaptureSession("p", [CaptureStep("Record 1")])
    session.confirm()
    assert session.results[0].raw is None
    assert session.results[0].skipped is False


def test_skip_records_a_skip_and_advances_even_with_something_pending() -> None:
    session = GuidedCaptureSession("p", [CaptureStep("Record 1"), CaptureStep("Record 2")])
    session.offer(_entry(_cc(34)))  # user pressed something, but chooses Skip anyway

    session.skip()

    result = session.results[0]
    assert result.skipped is True
    assert result.raw is None
    assert session.current_step == CaptureStep("Record 2")
    assert session.pending is None


def test_session_finishes_after_the_last_step_and_further_actions_are_no_ops() -> None:
    session = GuidedCaptureSession("p", [CaptureStep("Record 1")])
    session.confirm()

    assert session.finished is True
    assert session.current_step is None

    session.offer(_entry(_cc(99)))  # no-op: nothing to offer to
    assert session.pending is None
    session.confirm()  # no-op: no step to confirm
    session.skip()  # no-op: no step to skip
    assert len(session.results) == 1  # unchanged


def test_results_preserve_step_order_mixing_confirmed_and_skipped() -> None:
    session = GuidedCaptureSession("p", [CaptureStep("A"), CaptureStep("B"), CaptureStep("C")])
    session.offer(_entry(_cc(1)))
    session.confirm()  # A: captured
    session.skip()  # B: skipped
    session.offer(_entry(_cc(3)))
    session.confirm()  # C: captured

    labels_and_skipped = [(r.label, r.skipped) for r in session.results]
    assert labels_and_skipped == [("A", False), ("B", True), ("C", False)]


# --- Report / save (MON-GUIDE-010, 012) ---


def test_build_report_never_invents_a_controller_profile_or_mapping_write() -> None:
    """MON-GUIDE-012: nothing in this module touches the Mapping Engine, the
    Preset Store, or a controller definition - verified by construction:
    build_report()/save_capture_session() only ever produce/write a plain
    dict/JSON file, never import or call into mapping.py, preset_store.py,
    or controller_profile.py's write paths."""
    session = GuidedCaptureSession("nanoKONTROL Studio", [CaptureStep("Record 1"), CaptureStep("Set Marker")])
    session.offer(_entry(_cc(number=34, channel=15, raw_value=127), device_name="nanoKONTROL Studio SOUND"))
    session.confirm()
    session.skip()

    report = build_report("nanoKONTROL Studio", session.results, clock=lambda: 1_700_000_000.0)

    assert report["profile_name"] == "nanoKONTROL Studio"
    assert report["results"] == [
        {
            "label": "Record 1",
            "skipped": False,
            "raw": {"type": "cc", "channel": 15, "number": 34, "raw_value": 127},
            "device_name": "nanoKONTROL Studio SOUND",
        },
        {"label": "Set Marker", "skipped": True, "raw": None, "device_name": None},
    ]


def test_save_capture_session_writes_a_json_file_and_creates_the_directory(tmp_path) -> None:
    directory = tmp_path / "capture_sessions"  # does not exist yet
    session = GuidedCaptureSession("nanoKONTROL Studio", [CaptureStep("Record 1")])
    session.offer(_entry(_cc(number=34)))
    session.confirm()

    path = save_capture_session(directory, "nanoKONTROL Studio", session.results, clock=lambda: 1_700_000_000.0)

    assert path.is_file()
    assert path.parent == directory
    assert path.name.startswith("nanoKONTROL Studio-")
    assert path.name.endswith(".json")
    written = json.loads(path.read_text())
    assert written["profile_name"] == "nanoKONTROL Studio"
    assert written["results"][0]["label"] == "Record 1"


def test_saving_twice_produces_two_distinct_files_when_clocks_differ(tmp_path) -> None:
    session = GuidedCaptureSession("p", [CaptureStep("A")])
    session.skip()

    first = save_capture_session(tmp_path, "p", session.results, clock=lambda: 1_700_000_000.0)
    second = save_capture_session(tmp_path, "p", session.results, clock=lambda: 1_700_000_001.0)

    assert first != second
    assert first.is_file() and second.is_file()


# ============================================================
# Guided Verify Session (docs/specs/midi-monitor.md § Guided Verify)
# ============================================================


def _resolved_entry(resolved, device_name: str | None = "X") -> MonitorEvent:
    """A MonitorEvent as it would look once Grid has resolved it - raw CC is
    deliberately unrelated to `resolved`, matching how a real Grid raw
    address bears no numeric relationship to its logical key."""
    raw = _cc(number=99)
    return MonitorEvent(timestamp=0.0, device_name=device_name, raw=raw, resolved=resolved, module=None, captured=False)


# --- Building steps from the real Controller Descriptor list (MON-VERIFY-001) ---


def test_build_verify_steps_mirrors_the_descriptor_list_exactly() -> None:
    descriptors = [
        ControlDescriptor(key=("cc", 0), label="Fader Channel 1", control_type="fader"),
        ControlDescriptor(key=("cc", 64), label="Record 1", control_type="button"),
    ]
    steps = build_verify_steps(descriptors)
    assert steps == [VerifyStep("Fader Channel 1", ("cc", 0)), VerifyStep("Record 1", ("cc", 64))]


# --- actual-identity resolution: resolved key wins when present, else raw (MON-VERIFY-004) ---


def test_pending_passed_compares_raw_identity_for_a_non_grid_control() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Record 1", ("cc", 64))])
    session.offer(_entry(_cc(number=64)))  # raw matches expected exactly
    assert session.pending_passed is True


def test_pending_passed_compares_resolved_identity_when_grid_has_resolved_it() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Grid Fader 3", ("grid_fader", 3))])
    # Raw CC (99) bears no relation to the logical key - only `resolved` matters.
    session.offer(_resolved_entry(resolved=("grid_fader", 3)))
    assert session.pending_passed is True


def test_pending_passed_is_false_on_a_genuine_mismatch() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Record 1", ("cc", 64))])
    session.offer(_entry(_cc(number=65)))  # wrong control pressed
    assert session.pending_passed is False


def test_pending_passed_is_none_before_anything_is_offered() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Record 1", ("cc", 64))])
    assert session.pending_passed is None


# --- offer/advance/retry state machine (MON-VERIFY-003, 005, 006, 007, 008) ---


def test_offer_replaces_pending_not_accumulates() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Record 1", ("cc", 64))])
    first = _entry(_cc(65))
    second = _entry(_cc(64))
    session.offer(first)
    session.offer(second)
    assert session.pending is second


def test_advance_records_a_pass_and_moves_to_the_next_step() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Record 1", ("cc", 64)), VerifyStep("Record 2", ("cc", 65))])
    session.offer(_entry(_cc(64), device_name="D"))
    session.advance()

    assert len(session.results) == 1
    result = session.results[0]
    assert result.passed is True
    assert result.expected_key == ("cc", 64)
    assert result.actual_key == ("cc", 64)
    assert result.device_name == "D"
    assert session.current_step == VerifyStep("Record 2", ("cc", 65))
    assert session.pending is None


def test_advance_records_a_failure_without_blocking_progress() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Record 1", ("cc", 64)), VerifyStep("Record 2", ("cc", 65))])
    session.offer(_entry(_cc(99)))  # wrong control
    session.advance()

    result = session.results[0]
    assert result.passed is False
    assert result.actual_key == ("cc", 99)
    assert session.current_step == VerifyStep("Record 2", ("cc", 65))  # still advanced


def test_advance_with_nothing_pending_is_a_no_op() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Record 1", ("cc", 64))])
    session.advance()
    assert session.results == ()
    assert session.current_step == VerifyStep("Record 1", ("cc", 64))


def test_retry_discards_pending_without_advancing() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Record 1", ("cc", 64))])
    session.offer(_entry(_cc(99)))
    assert session.pending_passed is False

    session.retry()

    assert session.pending is None
    assert session.current_step == VerifyStep("Record 1", ("cc", 64))  # unchanged, no result recorded
    assert session.results == ()


def test_session_finishes_after_the_last_step() -> None:
    session = GuidedVerifySession("p", [VerifyStep("Record 1", ("cc", 64))])
    session.offer(_entry(_cc(64)))
    session.advance()

    assert session.finished is True
    assert session.current_step is None
    assert session.pending_passed is None  # nothing left to check against

    session.offer(_entry(_cc(64)))  # no-op: nothing to offer to
    assert session.pending is None


def test_results_preserve_order_mixing_pass_and_fail() -> None:
    session = GuidedVerifySession("p", [VerifyStep("A", ("cc", 1)), VerifyStep("B", ("cc", 2)), VerifyStep("C", ("cc", 3))])
    session.offer(_entry(_cc(1)))
    session.advance()  # A: pass
    session.offer(_entry(_cc(99)))
    session.advance()  # B: fail
    session.offer(_entry(_cc(3)))
    session.advance()  # C: pass

    assert [(r.label, r.passed) for r in session.results] == [("A", True), ("B", False), ("C", True)]


# --- Report / save (MON-VERIFY-009) ---


def test_build_verify_report_includes_expected_and_actual_keys() -> None:
    session = GuidedVerifySession("nanoKONTROL Studio", [VerifyStep("Record 1", ("cc", 64)), VerifyStep("Record 2", ("cc", 65))])
    session.offer(_entry(_cc(64), device_name="D"))
    session.advance()
    session.offer(_entry(_cc(99)))
    session.advance()

    report = build_verify_report("nanoKONTROL Studio", session.results, clock=lambda: 1_700_000_000.0)

    assert report["profile_name"] == "nanoKONTROL Studio"
    assert report["results"][0]["passed"] is True
    assert report["results"][0]["expected_key"] == ["cc", 64]
    assert report["results"][0]["actual_key"] == ["cc", 64]
    assert report["results"][1]["passed"] is False
    assert report["results"][1]["actual_key"] == ["cc", 99]


def test_save_verify_session_writes_a_distinctly_named_json_file(tmp_path) -> None:
    session = GuidedVerifySession("nanoKONTROL Studio", [VerifyStep("Record 1", ("cc", 64))])
    session.offer(_entry(_cc(64)))
    session.advance()

    path = save_verify_session(tmp_path, "nanoKONTROL Studio", session.results, clock=lambda: 1_700_000_000.0)

    assert path.is_file()
    assert "-verify-" in path.name  # distinct from a Guided Capture report in the same folder
    written = json.loads(path.read_text())
    assert written["results"][0]["label"] == "Record 1"
