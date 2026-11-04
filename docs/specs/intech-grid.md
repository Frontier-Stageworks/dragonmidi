# Intech Grid Support — EARS Specs

Traces to `docs/llds/intech-grid.md`. None of the requirements below are implemented yet (`[ ]`, per `CLAUDE.md`'s "active gap" marker) — this file records the finalized Phase-1 design ahead of the tests-first/code phases.

## Discovery

- [ ] **GRID-DISCOVER-001**: The system shall detect Grid's USB-MIDI interface by fuzzy-matching the enumerated MIDI port name against a `match_substring` of `"intechgridmidi"` (the normalized form of Grid's confirmed MIDI interface descriptor string, `"Intech Grid MIDI"`), using the existing `MidiInputAdapter` discovery/auto-connect mechanism (`docs/specs/midi-input.md`) unchanged.
- [ ] **GRID-DISCOVER-002**: The system shall detect Grid's USB-CDC interface by filtering enumerated serial ports against Grid's known VID/PID pairs (`(0x03eb, 0xecac)`, `(0x303a, 0x8123)`, `(0x2e8a, 0x1145)`); a port's name matching Grid's confirmed CDC interface descriptor string (`"Intech Grid CDC"`) may corroborate a match but shall never substitute for the VID/PID filter.
- [ ] **GRID-DISCOVER-003**: If exactly one candidate Grid CDC port is found, the system shall open it at 2,000,000 baud and proceed to topology acquisition (`GRID-TOPO-*`).
- [ ] **GRID-DISCOVER-004**: If more than one candidate Grid CDC port is found, the system shall not open any of them and shall report an ambiguous-chains status (`docs/llds/intech-grid.md § UI Implications`); Grid shall not become the active controller while more than one candidate remains.
- [ ] **GRID-DISCOVER-005**: While no candidate Grid CDC port, or no matching Grid MIDI port, is found, the system shall remain in the same "waiting for device" state `docs/specs/midi-input.md` already defines for any controller with no connected device, rather than partially activating.
- [ ] **GRID-DISCOVER-006**: The system shall discover and open both the Grid MIDI and Grid CDC interfaces without requiring Grid Editor, or any other companion application, to be running.

## Topology Acquisition

- [ ] **GRID-TOPO-001**: The system shall parse Grid CDC byte traffic as `SOH` (`0x01`) / `EOB` (`0x17`)-delimited frames; a byte sequence that does not form a complete, well-formed frame before the next `SOH` shall be discarded without raising, and parsing shall resynchronize on the next `SOH`.
- [ ] **GRID-TOPO-002**: From a frame whose heartbeat `TYPE` is `0` ("grid") or `1` ("gridmaster"), the system shall extract `hwcfg`, `x`, `y`, `rotation`, and `port_rotation`; from a `TYPE=1` frame specifically, the system shall additionally extract the current page number carried in that same transmission's `PAGEACTIVE` sub-frame.
- [ ] **GRID-TOPO-003**: The system shall treat a frame whose heartbeat `TYPE` is anything other than `0` or `1` — `255` ("editor") specifically, and any other value the protocol does not define as a module — as not a Grid module; such a frame shall be recognized and discarded, not treated as a parse failure or a third kind of module.
- [ ] **GRID-TOPO-004**: The system shall resolve a heartbeat's `hwcfg` to a supported module type (PBF4 or VSN1, `docs/llds/intech-grid.md § Module Definitions`) via a fixed lookup table; an `hwcfg` matching neither shall not raise and shall not, by itself, fail topology construction.
- [ ] **GRID-TOPO-005**: The system shall treat two heartbeats reporting the same `(x, y)` with the same `hwcfg` and `rotation` as an ongoing liveness refresh of the same module, not as a new or changed module.
- [ ] **GRID-TOPO-006**: The system shall classify each of the following as a structural topology change: a new `(x, y)` position appearing; an `(x, y)` position present in the current snapshot not reporting within Grid's own disconnect timeout (500ms); an `(x, y)` position reporting a different `hwcfg` or `rotation` than it previously reported; the gridmaster's reported current page changing. No other condition shall count as a structural change.
- [ ] **GRID-TOPO-007**: The system shall not consider a topology settled until no structural change (`GRID-TOPO-006`) has occurred for a configurable settle duration (Phase 1 default: 500ms) and at least one `TYPE=1` ("gridmaster") heartbeat has been observed.
- [ ] **GRID-TOPO-008**: An ordinary, unchanged heartbeat refresh of an already-known module shall not restart the settle duration in `GRID-TOPO-007`.
- [ ] **GRID-TOPO-009**: The system shall derive each recognized module's normalized left-to-right rank by sorting every recognized module in a settled topology by absolute `x` ascending; this rank, not absolute `x`, shall be the basis for every logical-control numbering rule (`GRID-CTRL-002`, `GRID-CTRL-003`).
- [ ] **GRID-TOPO-010**: If a settled topology contains any module — recognized or unrecognized — whose `y` differs from the rest, the system shall reject the topology as unsupported for Phase 1 and shall not construct a Grid runtime controller from it.
- [ ] **GRID-TOPO-011**: An unrecognized module within a topology that otherwise satisfies `GRID-TOPO-010` shall be excluded from element enumeration and shall not, by itself, cause topology rejection.
- [ ] **GRID-TOPO-012**: WHEN a structural topology change (`GRID-TOPO-006`) is detected while a Grid runtime controller built from a prior settled topology is active, THE SYSTEM SHALL mark that controller stale immediately, without attempting a live rebuild.

## Runtime Controller

- [ ] **GRID-CTRL-001**: The system shall expose a Grid runtime controller's `bank_count` as the count of normalized PBF4 fader elements only, distinct from its total logical-control count (`docs/llds/intech-grid.md § Active Grid Controller`).
- [ ] **GRID-CTRL-002**: The system shall number PBF4 faders, potentiometers, and buttons each `1..N` left-to-right across every PBF4 module in the normalized topology, independently of one another, such that a non-PBF4 or unrecognized module interposed between two PBF4 modules neither resets nor interrupts any of the three sequences.
- [ ] **GRID-CTRL-003**: The system shall assign VSN1's button and jog logical identities independent of VSN1's position in the normalized topology, such that relocating VSN1 within the row does not change those identities.
- [ ] **GRID-CTRL-004**: For Phase 1, the system shall support at most one recognized VSN1 module in a topology. IF more than one recognized VSN1 module is present, THEN THE SYSTEM SHALL NOT construct a Grid runtime controller from that topology, reporting an unsupported-topology outcome — a second VSN1 would otherwise alias the same `("grid_vsn1_button", N)`/`("grid_vsn1_jog", None)` logical identities as the first, a logical-identity collision distinct from or additional to any raw-address collision (`GRID-CTRL-005`) that does not, by itself, necessarily occur.
- [ ] **GRID-CTRL-005**: IF two recognized elements of a settled, single-row topology would resolve to the same `(channel, message type, controller/note number)`, THEN THE SYSTEM SHALL NOT construct a Grid runtime controller from that topology, and shall report an address-collision outcome instead.
- [ ] **GRID-CTRL-006**: The system shall not let one of two colliding elements (`GRID-CTRL-005`) silently override the other in a constructed address table; a detected collision shall abort construction entirely, not produce a partial table.
- [ ] **GRID-CTRL-007**: A Grid runtime controller shall satisfy the same structural `ActiveController` shape (`name`, `default_channel`, `has_native_mode`, `has_jog_wheel`, `has_scene_button`, `bank_count`, `bank_fader_keys`, `fader_keys`, `knob_to_fader`, `mute_to_fader`, `fader_to_knob`, `opinionated_map`, `control_names`, `websocket_keys`, `group_keys`, `bank_fader_key()`, `matches()`) that `ControllerProfile` already satisfies, without itself being a `ControllerProfile` instance.
- [ ] **GRID-CTRL-008**: The system shall report `has_jog_wheel = False` for a Grid runtime controller; VSN1's jog shall be represented as its own logical control (`("grid_vsn1_jog", None)`), not dispatched through the Korg-specific fixed-CC110 jog-wheel decode path.
- [ ] **GRID-CTRL-009**: The system shall derive a Grid runtime controller's `default_channel` as the settled topology's current page modulo 16, not a fixed constant.

## MIDI Resolution

- [ ] **GRID-MIDI-001**: The system shall compute each recognized element's expected MIDI channel as `(moduleY * 4 + currentPage) % 16` and its expected controller/note number as `(32 + moduleX * 16 + elementIndex) % 128`, using each module's absolute (un-normalized) `x`/`y` — never the normalized rank (`GRID-TOPO-009`) — per Grid's documented factory-default ("MIDI Auto") addressing.
- [ ] **GRID-MIDI-002**: The system shall expect Note On as the message type for a button-role element and Control Change for every other recognized role.
- [ ] **GRID-MIDI-003**: The system shall resolve an incoming MIDI event to a logical control via a single lookup against a precomputed address table built at topology-settle time, not a per-event re-evaluation of the addressing formula.
- [ ] **GRID-MIDI-004**: Before a Grid topology has settled for the first time, the system shall resolve every incoming Grid MIDI event to nothing.
- [ ] **GRID-MIDI-005**: WHILE the active Grid runtime controller is marked stale (`GRID-TOPO-012`), THE SYSTEM SHALL resolve every incoming Grid MIDI event to nothing, until the controller is rebuilt via an explicit reselection of Intech Grid as the active controller.
- [ ] **GRID-MIDI-006**: An incoming MIDI event that matches no entry in the current address table shall resolve to nothing; the system shall not guess the nearest or most-likely-intended logical control.
- [ ] **GRID-MIDI-007**: A resolved logical control's `MidiEvent` shall carry the original event's `channel`, `raw_value`, `normalized`, `is_press`, and `is_release` fields unchanged, with only its `type`/`number` fields rewritten to the resolved logical identity.

## Mapping Integration

- [ ] **GRID-MAP-001**: A Grid-resolved logical control's `MidiEvent` shall be passed to the existing `MappingEngine.process()`/`process_websocket()`/`process_keystroke()` entry points exactly as any other controller's event is, via the same `_Key` dispatch; the system shall not implement a separate Grid-specific output path to OSC, WebSocket, or keystroke synthesis.
- [ ] **GRID-MAP-002**: Bank/Group axis-assignment math (`docs/specs/static-mapping.md § MAP-WS-002`, `§ MAP-GROUP-*`) shall use the active controller's `bank_count` regardless of whether it is sourced from a static `ControllerProfile` or a runtime Grid controller, with no Grid-specific branch anywhere in the Mapping Engine.
- [ ] **GRID-MAP-003**: The Preset Store shall persist and load a Grid runtime controller's (Bank, Group) axis-assignment table keyed by a fixed profile name (`"Intech Grid"`) and positional Bank index, using the same file format and the same caller-supplied `bank_count` bounds check (`docs/specs/static-mapping.md § MAP-STORE-003`) already used for static Controller Profiles, with no Grid-specific schema.
- [ ] **GRID-MAP-004**: Loading a persisted (Bank, Group) entry whose Bank index exceeds the currently-connected Grid topology's `bank_count` shall be skipped with a logged warning, identically to the existing out-of-range handling for a static Controller Profile, and shall not be treated as an error.
- [ ] **GRID-MAP-005**: Selecting, using, or persisting Grid as the active controller shall not alter the behavior, opinionated map, or persisted data of any existing static Controller Profile (nanoKONTROL Studio, nanoKONTROL2).

## References

- `docs/llds/intech-grid.md` — the LLD these specs trace to; see it for the full rationale, source citations, and Decisions & Alternatives behind each requirement above.
- `docs/specs/static-mapping.md § MAP-CONFIG-*`, `§ MAP-WS-002`, `§ MAP-STORE-*` — the controller-derived `bank_count` and Bank-index bounds-check requirements `GRID-MAP-002`/`003`/`004` reuse unchanged.
- `docs/specs/midi-input.md § Device Discovery and Auto-Connect` — the discovery/auto-connect requirements `GRID-DISCOVER-001`/`005` reuse unchanged for Grid's MIDI side.
