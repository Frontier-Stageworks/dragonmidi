# Intech Grid Support

## Context and Design Philosophy

Continues `docs/high-level-design.md § Delivery Phasing` (Phase 7) and `§ Key Design Decisions`' Intech Grid entries. This LLD owns everything between "an Intech Studio Grid chain of PBF4/VSN1 modules is connected" and "the Mapping Engine (`docs/llds/static-mapping.md`) receives ordinary logical-control events" — it does not own anything downstream of that handoff (Bank/Group math, the Preset Store, the Mapping View), which are `static-mapping.md`'s and `app-ui.md`'s territory, unchanged by this document.

**Grid is architecturally unlike every existing Controller Profile**, for one reason: a Controller Profile's shape (which CCs exist, how many channel strips) is a fixed fact about one physical device, declared once in a YAML file and never rediscovered. Grid's shape is a fact about *today's physical arrangement* of interchangeable modules, discovered fresh each time the chain is connected, over a channel MIDI itself doesn't carry (topology). Forcing Grid through the YAML `ControlsConfig`/`ControllerProfile` path would mean either inventing a fake static profile that lies about a fact (device shape) that isn't static, or teaching the config-file format to describe something it was never meant to express (a runtime-discovered topology). Neither is this LLD's approach — see Active Grid Controller below.

**This document's governing constraint, inherited from the HLD**: Grid-specific knowledge — topology, module definitions, the position-derived MIDI addressing formula — is confined entirely to the components this LLD defines. The moment an incoming Grid MIDI event resolves to a logical control, it is handed to the *existing* Mapping Engine exactly as a Korg profile's own `(type, number)` keys already are. Nothing downstream of that handoff needs to know Grid exists. This is why `ControllerProfile.bank_count` becoming controller-derived (rather than a hardcoded `8`) was a prerequisite refactor completed before this LLD was drafted — Grid's runtime-discovered width is now just another value for a property every consumer already reads generically.

**Scope: Phase 1 only.** PBF4 and VSN1 modules, a single horizontal row, factory-default MIDI Auto addressing, no live structural rebuild. See Non-Goals below for the complete exclusion list.

## 1. Grid CDC Transport

Grid exposes two independent USB interfaces (source: `grid-fw/d51n20a/grid/d51/tusb_config.h`): a standard USB-MIDI class interface, carrying ordinary Note/CC traffic DragonMIDI already knows how to read (`docs/llds/midi-input.md`'s `MidiBackend`/`normalize_raw()`); and a USB-CDC virtual serial port at **2,000,000 baud**, carrying Grid's own ASCII-framed protocol (topology heartbeats, Lua scripting, LED control, etc.) — DragonMIDI needs only the heartbeat subset of this second channel.

**No Grid Editor dependency.** Grid Editor opens the CDC port itself via the browser's Web Serial API, filtered by a plain VID/PID allowlist in its own `configuration.json` — nothing about this is a proprietary handshake. A standalone client opening the same port directly needs nothing else running.

- **`GridTransport`**, a `Protocol` parallel to `midi_input.py`'s existing `MidiBackend` (`list_inputs`/`open_input`/`list_outputs`/`open_output`): `list_candidate_ports() -> list[str]` (serial ports matching Grid's known VID/PID pairs), `open(port_name: str, callback: Callable[[bytes], None]) -> GridConnection` (callback receives raw byte chunks as they arrive, mirroring `open_input`'s per-message callback shape), `close()`.
- **`SerialGridTransport`**, the real implementation, backed by `pyserial` (a new dependency — not yet in `pyproject.toml`; adding it is Phase 2 implementation work, not this LLD). Opens at 2,000,000 baud. Port candidates are filtered against the VID/PID pairs grid-editor itself uses (source: `grid-editor/configuration.json`) — `(0x03eb, 0xecac)`, `(0x303a, 0x8123)`, `(0x2e8a, 0x1145)`. **A second, independent signal confirms the right port**: Grid's shared USB descriptor source (`grid-fw/common/src/c/grid_usb.c`) gives the CDC interface its own descriptor string, `"Intech Grid CDC"`, distinct from the device's bare product string (`"Grid"`) — where the OS surfaces that interface string in the enumerated port name, `SerialGridTransport` can fuzzy-match it the same way `ControllerProfile.matches()` already fuzzy-matches a MIDI port name (see §8), as a belt-and-suspenders check alongside the VID/PID filter rather than instead of it (VID/PID is still required — a port's OS-surfaced name, unlike a MIDI port's, isn't guaranteed to carry the interface string on every platform).
- **Discovery/reconnect**: mirrors `MidiInputAdapter.poll_discovery()` exactly — poll candidate ports on a timer, connect to the first match when not already connected, treat a read failure or the port vanishing from the list as a disconnect, resume polling. No new concurrency model; this is the same single-loop, serially-executed pattern `midi-input.md`'s Device Discovery and Auto-Connect section already specifies, applied to a second transport.
- **Not over-designed**: a single candidate port is connected to (first match, same "log the choice, don't build a picker" tolerance as duplicate MIDI ports, `docs/llds/midi-input.md § Device Discovery`). No platform-specific USB enumeration beyond what `pyserial`'s own cross-platform port listing already provides.

## 2. Grid Frame / Heartbeat Parser

**Wire format** (source: `grid-fw/common/src/c/grid_protocol.h`): frames are delimited by `SOH` (`0x01`) and `EOB` (`0x17`) control bytes. A `HEARTBEAT`-class chunk inside a frame carries, at fixed hex-digit field offsets within the frame: `TYPE` (chunk-specific; `1` = "USB-connected Grid module," the only value this parser cares about — `0`/other values are different heartbeat purposes DragonMIDI doesn't need), `HWCFG` (the module's hardware-configuration ID), and the frame's `BRC` header carries `SX`/`SY`/`ROT`/`PORTROT` (the module's position/rotation, already corrected for mounting rotation by the firmware before transmission — see `grid_sys_set_module_absolute_position()`).

**Scope: only what DragonMIDI needs.** `VMAJOR`/`VMINOR`/`VPATCH` (firmware version), `PORTSTATE`, `GCCOUNT`, and every non-heartbeat frame type (Lua scripting, LED/display control, configuration read/write) are not parsed at all — the parser recognizes a frame as "a `TYPE=1` heartbeat" or "something else," and for "something else" extracts nothing and returns nothing. This is the same "normalize what we use, ignore the rest" posture `midi_input.py`'s `normalize_raw()` already takes toward MIDI message types DragonMIDI's mapping never consumes (`pitchbend`/`program`/`aftertouch`/`polytouch` are normalized but never dispatched against).

- **`GridHeartbeat`** (frozen dataclass): `hwcfg: int`, `x: int`, `y: int`, `rotation: int`, `port_rotation: int`. Produced only for `TYPE=1` frames; every other recognized-but-irrelevant frame type, and every frame that fails to parse, produces nothing.
- **Frame boundary handling**: a small accumulator state machine — `WAITING_FOR_SOH` → (byte-by-byte) → `ACCUMULATING` (buffering until `EOB`) → attempt-parse → back to `WAITING_FOR_SOH`. On any failure (an `EOB` with no preceding `SOH`, a buffer that grows past a sane maximum frame length with no `EOB` seen, a frame whose fields don't parse as the expected hex digits) the accumulator discards its buffer and returns to `WAITING_FOR_SOH` — it never raises, matching the Grid CDC Transport's "never crash on malformed input" posture already established for raw MIDI (`normalize_raw()` returns `None`, never raises, for anything it doesn't recognize).
- **Provenance**: the field *offsets* and frame *delimiters* are protocol facts, independently reimplemented in Python from the documented structure (not ported C). See Licensing/Provenance below.

## 3. Runtime Topology Model

- **`GridModule`** (frozen dataclass): `hwcfg: int`, `module_type: ModuleType | None` (`None` for an unrecognized `hwcfg` — see Module Definitions below), `x: int`, `y: int`, `rotation: int`.
- **`GridTopology`** (frozen dataclass): `modules: tuple[GridModule, ...]`.
- **Module-type derivation**: `module_type_from_hwcfg(hwcfg: int) -> ModuleType | None`, a plain dict lookup against the exact source-verified table (Module Definitions below). An unrecognized `hwcfg` doesn't fail topology construction — that module is simply excluded from the topology's recognized-module list (its heartbeat is still seen and tracked internally for the "is this slot occupied" question, but it contributes no logical controls and is skipped during normalization).
- **Snapshot assembly**: there is no stable per-module serial number in the heartbeat payload — a module's identity *is* its `(x, y)` position, since no two modules can occupy the same slot. A `GridTopologyBuilder` accumulates the most recent heartbeat per `(x, y)` slot and drops a slot whose heartbeat hasn't refreshed within Grid's own disconnect timeout (500ms, source: `GRID_PARAMETER_UART_DISCONNECTTIMEOUT_us`, `grid_protocol_bot.json`) — reusing Grid's own liveness constant rather than inventing a new one.
- **"Topology is ready" (settling)**: Phase 1 does not treat the very first heartbeat as sufficient — a chain of N modules reports N independent heartbeats roughly every 250ms (`GRID_PARAMETER_HEARTBEATINTERVAL_us`), not synchronously, so the builder waits for a short settle window (proposed: 2 × heartbeat interval, 500ms, with no new slot appearing or disappearing) before considering the current module set final and handing a `GridTopology` snapshot upstream. This is the same kind of tunable timing constant `docs/llds/midi-input.md`'s discovery-poll interval already is — not load-bearing on correctness, just on how quickly Phase 1 considers topology "settled."
- **USB-root normalization — the core correctness rule this LLD exists to satisfy**: `x`/`y` are *absolute* coordinates relative to whichever module is plugged into the USB host port (that module is always `(0, 0)`) — replugging the chain from a different end shifts every module's absolute `x` by a constant offset, without changing the physical left-to-right arrangement at all. **DragonMIDI never treats absolute `x` as identity.** `normalize_linear_order(modules: Sequence[GridModule]) -> tuple[GridModule, ...]` sorts strictly by `x` ascending and the result's *position in that sorted sequence* — not the `x` value itself — is what every downstream numbering rule (Module Definitions, MIDI resolution) is built from. Two topologies differing only by a constant offset to every module's `x` produce an identical `normalize_linear_order()` result.
- **Phase 1 assumes a single row** (`y` constant across all modules, which holds for any chain plugged in purely horizontally, since only the host module's position is guaranteed `(0,0)` and a horizontal chain never deviates in `y`). A module reporting a different `y` than the rest is a 2-D layout, out of scope (Non-Goals) — Phase 1 does not attempt to interpret it; see Decisions & Alternatives for the chosen failure mode.

## 4. Module Definitions

Module definitions are **templates**, not Controller Profiles — never user-selectable, only composed at runtime from whatever `module_type_from_hwcfg()` resolves.

- **`GridElement`** (frozen dataclass): `index: int` (the element's 0-based index within its module, exactly as Intech's own firmware numbers it), `role: str` (`"fader"`, `"potentiometer"`, `"button"`, `"endless"`, or `"lcd"`).
- **`GridModuleDefinition`** (frozen dataclass): `name: str`, `hwcfg_values: frozenset[int]`, `elements: tuple[GridElement, ...]`.

**`PBF4_DEFINITION`** (source: `grid-protocol/src/grid-protocol.ts` `moduleElements[ModuleType.PBF4]`, independently reimplemented — see Licensing/Provenance):

```text
hwcfg_values = {64, 65, 67, 75}   # PBF4 RevA/RevD/RevH/CD_RevH

index 0-3   role="potentiometer"
index 4-7   role="fader"
index 8-11  role="button"
# index 255 ("system") is not a real I/O control and is not part of this definition
```

**`VSN1_DEFINITION`** (source: `grid-protocol/src/grid-protocol.ts` `moduleElements[ModuleType.VSN1L / VSN1R]`, identical for both — independently reimplemented):

```text
hwcfg_values = {49, 81, 57, 89, 59, 91}   # VSN1L/VSN1R x RevA/RevB/RevH

index 0-7    role="button"
index 8      role="endless"
index 9-12   role="button"
index 13     role="lcd"
# index 255 ("system") is not part of this definition
```

**`VSN1L`/`VSN1R` collapse to one definition.** Per the task's own instruction and the element tables above (identical regardless of which side the LCD sits on), Phase 1 has no reason to distinguish them — both hardware IDs resolve to the same `VSN1_DEFINITION` via `module_type_from_hwcfg()`.

**`role="lcd"` is recorded but produces no logical control in Phase 1** (Non-Goals: no display output). It's kept in the definition for completeness and because a future phase giving VSN1 output capability shouldn't need to re-derive the element table from source again.

`MODULE_DEFINITIONS = (PBF4_DEFINITION, VSN1_DEFINITION)`. An `hwcfg` matching neither is `module_type_from_hwcfg()`'s `None` case (Runtime Topology Model, above) — not an error, just an unrecognized module contributing nothing.

## 5. Active Grid Controller

**The problem this section solves**: `MappingEngine`, `preset_store.load_group_axis_targets()`, and `mapping_view_model.py`'s row builders all currently take or read a `ControllerProfile` — a concrete, frozen dataclass whose fields (`has_native_mode`, `opinionated_map`, `bank_fader_keys`, `websocket_keys`, …) are populated once from a YAML file at load time. Grid has no YAML file and no load time in that sense — its shape is whatever `GridTopology` says *right now*. The task's own constraint rules out the shortcut of calling `build_profile()` with a synthesized `ControlsConfig` to produce a real `ControllerProfile` instance: a `ControllerProfile` is conceptually "a fixed fact about one device declared in a file," and Grid's shape is neither fixed nor file-declared, so manufacturing one — even though it would type-check today — would be an honesty problem in the codebase, not just an engineering shortcut.

**The resolution: a structural `ActiveController` shape, not a shared base class.** `MappingEngine`/`preset_store`/`mapping_view_model` each already read only a *subset* of `ControllerProfile`'s fields; `ControllerProfile` already happens to satisfy that subset's shape today, with zero changes required to it. Introducing a `typing.Protocol` naming that subset lets a second, independent class satisfy the same shape without either class knowing about the other:

```text
class ActiveController(Protocol):
    name: str
    default_channel: int
    bank_count: int
    bank_fader_keys: tuple[_Key, ...]
    fader_keys: frozenset[_Key]
    knob_to_fader: Mapping[_Key, _Key]
    mute_to_fader: Mapping[_Key, _Key]
    fader_to_knob: Mapping[_Key, _Key]
    opinionated_map: Mapping[_Key, _MapEntry]
    control_names: Mapping[_Key, str]
    websocket_keys: WebSocketKeys | None
    group_keys: GroupKeys | None
    has_jog_wheel: bool
    has_scene_button: bool
    def bank_fader_key(self, key: _Key) -> _Key | None: ...
```

`ControllerProfile` satisfies this today, unmodified. **`GridRuntimeController`** (a plain class, not a frozen dataclass — its fields are derived from a live `GridTopology`, not fixed at construction) satisfies it by construction, built as follows:

1. Normalize the current `GridTopology` (§3) into left-to-right module order.
2. Walk the ordered modules' elements per their `GridModuleDefinition`, assigning each `role="fader"` element the next `grid_fader` logical index (PBF4 only contributes faders to this count — its own potentiometers/buttons are numbered in separate, independent sequences, never mixed into fader numbering); similarly for `potentiometer`/`button` roles across PBF4 modules, and for VSN1's `button`/`endless` roles (VSN1 numbering is *not* reset or affected by its position — Phase 1 assumes exactly one VSN1, so there is nothing to disambiguate).
3. Reuse the *existing*, profile-agnostic entry-builder helpers already in `mapping.py` (`build_bank_membership()`, `build_control_names()`) by handing them a synthetic `ControlsConfig`-shaped input whose "CC numbers" are actually the stable logical indices from step 2 — this is the one small, explicitly-deferred generalization this LLD calls for (see Decisions & Alternatives): today `_fader_entries()`/`_knob_entries()`/`_mute_entries()` hardcode the key tag `"cc"`; Phase 2 implementation parameterizes that tag so the exact same formula/derivation code produces `("grid_fader", N)`-tagged entries instead of `("cc", N)`-tagged ones, with **zero duplication** of the Bank-pairing or encoder-offset arithmetic `static-mapping.md` already specifies.
4. `opinionated_map` is populated for `grid_fader` entries only, exactly the way a Korg fader's default OSC-encoder target is built (`/dragonframe/encoder/{N}`) — PBF4 pots/buttons and VSN1 buttons/jog get a `control_names` entry (so they're nameable/visible) but no `opinionated_map` entry yet, matching "logical identity now, default action later" (see Logical Control Identity below).
5. `default_channel = 0` — see MIDI → Module/Element Resolution below for why this is always true under Phase 1's single-row assumption, not an arbitrary choice.
6. `has_native_mode = False`, `has_jog_wheel = False`, `has_scene_button = False` — none of these Korg-specific behaviors exist on Grid hardware.

**This is not implemented in this task** — the `ActiveController` Protocol and `GridRuntimeController`'s construction are described here as the Phase 2 implementation target; `MappingEngine.__init__`/`set_profile()` and the `preset_store`/`mapping_view_model` call sites continue to type-hint against `ControllerProfile` concretely until that retyping lands (a small, mechanical change once this shape is agreed — Python's duck typing means nothing *breaks* by introducing `GridRuntimeController` before the retype, only the type-checker's precision is temporarily looser).

## 6. MIDI → Module/Element Resolution

**The formula** (source: `grid-fw/common/src/lua/simplemidi.lua`, cross-confirmed against Intech's own docs — see `docs/high-level-design.md § References`):

```text
channel          = (moduleY * 4 + currentPage) % 16
cc_or_note_number = (32 + moduleX * 16 + elementIndex) % 128
command           = Note On   if the element's role is "button"
                     Control Change   otherwise
```

`moduleX`/`moduleY` here are the module's *absolute* topology coordinates (§3) — not its normalized left-to-right rank — because this is Grid's own firmware-side formula, computed before DragonMIDI ever sees the data; DragonMIDI only *inverts* it, it doesn't reproduce the forward computation.

**Phase 1 simplifying consequence**: since Phase 1 assumes a single horizontal row and the host module is always `(0, 0)`, every module's `moduleY = 0`. With `currentPage` also fixed at Grid's default page `0` (custom pages are out of scope — Non-Goals), the formula collapses to `channel = 0` for every element on every module, unconditionally. **This is why `GridRuntimeController.default_channel = 0` isn't a guess** — it's the one value Phase 1's own stated assumptions make inevitable. An incoming event on any other channel cannot be explained by a supported Phase-1 arrangement (it implies a 2-D layout or a non-default page) and is simply not matched by anything in the address table below — DragonMIDI does not attempt to interpret it.

**Resolution is a precomputed reverse lookup, not a per-event formula inversion.** Whenever a `GridTopology` settles (§3) and `GridRuntimeController` is (re)built, it also builds:

```text
address_table: dict[_Key, (GridModule, GridElement)]
```

by running the *forward* formula once per element of every recognized module currently in the topology — for element `e` of module `m`: `key = ("cc" if e.role != "button" else "note", (32 + m.x * 16 + e.index) % 128)` on channel `0` — and recording the result. Per-event resolution is then a single dict lookup against this table, the same O(1) dispatch shape `MappingEngine.process()`'s own `opinionated_map` lookup already is; there is no per-event scan or formula re-evaluation.

**Modulo collisions.** `% 128` can in principle let two different (module, element) pairs compute the same raw number if `moduleX` is large enough to wrap — for Phase 1's small chains (a handful of modules, each with at most 12 elements) this is not expected to occur in practice, but the policy is explicit rather than silently assumed: if two elements compute an identical `(channel, type, number)` key while building `address_table`, the second one encountered overwrites the first, with a logged warning — the same "duplicate match: log and take one, don't fail" tolerance `docs/llds/midi-input.md § Device Discovery` already applies to duplicate MIDI port names.

**No topology, no interpretation.** Before a `GridTopology` has settled at least once, `address_table` is empty (or does not exist yet) and *every* raw Grid MIDI event resolves to nothing — DragonMIDI never guesses a module/element from an incomplete or absent topology. This is the same "fail closed, not loud" posture `normalize_raw()` already takes toward unrecognized MIDI message types.

**Factory defaults only.** This formula describes Grid's *default* ("MIDI Auto") addressing. A module whose MIDI Auto settings have been edited in Grid Editor, or that has a custom Package loaded, no longer matches this formula — out of scope (Non-Goals), and not detected; such a module's events simply fail to resolve (same "no topology" outcome above), rather than DragonMIDI misinterpreting them as a different control.

## 7. Logical Control Identity

Grid's logical controls are expressed as ordinary `_Key` tuples (`mapping.py`'s existing `tuple[str, int | None]`) — **the same type `MappingEngine.process()` already dispatches on**, with Grid-specific type tags whose second element is a **stable logical index**, never a raw CC/note number:

```text
("grid_fader", N)         # N = 1..bank_count, left-to-right across all PBF4 modules
("grid_pbf4_pot", N)       # left-to-right across all PBF4 modules, independent of fader numbering
("grid_pbf4_button", N)    # left-to-right across all PBF4 modules
("grid_vsn1_button", N)    # N = 1..12, by VSN1's own element-index order (0-7, then 9-12)
("grid_vsn1_jog", None)
```

(`grid_`-prefixed, rather than the bare `"fader"`/`"pot"` the task sketches conceptually, purely to make the namespace boundary explicit at a glance — nothing in Korg's own key space, which is always `("cc", N)`/`("note", N)`, would actually collide with an unprefixed tag either, but a reader scanning a key should be able to tell "this came from Grid's normalizer" without cross-referencing which controller is active.)

**How a raw Grid MIDI event becomes one of these**: the Grid normalizer (part of `GridRuntimeController`) takes the already-normalized `MidiEvent` that `midi_input.py`'s existing `normalize_raw()` produced from the real `mido` message (unchanged — Grid's wire format is ordinary CC/Note, nothing about *that* step is Grid-specific), looks up `(event.type, event.number)` in `address_table` (§6), and if found, returns a **new** `MidiEvent` with `type`/`number` *rewritten* to the resolved logical key's tag/index while `channel`, `raw_value`, `normalized`, `is_press`, `is_release` pass through unchanged — those fields describe the physical gesture (how far a fader moved, whether a button is down), which topology and addressing have no bearing on. **This rewritten event is handed to `MappingEngine.process()` completely unchanged from how any other controller's event reaches it** — this is the entire "Grid-specific behavior ends at normalization" claim the HLD makes, made concrete: there is no second code path into the Mapping Engine, only a different *source* for the same `MidiEvent` shape.

**Raw CC/note numbers are never a logical control's permanent identity.** `address_table` is rebuilt from scratch every time topology settles; the same `("grid_fader", 3)` key can point at a different raw `(channel, type, number)` triple before and after a rearrangement, while remaining the exact same key the Mapping Engine, Preset Store, and Mapping View all see.

## 8. Controller-Defined `bank_count`

`bank_count` reaches every consumer that already reads it from `ControllerProfile.bank_count` (`MappingEngine`'s Solo formula, `preset_store`'s load/save calls, `mapping_view_model`'s row builders) through the `ActiveController` Protocol (§5) — none of those call sites need a Grid-specific branch; they need only be retyped (Phase 2, not this task) from the concrete `ControllerProfile` to the structural `ActiveController`. `GridRuntimeController.bank_count` is simply `len(bank_fader_keys)`, computed fresh every time topology settles — the identical derivation `ControllerProfile.bank_count` already uses, just fed from a different source.

**`app.py`'s own consumption needs no new mechanism, only confirmation of which string to match.** Today it calls `profile.matches(port_name)` to auto-connect-by-MIDI-port-name within a selected profile — `matches()` fuzzy-normalizes (strip non-alphanumeric, lowercase) and checks for a substring. Grid's MIDI interface has its own USB descriptor string, confirmed from source (`grid-fw/common/src/c/grid_usb.c`'s `s_str_table`): **`"Intech Grid MIDI"`**, distinct from the device's bare product string (`"Grid"`) or the CDC interface's own string (`"Intech Grid CDC"`, §1). Normalized the same way `ControllerProfile.matches()` already normalizes, that gives a `match_substring` of `"intechgridmidi"` — so `GridRuntimeController` can expose a `matches(port_name: str) -> bool` method with the identical fuzzy-match behavior `ControllerProfile.matches()` already has (sharing its normalization helper rather than reimplementing it), and `MidiInputAdapter`'s *existing* `poll_discovery()`/`connect()` path (`docs/llds/midi-input.md § Device Discovery and Auto-Connect`) opens Grid's MIDI port exactly the way it opens any other controller's — no new discovery mechanism for the MIDI side at all. Only the CDC/topology side (§1) needs a second, independent discovery mechanism, since Korg controllers have no analog to it.

## 9. Initialization Lifecycle

1. User selects "Intech Grid" from the Controller Profile dropdown.
2. Grid CDC Transport (§1) begins polling for a VID/PID-matching serial port; on match, opens it at 2,000,000 baud.
3. Raw bytes stream into the Grid Frame Parser (§2); recognized `TYPE=1` heartbeats feed the `GridTopologyBuilder` (§3).
4. The builder waits for its settle window (proposed 500ms of a stable module set) before considering topology ready. Before this point, the UI shows the same "Waiting for …" state `midi-input.md` already defines for any controller with no connected device yet.
5. Once settled: unsupported `hwcfg` values are dropped (logged); the remaining modules are normalized into left-to-right order (§3).
6. `GridRuntimeController` is constructed from the normalized topology and `MODULE_DEFINITIONS` (§4, §5): logical controls are enumerated, `bank_count` is fixed for this topology snapshot, `address_table` (§6) is built, `opinionated_map`/`control_names`/Bank-membership fields are derived via the existing entry-builder helpers.
7. `app.py`'s composition root hands the resulting `ActiveController` to `MappingEngine` and to the Mapping View/Configuration Dialog's row builders — the exact same wiring call sites already use for a freshly-selected `ControllerProfile`, since both satisfy the same shape (§5).
8. The ordinary `MidiInputAdapter`/MIDI backend opens Grid's USB-MIDI port and begins delivering raw events; each passes through the Grid normalizer (§7, resolving against `address_table`) before reaching `MappingEngine.process()` — from here, event handling is indistinguishable from any other controller's.
9. The Preset Store loads `"Intech Grid"`'s persisted (Bank, Group) table (§ Persistence below), bounded by this session's `bank_count`, exactly as it does for any profile switch.

## 10. Topology Change Policy (Phase 1: Stale, Not Live)

Phase 1 does not attempt to keep a running session's `GridRuntimeController`/Mapping View correct against a structural change mid-session. The explicit policy, for every case the task calls out:

| Event | Phase 1 behavior |
|---|---|
| Module added while running | New heartbeat slot detected; **not** incorporated into the live `GridRuntimeController`. The running session continues reflecting the topology it was built from. |
| Module removed while running | That module's heartbeat slot times out (500ms); **not** removed from the live controller. Its elements simply stop producing MIDI (the module is gone), which looks identical to "nothing moved," not a crash or a stale/wrong resolution. |
| USB root moved (replugged from a different end) | Absolute coordinates shift; **not** re-normalized live. Normalization (§3) is only applied at (re)build time. |
| Module order physically changed | Same as above — not re-normalized live. |

**The supported way to pick up any of the above is to reselect "Intech Grid" from the Controller Profile dropdown** (switch away and back, or simply re-trigger the existing profile-switch handler), which re-runs the full Initialization Lifecycle (§9) from a fresh topology settle. This reuses the *existing* Controller-Profile-switch mechanism (`MappingEngine.set_profile()`, `MidiInputAdapter.set_profile()`, `docs/llds/midi-input.md § Controller Profiles`'s "switching disconnects and re-polls") verbatim — no new UI affordance is required for the mechanism to work, only (optionally) a signal telling the user *that* a reselect would help (see Open Questions).

## 11. UI Implications (No Redesign)

- "Intech Grid" is one more entry in the existing Controller Profile dropdown (`docs/llds/app-ui.md`) — no new dropdown, no per-module sub-selection.
- The Mapping View's fader-row count already derives from `profile.bank_fader_keys` (confirmed generic during the `bank_count` refactor that preceded this LLD) — Grid's `bank_count` flows through unchanged; a PBF4-only chain shows 4 rows, a `PBF4 | VSN1 | PBF4` chain shows 8, with no Mapping View code change.
- **No dynamic rebuild guarantee**: per the Stale Topology Policy (§10), the Mapping View does not promise to reflect a structural change that happens while Grid is already the active, connected controller — only a reselect rebuilds it. This is the same `app-ui.md`'s already-documented "Mapping View is build-once, refresh-content-only" gap (Open Questions, `docs/llds/app-ui.md`), now explicitly relevant to Grid rather than only a hypothetical.
- Group switching (Track ◄/►, 5 Groups, `docs/llds/static-mapping.md § Group Switching`) operates on Grid's `bank_count` exactly as it does for any profile — no Grid-specific Group code. **Accepted Phase-1 limitation**: neither PBF4 nor VSN1 has an element wired to Group switching (`group_keys = GroupKeys(previous=None, next=None)` for `GridRuntimeController`), so a Grid session is effectively pinned to Group 1 until a future phase wires a control to it.

## 12. Persistence

**No Preset Store schema or code change is required.** `preset_store.py` already persists the (Bank, Group) axis-assignment table keyed by **profile name + positional Bank index + Group index** — never by raw CC (confirmed during the `bank_count` refactor, which also made the load path's Bank-index ceiling a caller-supplied `bank_count` rather than a hardcoded `8`). Both of this task's stated goals fall out of that existing design for free:

- **Survives a USB-root change or module rearrangement** that preserves the same logical control set: Bank N already means "the Nth `grid_fader`, left-to-right" (§3, §7), which is exactly the quantity normalization keeps stable — the persisted file needs no awareness that anything physical changed.
- **A missing logical control** (the saved table has an entry for a Bank index beyond the currently-connected chain's `bank_count` — e.g. a PBF4 was removed) is already handled: `load_group_axis_targets()`'s existing bounds check against the caller-supplied `bank_count` skips any out-of-range entry with a logged warning, exactly as it already does for a hand-edited or stale file today. No Grid-specific handling needed.

**One fixed requirement this LLD does add**: `GridRuntimeController`'s profile-name-equivalent used to key its preset file must be a **constant** (`"Intech Grid"`), never something derived from the current topology — keying on anything topology-dependent would silently fragment one chain's saved mappings across multiple files as it's rearranged, defeating the entire point of normalization.

**Accepted, matches existing precedent**: if a rearrangement changes *which physical fader* is "3rd from the left" while keeping the same total count, the persisted Bank-3 assignment now applies to a different physical fader than before. This is not a new gap — Bank N has always meant "the Nth positional slot," never "this exact physical control," for the Korg profiles too (`MAP-CONFIG-008`). Grid inherits the identical trade-off, not a worse one.

**Nothing new to persist for PBF4 pots/buttons or VSN1 buttons/jog in Phase 1** — they have no `opinionated_map` entry and no Mapping View row yet (§5, §11), so there is no user-editable target for them to lose or need to persist.

## 13. Licensing / Provenance

DragonMIDI is GPL-3.0-or-later. `grid-protocol`, `grid-editor`, and `grid-fw` are **GPL-3.0-only** (plain FSF template, no "or later" grant, no SPDX markers — confirmed by direct inspection of all three repos' `LICENSE` files).

**What this LLD describes is fact-level reimplementation, not code adaptation**: the HWCFG table (§4), the element index tables (§4), the frame field offsets (§2), and the MIDI Auto addressing formula (§6) are *protocol facts* — observable, documented behavior of the hardware/firmware — reimplemented independently in original Python from those facts, not ported from Intech's C, TypeScript, or Lua source. No source lines from any of the three repositories are copied into this LLD or are intended to be copied into DragonMIDI's implementation.

**Why this matters for licensing**: a clean-room reimplementation of a documented fact (a lookup table of integers, a two-line arithmetic formula, a byte-offset layout) does not carry Intech's copyright into DragonMIDI, so DragonMIDI's own GPL-3.0-or-later terms are unaffected. This is different from *directly adapting* Intech source — if a future implementation detail turns out to need that (not currently anticipated for anything in this LLD), the adapted file would need `SPDX-License-Identifier: GPL-3.0-only` and the combined distributed work would be constrained to GPL-3.0 terms (not "-or-later") for as long as that adaptation remains, per ordinary GPL combination rules — a cost worth naming now so Phase 2 implementation treats "should I just port this function" as a real licensing question, not only a convenience one.

**Attribution**: Phase 2 implementation should carry a short provenance comment at each fact-table/formula site (module definitions, the frame parser, the resolution formula) citing the specific upstream repository and file the fact was confirmed against — the same treatment `docs/high-level-design.md § References` already gives this research at the HLD level, pushed down to the code that actually encodes each fact.

## Non-Goals (Phase 1)

Restates `docs/high-level-design.md`'s Non-Goals for this phase, scoped to this LLD's territory — not restated per-section above:

- Arbitrary 2-D layouts; a second VSN1's identity; custom Grid pages; edited MIDI Auto mappings or Grid Editor Packages; a Grid-side WebSocket bridge; LED or LCD output; writing to Grid's own configuration; pressure/velocity-sensitive button data; any module beyond PBF4/VSN1; user-authored Grid module definitions; a guaranteed live structural rebuild on hot-plug/rearrangement; any Mapping UI redesign; a direct-to-OSC Grid path.

## Test Strategy

No hardware required — every test below drives the parser/topology/resolution layers from fixture byte sequences or fabricated `GridHeartbeat`/`GridTopology` values, the same "fake backend, real logic" pattern `test_midi_input.py` already uses for MIDI.

| # | Scenario | Layer exercised | Proposed home |
|---|---|---|---|
| 1 | `PBF4 \| VSN1 \| PBF4` → 8 `grid_fader` entries | Module Definitions + Active Grid Controller | `test_grid_controller.py` |
| 2 | `PBF4 \| PBF4 \| PBF4` → 12 `grid_fader` entries | same | `test_grid_controller.py` |
| 3 | Shifting every module's absolute `x` by a constant (USB-root change) produces an identical `normalize_linear_order()` result | Runtime Topology Model | `test_grid_topology.py` |
| 4 | VSN1 at left/middle/right position all produce the same `("grid_vsn1_button", N)`/`("grid_vsn1_jog", None)` keys | Active Grid Controller | `test_grid_controller.py` |
| 5 | PBF4 fader numbering skips over an interposed VSN1 without a gap or reset | Active Grid Controller | `test_grid_controller.py` |
| 6 | PBF4 pots/buttons numbered left-to-right across modules, independent of fader numbering | Active Grid Controller | `test_grid_controller.py` |
| 7 | The same physical control's raw MIDI, generated at two different module `x` positions, resolves to the same logical key after topology normalization | MIDI → Module/Element Resolution | `test_grid_resolution.py` |
| 8 | An unrecognized `hwcfg` is dropped, not a crash, and contributes no logical controls | Module Definitions / Runtime Topology Model | `test_grid_topology.py` |
| 9 | Truncated/malformed/missing-`EOB` byte sequences are discarded safely, parser resyncs on the next `SOH` | Grid Frame / Heartbeat Parser | `test_grid_protocol.py` |
| 10 | No settled topology yet → every raw Grid MIDI event resolves to nothing (no guessing) | MIDI → Module/Element Resolution | `test_grid_resolution.py` |
| 11 | Existing nanoKONTROL Studio/2 behavior is unchanged | Regression gate | full existing suite, re-run as-is |
| 12 | Existing Preset Store behavior/schema is unchanged for non-Grid profiles | Regression gate | `test_preset_store.py`, unchanged |
| 13 | A synthetic `GridRuntimeController`-shaped object with `bank_count=12` drives Group/Bank math (Solo offset, axis-target bounds) identically to a 12-bank `ControllerProfile` | `ActiveController` shape conformance | `test_grid_controller.py`, exercising the already-generalized `MappingEngine`/`preset_store` code paths from the prior refactor |
| 14 | Each Topology Change Policy row (§10): a mid-session module add/remove/root-move/reorder does not alter the live controller until a reselect | Topology Change Policy | `test_grid_lifecycle.py` |

**Fixtures proposed**: a `FakeGridTransport` (scripted byte chunks, mirroring the existing fake `MidiBackend` test double), a raw-heartbeat-frame builder helper (encodes a `GridHeartbeat`'s fields into the real SOH/EOB wire format, for parser round-trip tests), and a `fake_topology(modules: list[tuple[hwcfg, x, y, rotation]]) -> GridTopology` builder for every test that doesn't need to exercise the parser itself.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Grid's "controller" shape | A structural `ActiveController` Protocol both `ControllerProfile` and `GridRuntimeController` satisfy | Fabricate a real `ControllerProfile` via `build_profile()`; add Grid-specific `if`-branches throughout `MappingEngine`/`preset_store` | The task explicitly rules out the first (a `ControllerProfile` is a *static, file-declared* fact, which Grid's shape isn't); the second repeats the exact mistake Controller Profiles were introduced to avoid for Korg devices |
| Logical control identity | `_Key`-shaped tuples with `grid_`-prefixed type tags and a stable logical index | A new `LogicalControl` dataclass, migrating `MappingEngine`'s internals off `_Key` entirely | `_Key` is already generic (`tuple[str, int \| None]`, nothing CC-specific baked in); reusing it exactly lets Grid enter `MappingEngine.process()` with *zero* changes to that method, versus a dataclass migration touching Korg's path too for no Phase-1 benefit |
| Entry-builder reuse | Parameterize `_fader_entries()`/`_knob_entries()`/`_mute_entries()`'s hardcoded `"cc"` key tag (Phase 2 implementation) | Duplicate equivalent builders inside a Grid-specific module | Avoids re-deriving the encoder-offset/Bank-pairing arithmetic a second time; the formula is already profile-agnostic, only the literal string `"cc"` is hardcoded |
| Topology discovery channel | USB-CDC serial, opened directly by DragonMIDI (`pyserial`) | Require Grid Editor running and talk to it via some IPC; parse topology out of MIDI sysex | Source-confirmed that no proprietary handshake exists and a standalone client can open the same port Grid Editor does; MIDI carries no topology data in Grid's default behavior at all |
| Module identity within a topology snapshot | `(x, y)` position (no two modules share a slot) | A stable per-module serial number | No serial number field was found in the heartbeat payload; position-as-identity is sufficient since Phase 1 only needs "what's connected right now," not "track this exact module across a rearrangement" |
| USB-root coordinate handling | Sort by absolute `x`, re-index by rank — never use absolute `x` as identity | Require the user to always plug in from a fixed end | The whole point of normalization is that the user *shouldn't* have to care which end is plugged in; a requirement like this would be a UX regression hiding behind a design shortcut |
| Topology settle window | A short fixed delay (proposed 500ms) with no new/changed module, before treating topology as ready | Act on the very first heartbeat seen | A chain's modules report independently roughly every 250ms, not synchronously — acting on the first heartbeat would very likely build a controller missing every module that simply hasn't reported yet |
| 2-D layout detection | A module reporting a different `y` than the rest is simply excluded from normalization (same treatment as an unrecognized `hwcfg`) | Reject/error the whole topology | Matches this codebase's established "accept the rare gap, don't build detection/rejection machinery for an out-of-scope case" pattern (e.g. a nanoKONTROL2 stuck in DAW mode) rather than introducing a new hard failure mode |
| Modulo-collision handling in `address_table` | Log and let the second-built entry win | Treat as a hard topology-construction error | Matches the existing "duplicate matching port: log and take one" tolerance (`docs/llds/midi-input.md`) rather than introducing a new failure mode for an edge case Phase 1's small chains aren't expected to actually hit |
| Topology-change handling mid-session | Stale until a profile reselect; no live rebuild | Live incremental rebuild of the active controller and Mapping View | The task explicitly accepts this as a valid Phase-1 policy; a live rebuild would have to solve UI row-count changes mid-session and in-flight dedup/position state invalidation (`static-mapping.md`'s reconnect-hygiene rules) for a capability nothing in Phase 1 requires |
| Preset Store schema | Unchanged — reuse as-is, keyed by a fixed `"Intech Grid"` name | Version the schema to record topology shape alongside the table | The existing positional-Bank-index design already satisfies both stated persistence goals; adding topology-shape bookkeeping would be speculative machinery for a need that hasn't materialized |
| VSN1L/VSN1R | One shared `VSN1_DEFINITION` | Two distinct definitions with a shared base | Their element tables are identical; two definitions would be two names for the same thing with no behavioral difference to justify the distinction |
| Grid MIDI port discovery | Fuzzy-substring match against the confirmed `"Intech Grid MIDI"` interface string (`match_substring = "intechgridmidi"`), reusing `ControllerProfile.matches()`'s existing normalization | Match via VID/PID only, the same way as the CDC port; require real-hardware verification before deciding | The string is confirmed from source (`grid-fw/common/src/c/grid_usb.c`), not guessed — no reason to fall back to a weaker or unverified mechanism when the exact same pattern every other controller already uses applies directly |

## Open Questions & Future Decisions

### Resolved (this draft)
1. Grid's "controller" shape is a structural `ActiveController` Protocol, not a fabricated `ControllerProfile` — see Active Grid Controller and Decisions & Alternatives above.
2. Logical control identity is `_Key`-shaped with `grid_`-prefixed tags, not a new dataclass — see Logical Control Identity above.
3. Topology changes mid-session are stale-until-reselect, not live-rebuilt — see Topology Change Policy above.
4. Persistence requires no schema change, only a fixed profile-name key — see Persistence above.
5. VSN1L/VSN1R share one module definition — see Module Definitions above.
6. **Grid's USB-MIDI port match pattern.** Confirmed from source, not guessed or hardware-dependent: `grid-fw/common/src/c/grid_usb.c`'s shared USB descriptor string table gives the MIDI streaming interface its own descriptor string, `"Intech Grid MIDI"` (distinct from the device's bare product string `"Grid"` and the CDC interface's own `"Intech Grid CDC"`) — normalized the same way `ControllerProfile.matches()` already normalizes, `match_substring = "intechgridmidi"`. `app.py`'s existing MIDI auto-connect path needs no new mechanism, only this confirmed string — see Controller-Defined `bank_count` above.

### Deferred — need a decision before Phase 2 implementation
1. **Whether a minimal UI signal should mark topology as stale**, pointing the user at "reselect to apply," given this app's established "no log pane" Non-Goal and the Status UI's narrow indicator vocabulary (`docs/llds/app-ui.md`) — a real product decision, not an engineering one.
2. **`GridRuntimeController`'s `setup_hint`** (if any) — e.g. "connect PBF4/VSN1 modules in a single horizontal row" — parallel to the nanoKONTROL2's existing power-on-hold hint. Easy to add, not yet decided whether it's warranted for Phase 1's audience.
3. **Exact topology settle-window duration** (proposed 500ms / 2× heartbeat interval) — a tunable constant, not yet measured against real hardware's actual heartbeat jitter.
4. **Whether/when PBF4 pots/buttons and VSN1 buttons/jog get a default `opinionated_map` entry** — explicitly deferred past Phase 1 by the task itself; this LLD only guarantees they have a stable logical *identity* now, not a *behavior*.
5. **Whether to parameterize `_fader_entries()`/`_knob_entries()`/`_mute_entries()`'s key tag now or have Grid's Phase 2 implementation duplicate a small equivalent** — recommended direction stated in Decisions & Alternatives, not yet implemented or confirmed.
6. **Multiple independent Grid chains connected simultaneously** — not addressed by this LLD at all; Phase 1 implicitly assumes at most one Grid CDC device is ever a match.
7. **Whether the legacy SAMD51 (`d51n20a`) firmware build's different, device-level product string (`"Intech Studio: Grid"`, from `d51n20a/config/usbd_config.h`, with no separate per-interface strings) could still appear on some currently-shipped hardware running older firmware.** The current shared descriptor source (`common/src/c/grid_usb.c`, item 6 above) is what this LLD designs against, consistent with the same source tree the HWCFG/element tables (§4) were confirmed against; this older variant is noted for awareness, not designed around, since nothing indicates it's what current PBF4/VSN1 units ship with.

## References

- `intechstudio/grid-protocol`, `intechstudio/grid-editor`, `intechstudio/grid-fw` (all GPL-3.0-only) — source of every protocol fact cited in this LLD (frame format, HWCFG table, element tables, the MIDI Auto formula, VID/PID allowlist, heartbeat/disconnect timing constants). See Licensing/Provenance above for how this LLD's use of them is scoped.
- `grid-fw/common/src/c/grid_usb.c`'s `s_str_table` — source of the confirmed USB descriptor strings ("Grid" the device, "Intech Grid MIDI" the MIDI interface, "Intech Grid CDC" the CDC interface) behind §1's and §8's port-matching design — resolved from source, not real-hardware verification, per the project's own correction to an earlier draft of this LLD.
- `docs/high-level-design.md § Delivery Phasing` (Phase 7) and `§ Key Design Decisions` — the architectural commitments this LLD elaborates (Grid as one controller, normalization into the existing pipeline, controller-derived `bank_count`).
- `docs/llds/midi-input.md § Device Discovery and Auto-Connect` — the poll/connect/disconnect pattern the Grid CDC Transport (§1) reuses verbatim for a second transport.
- `docs/llds/static-mapping.md § Controller Profile Config Schema`, `§ Bank Derivation` — the `bank_count`-generalized entry-builder helpers (§5, §8) and Bank-index persistence bounds-check (§12) this LLD depends on, completed as a prerequisite refactor before this LLD was drafted.
