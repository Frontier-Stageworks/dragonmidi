from __future__ import annotations

from typing import Any, Callable, Protocol

from .controller_profile import ControllerProfile
from .events import MidiEvent


def native_mode_message(channel: int, enter: bool) -> list[int]:
    """KORG Native Mode In/Out Request payload (without the F0/F7 SysEx wrapper).

    @spec MIDI-NATIVE-001, MIDI-NATIVE-002
    """
    return [0x42, 0x40 | channel, 0x00, 0x01, 0x37, 0x02, 0x00, 0x00, 0x00, 0x01 if enter else 0x00]


_SCENE_BUTTON_PREFIX = (0x00, 0x01, 0x37)
_SCENE_BUTTON_MIDDLE = (0x05, 0x00, 0x00, 0x41, 0x40, 0x40)


def _normalize_sysex(data: tuple[int, ...]) -> MidiEvent | None:
    if (
        len(data) == 13
        and data[0] == 0x42
        and data[1] & 0xF0 == 0x40
        and tuple(data[2:5]) == _SCENE_BUTTON_PREFIX
        and tuple(data[5:11]) == _SCENE_BUTTON_MIDDLE
        and data[12] == 0x00
    ):
        value = data[11]
        channel = data[1] & 0x0F
        return MidiEvent(
            type="korg_scene",
            channel=channel,
            number=None,
            raw_value=value,
            normalized=value / 127.0,
            is_press=value > 0,
            is_release=value == 0,
        )
    return None


def normalize_raw(raw: Any) -> MidiEvent | None:
    """Normalize a raw mido-like MIDI message into a MidiEvent.

    @spec MIDI-EVT-001
    """
    msg_type = getattr(raw, "type", None)

    if msg_type == "control_change":
        value = int(raw.value)
        return MidiEvent(
            type="cc",
            channel=raw.channel,
            number=int(raw.control),
            raw_value=value,
            normalized=value / 127.0,
            is_press=value > 0,
            is_release=value == 0,
        )

    if msg_type in ("note_on", "note_off"):
        velocity = int(raw.velocity)
        release = msg_type == "note_off" or velocity == 0
        return MidiEvent(
            type="note",
            channel=raw.channel,
            number=int(raw.note),
            raw_value=velocity,
            normalized=velocity / 127.0,
            is_press=not release,
            is_release=release,
        )

    if msg_type == "pitchwheel":
        pitch = int(raw.pitch)
        normalized = max(0.0, min(1.0, (pitch + 8192) / 16383.0))
        return MidiEvent(
            type="pitchbend",
            channel=raw.channel,
            number=None,
            raw_value=pitch,
            normalized=normalized,
            is_press=pitch > 0,
            is_release=pitch == 0,
        )

    if msg_type == "program_change":
        program = int(raw.program)
        return MidiEvent(
            type="program",
            channel=raw.channel,
            number=program,
            raw_value=program,
            normalized=program / 127.0,
            is_press=True,
            is_release=False,
        )

    if msg_type == "aftertouch":
        value = int(raw.value)
        return MidiEvent(
            type="aftertouch",
            channel=raw.channel,
            number=None,
            raw_value=value,
            normalized=value / 127.0,
            is_press=value > 0,
            is_release=value == 0,
        )

    if msg_type == "polytouch":
        value = int(raw.value)
        return MidiEvent(
            type="polytouch",
            channel=raw.channel,
            number=int(raw.note),
            raw_value=value,
            normalized=value / 127.0,
            is_press=value > 0,
            is_release=value == 0,
        )

    if msg_type == "sysex":
        return _normalize_sysex(tuple(raw.data))

    return None


class MidiBackend(Protocol):
    def list_inputs(self) -> list[str]: ...
    def list_outputs(self) -> list[str]: ...
    def open_input(self, name: str, callback: Callable[[Any], None]) -> Any: ...
    def open_output(self, name: str) -> Any: ...


class _MidoInputPort:
    def __init__(self, port: Any) -> None:
        self._port = port

    def close(self) -> None:
        self._port.close()


class _MidoOutputPort:
    def __init__(self, mido_module: Any, port: Any) -> None:
        self._mido = mido_module
        self._port = port

    def send(self, data: list[int]) -> None:
        self._port.send(self._mido.Message("sysex", data=data))

    def close(self) -> None:
        self._port.close()


class MidoBackend:
    """The real MidiBackend, backed by the `mido` + `python-rtmidi` libraries."""

    def __init__(self) -> None:
        import mido

        self._mido = mido

    def list_inputs(self) -> list[str]:
        return list(self._mido.get_input_names())

    def list_outputs(self) -> list[str]:
        return list(self._mido.get_output_names())

    def open_input(self, name: str, callback: Callable[[Any], None]) -> _MidoInputPort:
        port = self._mido.open_input(name, callback=callback)
        return _MidoInputPort(port)

    def open_output(self, name: str) -> _MidoOutputPort:
        port = self._mido.open_output(name)
        return _MidoOutputPort(self._mido, port)


class MidiInputAdapter:
    """Discovers, connects to, and (when the active Controller Profile has one)
    manages Native Mode for a supported KORG nanoKONTROL controller.

    @spec MIDI-CONN-001, MIDI-CONN-002, MIDI-CONN-003, MIDI-CONN-004, MIDI-CONN-005
    @spec MIDI-CONN-006, MIDI-CONN-007
    @spec MIDI-NATIVE-001, MIDI-NATIVE-002, MIDI-NATIVE-003, MIDI-NATIVE-004, MIDI-NATIVE-005
    @spec MIDI-EVT-001, MIDI-EVT-003, MIDI-EVT-004
    @spec MIDI-PROFILE-004, MIDI-PROFILE-005, MIDI-PROFILE-006, MIDI-PROFILE-007
    """

    def __init__(
        self,
        backend: MidiBackend,
        on_activity: Callable[[], None],
        on_event: Callable[[MidiEvent], None],
        on_connection_change: Callable[[bool, str | None], None],
        on_error: Callable[[bool], None],
        on_reset_mapping: Callable[[], None],
        profile: ControllerProfile,
    ) -> None:
        self._backend = backend
        self._on_activity = on_activity
        self._on_event = on_event
        self._on_connection_change = on_connection_change
        self._on_error = on_error
        self._on_reset_mapping = on_reset_mapping
        self._profile = profile

        self._input_port: Any = None
        self._output_port: Any = None
        self._busy = False

        self.connected = False
        self.device_name: str | None = None

    @property
    def profile(self) -> ControllerProfile:
        return self._profile

    def set_profile(self, profile: ControllerProfile) -> None:
        """Switch the active Controller Profile: disconnect the current device
        (if any, releasing Native Mode first when the outgoing profile had it),
        then start matching future discovery polls against the new profile's
        pattern. Shares `poll_discovery()`/`connect()`/`disconnect()`'s `_busy`
        reentrancy guard, so a switch landing mid-operation is a no-op rather
        than racing an in-flight connect/disconnect.

        @spec MIDI-PROFILE-006, MIDI-PROFILE-007
        """
        if self._busy:
            return
        self._busy = True
        try:
            if self.connected:
                self.disconnect()
            self._profile = profile
        finally:
            self._busy = False

    def poll_discovery(self) -> None:
        # The busy flag is held for the *entire* tick, including the list_inputs()
        # call below - not just inside connect() - so a reentrant tick triggered
        # from within a fake backend's list_inputs() (simulating an overlapping
        # timer firing mid-operation) is a guaranteed no-op, never a second connect.
        if self._busy:
            return
        self._busy = True
        try:
            if self.connected:
                try:
                    still_present = self.device_name in self._backend.list_inputs()
                except Exception:
                    still_present = False
                if not still_present:
                    self.disconnect()
                return

            ports = self._backend.list_inputs()
            matches = [name for name in ports if self._profile.matches(name)]
            if matches:
                self.connect(matches[0])
        finally:
            self._busy = False

    def connect(self, port_name: str) -> None:
        self._on_error(False)  # clear before attempting the handshake (MIDI-NATIVE-004)
        self._input_port = self._backend.open_input(port_name, self._handle_raw_message)
        self.connected = True
        self.device_name = port_name
        self._on_connection_change(True, port_name)
        self._on_reset_mapping()
        if self._profile.has_native_mode:
            self._enable_native_mode(port_name)
        # A profile with no Native Mode (e.g. nanoKONTROL2) skips the handshake
        # entirely: no output port is opened, no SysEx is sent, and the error flag
        # (already cleared above) is never set on this connection's behalf - there
        # is nothing to fail - @spec MIDI-NATIVE-005.

    def _match_output(self, input_name: str) -> str | None:
        outputs = self._backend.list_outputs()
        if input_name in outputs:
            return input_name
        candidates = [name for name in outputs if self._profile.matches(name)]
        return candidates[0] if candidates else None

    def _enable_native_mode(self, port_name: str) -> None:
        output_name = self._match_output(port_name)
        if output_name is None:
            self._on_error(True)
            return
        try:
            self._output_port = self._backend.open_output(output_name)
        except Exception:
            self._output_port = None
            self._on_error(True)
            return
        for channel in range(16):
            try:
                self._output_port.send(native_mode_message(channel, enter=True))
            except Exception:
                pass  # isolate a single failing channel, matching the exit handshake's resilience

    def disconnect(self) -> None:
        if self._output_port is not None:
            for channel in range(16):
                try:
                    self._output_port.send(native_mode_message(channel, enter=False))
                except Exception:
                    pass
            self._output_port.close()
            self._output_port = None
        if self._input_port is not None:
            self._input_port.close()
            self._input_port = None
        self.connected = False
        self.device_name = None
        self._on_connection_change(False, None)

    def _handle_raw_message(self, raw: Any) -> None:
        self._on_activity()  # liveness before normalization (MIDI-EVT-003)
        event = normalize_raw(raw)
        if event is not None:
            self._on_event(event)
