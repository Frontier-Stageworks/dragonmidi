# Named Controller Registry — EARS Specs

Traces to `docs/llds/named-controller.md`.

## Data Model and Persistence

- [x] **NAMEDCTRL-DATA-001**: The system shall represent a Named Controller as: a stable `id` (assigned once at creation, never changed), a user-editable `display_name`, a `kind` of `"static"` or `"grid"`, and either a `profile_name` (`kind == "static"`) or a `module_shape` (`kind == "grid"`, an ordered tuple of recognized module-type names).
- [x] **NAMEDCTRL-DATA-002**: The system shall persist each Named Controller as its own file at `~/Documents/DragonMIDI/named_controllers/{id}.json`, creating the folder on first write if it does not exist.
- [x] **NAMEDCTRL-DATA-003**: A Named Controller file that fails to parse shall be skipped with a logged warning when the registry is loaded; it shall not raise and shall not prevent any other file in the folder from loading.
- [x] **NAMEDCTRL-DATA-004**: Renaming a Named Controller (`rename_named_controller`) shall change only its `display_name`; its `id`, `kind`, and `profile_name`/`module_shape` shall be unchanged, and the rename shall be written to the same file (same filename stem) it already occupies.
- [x] **NAMEDCTRL-DATA-005** (Phase 1.4): The system shall represent an `is_builtin` boolean on each Named Controller, defaulting to `False`. It shall be set to `True` only by the creation performed under `NAMEDCTRL-STATIC-001` and the creation performed under `NAMEDCTRL-MIGRATE-001`; no other creation or mutation path, including `rename_named_controller`, shall set it `True`.

## Korg: Static Profile Wrapping

- [x] **NAMEDCTRL-STATIC-001**: The system shall ensure exactly one Named Controller with `id == profile_name` and `kind == "static"` exists for a static Controller Profile the first time that profile is selected, creating it with `display_name = profile_name` if absent; a subsequent selection of the same profile shall return the existing record unchanged, not create a second one.
- [x] **NAMEDCTRL-STATIC-002**: The Preset Store key used for a static Controller Profile shall be exactly `profile_name`, both before and after this feature — `NAMEDCTRL-STATIC-001`'s wrapper shall not change the string passed to `preset_store.load_group_axis_targets()`/`save_group_axis_targets()` for any existing Korg installation.
- [x] **NAMEDCTRL-STATIC-003** (Phase 1.4): WHEN `ensure_static_named_controller` finds an existing record (`NAMEDCTRL-STATIC-001`) whose `is_builtin` is `False`, THE SYSTEM SHALL correct it to `True` and re-persist the record under its existing `id`/filename, with every other field unchanged, before returning it.

## Grid: Shape-Based Matching

- [x] **NAMEDCTRL-MATCH-001**: When a Grid runtime controller is successfully built (a `Ready` outcome), the system shall look up every Named Controller of `kind == "grid"` whose `module_shape` equals the new controller's `module_shape`, after the one-time legacy-migration check (`NAMEDCTRL-MIGRATE-001`) has run.
- [x] **NAMEDCTRL-MATCH-002**: WHEN zero Named Controllers match the settled `module_shape`, THE SYSTEM SHALL create a new Named Controller — a freshly-generated `id` (`NAMEDCTRL-MATCH-005`), `display_name` defaulted to a shape-derived summary (e.g. `"Intech Grid (PBF4+VSN1+PBF4)"`), `kind = "grid"`, and the matched `module_shape` — and activate it immediately, without prompting the user for confirmation or a name.
- [x] **NAMEDCTRL-MATCH-003**: WHEN exactly one Named Controller matches the settled `module_shape`, THE SYSTEM SHALL activate it without prompting the user.
- [x] **NAMEDCTRL-MATCH-004**: WHEN two or more Named Controllers match the settled `module_shape`, THE SYSTEM SHALL NOT activate any of them automatically; it shall report an ambiguous-named-controller outcome, naming every matching candidate, and shall not install any saved (Bank, Group) axis mapping until the user selects one candidate or creates a new Named Controller.
- [x] **NAMEDCTRL-MATCH-005**: A Named Controller created under `NAMEDCTRL-MATCH-002` shall receive an `id` of the form `grid-{n}`, where `n` is one greater than the highest existing numeric suffix among `kind == "grid"` entries whose `id` matches that form — never a count of existing entries, which could collide with a surviving higher-numbered entry after a lower-numbered one was deleted.
- [x] **NAMEDCTRL-MATCH-006**: Two separate settles that each produce the identical `module_shape` as an already-existing Named Controller shall both resolve to that same Named Controller's `id`; a second settle of an already-seen shape shall never create a duplicate entry.

## Legacy Migration

- [x] **NAMEDCTRL-MIGRATE-001**: IF the Named Controller registry contains zero entries of `kind == "grid"` AND a legacy preset file exists at `~/Documents/DragonMIDI/configurations/Intech Grid.json`, THEN THE SYSTEM SHALL create exactly one Named Controller — `id = "Intech Grid"`, `display_name = "Intech Grid"`, `kind = "grid"` — bound to whichever `module_shape` is settled at that moment, before `NAMEDCTRL-MATCH-001`'s ordinary lookup runs.
- [x] **NAMEDCTRL-MIGRATE-002**: `NAMEDCTRL-MIGRATE-001` shall fire at most once per installation; once any `kind == "grid"` Named Controller exists, its precondition shall never hold again, regardless of what `module_shape` is subsequently settled.
- [x] **NAMEDCTRL-MIGRATE-003**: Where no legacy preset file exists (a fresh installation), the system shall not perform `NAMEDCTRL-MIGRATE-001` and shall fall through directly to `NAMEDCTRL-MATCH-002`'s ordinary zero-candidate path.

## Named Configuration: Many Per Hardware Key (Phase 1.4)

- [x] **NAMEDCTRL-CONFIG-001**: More than one Named Controller may share the same `profile_name` (`kind == "static"`) or the same `module_shape` (`kind == "grid"`) as a normal, supported state — hardware-key multiplicity shall not itself be treated as an error condition outside the existing connect-time ambiguity resolution (`NAMEDCTRL-MATCH-004`), whose behavior is unchanged by this section.
- [x] **NAMEDCTRL-CONFIG-002**: `configurations_for_profile(named_controllers_dir, profile_name)` shall return every Named Controller of `kind == "static"` whose `profile_name` equals the given value, ordered by `created_at`.
- [x] **NAMEDCTRL-CONFIG-003**: `configurations_for_grid(named_controllers_dir)` shall return every Named Controller of `kind == "grid"` in the registry, regardless of `module_shape`.
- [x] **NAMEDCTRL-CONFIG-004**: `create_static_named_controller(named_controllers_dir, profile_name, display_name)` shall create and persist a new Named Controller with a fresh `id` from `next_static_sibling_id`, `kind = "static"`, the given `profile_name` and `display_name`, and `is_builtin = False`.
- [x] **NAMEDCTRL-CONFIG-005**: `next_static_sibling_id(named_controllers_dir, profile_name)` shall return `f"{profile_name} ({n})"`, where `n` is one greater than the highest existing numeric suffix among ids matching that exact pattern for the given `profile_name` — never a count of existing entries, for the same reissue-after-deletion reason `NAMEDCTRL-MATCH-005` already states for `next_grid_id`.
- [x] **NAMEDCTRL-CONFIG-006**: `shape_matches_connected_hardware(controller, connected_shape)` shall return `True` if and only if `controller.module_shape` is exactly equal (order-sensitive) to `connected_shape`.

## Ambiguity Resolution (UI-facing outcome; owned here, surfaced per `docs/specs/app-ui.md`)

- [x] **NAMEDCTRL-AMBIG-001**: While an ambiguous-named-controller outcome (`NAMEDCTRL-MATCH-004`) is unresolved, the system shall not install the Grid runtime controller that triggered it into the Mapping Engine or MIDI Input Adapter, and the Status UI shall reflect a distinct "named controller ambiguous" state (`docs/specs/app-ui.md`), never conflated with the pre-existing Grid CDC-ambiguous or address-collision states.
- [x] **NAMEDCTRL-AMBIG-002**: Resolving an ambiguous-named-controller outcome by selecting an existing candidate shall activate that candidate's `id` with no further prompt; resolving it by creating a new Named Controller shall follow `NAMEDCTRL-MATCH-002`'s creation behavior under a user-supplied `display_name` instead of the shape-derived default.

## References

- `docs/llds/named-controller.md` — the LLD these specs trace to; see it for the full rationale and Decisions & Alternatives behind each requirement above.
- `docs/specs/intech-grid.md § GRID-CTRL-*`, `§ GRID-MAP-003` — the `module_shape` source data and the Preset Store keying this segment feeds.
- `docs/specs/static-mapping.md § MAP-STORE-*` — the unchanged Preset Store file format/bounds-checking the resolved `id` is handed to.
- `docs/specs/app-ui.md § UI-NAMEDCTRL-*` — the Qt-facing status text and ambiguity dialog driven by this segment's outcomes.
- `docs/specs/app-ui.md § UI-SAVELOAD-*` (Phase 1.4) — the Qt-facing Save/Save As/Load UI driven by this segment's `NAMEDCTRL-CONFIG-*` additions.
