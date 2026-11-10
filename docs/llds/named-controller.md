# Named Controller Registry

## Context and Design Philosophy

Continues `docs/high-level-design.md`'s Named Controller Registry Key Design Decisions and the "Named Controller Registry" paragraph under System Design. This LLD owns the territory between "a Controller Profile or Grid runtime controller has an identity" and "the Preset Store is given a key to load/save (Bank, Group) axis data under" — it does not own the Preset Store's file format or bounds-checking (`docs/llds/static-mapping.md § Preset Store`, unchanged), the Grid topology/controller construction itself (`docs/llds/intech-grid.md`, which this LLD only reads from), or the dropdown/dialog widgets that call into it (`docs/llds/app-ui.md`).

**The problem this LLD exists to solve.** `ControllerProfile.name` and `GridRuntimeController.name` (`GRID_PROFILE_NAME`, a fixed constant, `"Intech Grid"`) are the two strings the Preset Store has ever been keyed by (`docs/llds/intech-grid.md § Persistence`). For a Korg profile this is correct and sufficient — one physical shape, one name, forever. For Intech Grid it is not: every physical arrangement that normalizes to the same module-type shape resolves to the identical constant name, so a second, unrelated rig silently overwrites the first's saved mapping the moment it is connected, with no warning. Named Controller gives the user a way to say "this arrangement is 'Stewart Platform Controller'" once, and have that chosen identity — not the bare shape, and not a guess — be what the Preset Store actually keys against.

**Three distinct concepts, kept distinct by construction, not by convention alone:**

- **Hardware definition**: a module's or device's physical capabilities — `GridModuleDefinition`/`PBF4_DEFINITION`/`VSN1_DEFINITION` (`docs/llds/intech-grid.md § Module Definitions`) for Grid, a `ControllerProfile`'s declared `controls:` block for Korg. This LLD does not touch either.
- **Named Controller** (this LLD): a particular physical device or Intech Grid module arrangement, identified either by a static Controller Profile's name (Korg) or a settled Grid topology's module-type shape (Grid). A `NamedController` record is the user-facing identity a saved mapping is actually attached to. As of § 8 (Phase 1.4), a hardware identity (`profile_name`/`module_shape`) may have more than one saved `NamedController` — a "Named Configuration" in that section's terms — each independently created via Save As; §§1–7 below describe the original, still-accurate single-match-per-shape *connect-time resolution* behavior, which § 8 extends rather than replaces.
- **Mapping preset**: the (Bank, Group) axis-assignment table + Rotary/Button action overrides a Named Controller's mapping currently holds — unchanged Preset Store territory (`docs/llds/static-mapping.md § Preset Store`). One `NamedController` record still has exactly one current mapping, the same single-file-per-key model the Preset Store already implements — § 8 multiplies how many `NamedController` records a hardware identity may have, not how many mappings one record holds; there is still no per-record mapping history or versioning (§9).

**Accepted consequence of using only *recognized* modules in the shape**: a topology with an unrecognized module inserted between two PBF4s produces the identical `module_shape` as the same two PBF4s with no module between them — matching, not a gap, since an unrecognized module contributes zero logical controls either way (`docs/llds/intech-grid.md § Runtime Topology Model`'s Unsupported-Module Policy); the two arrangements are functionally identical from DragonMIDI's addressable-control perspective, so treating them as the same saved identity is correct, not a loss of precision.

**Governing constraint: no per-physical-module persistent identity exists, so this LLD never claims one.** Grid's heartbeat protocol carries no serial number (`docs/llds/intech-grid.md § Runtime Topology Model`); a module's only identity within a session is its settled `(x, y)` position, already established as non-persistent (it resets on every USB-root change). Named Controller matching is therefore keyed on the coarser, genuinely stable **module-type shape** — the ordered sequence of recognized module types a settled topology normalizes to — never on an individual module's history. This is a conservative, intentionally-coarse matching strategy: it can tell "a PBF4+VSN1+PBF4 chain" apart from "a PBF4+PBF4+PBF4 chain," but it cannot tell two distinct PBF4+VSN1+PBF4 rigs apart from each other. The rest of this LLD is built around never letting that specific blind spot resolve silently.

## 1. Data Model

```text
NamedController (frozen dataclass):
    id: str                          # stable; assigned once at creation; the Preset Store key and registry filename stem
    display_name: str                # user-facing; freely editable; never used as a key
    kind: Literal["static", "grid"]
    profile_name: str | None         # set iff kind == "static"; the ControllerProfile.name this wraps
    module_shape: tuple[str, ...] | None   # set iff kind == "grid"; ordered recognized module-type names, left-to-right
    created_at: str                  # ISO-8601 timestamp, informational only
    is_builtin: bool = False         # Phase 1.4; set once at creation, see § 8; never toggled afterward
```

`id` and `display_name` are deliberately independent fields. Renaming a Named Controller (editing `display_name`) never touches `id`, so it never touches which Preset Store file its mapping lives in — a rename cannot silently detach a saved mapping from its controller. `module_shape` is set once, at creation, from whatever topology triggered the creation (§3); it is never edited by the user and never changes on an existing record — a change to the connected hardware's shape produces a *new* `NamedController` candidate (§3's zero/one/many flow), never a mutation of an old one.

**Persistence**: one JSON file per `NamedController`, at `~/Documents/DragonMIDI/named_controllers/{id}.json`, mirroring the Controller Profile/Preset Store folders' existing one-file-per-name convention. `id` is used verbatim as the filename stem — for Korg this is always a profile name (already filesystem-safe, confirmed by existing Preset Store usage); for Grid-generated ids (§3) the generator is responsible for producing a filesystem-safe string. File I/O lives in `dragonmidi/named_controller_registry.py`, a plain-Python module with no Qt dependency, matching `controller_profile_loader.py`/`preset_store.py`'s existing separation.

```text
def load_registry(named_controllers_dir: Path) -> tuple[NamedController, ...]
def save_named_controller(named_controllers_dir: Path, nc: NamedController) -> None
```

`load_registry` discovers every `*.json` file in the folder (creating it if absent, matching `preset_store.py`'s own first-run behavior) and parses each into a `NamedController`; a file that fails to parse is skipped with a logged warning, not raised — the same "a stale/hand-edited file never blocks the rest" posture `preset_store.py`'s own loader already takes toward a malformed configuration file.

## 2. Korg: Trivial 1:1 Wrapping

```text
def ensure_static_named_controller(named_controllers_dir: Path, profile_name: str) -> NamedController
```

Called once, from the same `app.py` call site that currently installs a freshly-selected static `ControllerProfile` (`docs/llds/intech-grid.md § Application Integration`'s `_install_active_controller()`), immediately before the existing `preset_store.load_group_axis_targets()` call. If a `NamedController` with `id == profile_name` already exists in the registry (the common case after the very first run), it is returned unchanged. Otherwise one is created — `id = profile_name`, `display_name = profile_name`, `kind = "static"`, `profile_name = profile_name`, `module_shape = None` — persisted, and returned.

**This is a transparent wrapper, not a behavior change.** Because `id` is always exactly `profile_name`, the Preset Store key `_install_active_controller()` passes is byte-identical to what it passes today — a Korg user's existing `nanoKONTROL2.json`/`nanoKONTROL Studio.json` configuration files load exactly as before, with no migration step. The only observable effect is that a `NamedController` record now exists for display purposes — nothing about discovery, matching, or persistence for Korg changes. Korg's hardware shape cannot vary, so there is nothing for the zero/one/many matching flow (§3) to ever disambiguate for it; that flow is Grid-only.

**Self-healing `is_builtin` upgrade (Phase 1.4, § 8).** A record shaped `id == profile_name`, `kind == "static"` can only ever have been created by this function — so finding one on a subsequent call with `is_builtin` still `False` (a file written by a pre-Phase-1.4 installation, before that field existed) is corrected to `True` and re-persisted in place, same `id`, same file, every other field untouched. Without this, a user who installed DragonMIDI before Phase 1.4 would keep an unprotected "default" forever, while a fresh Phase 1.4+ install's default is protected from the start — an asymmetry with no good reason to leave standing, since both are the exact same semantic thing.

## 3. Grid: Shape-Based Matching

```text
GridMatchOutcome =
    Activated(controller: NamedController)
  | Ambiguous(candidates: tuple[NamedController, ...])

def resolve_grid_named_controller(
    named_controllers_dir: Path,
    configurations_dir: Path,
    module_shape: tuple[str, ...],
) -> GridMatchOutcome
```

Called every time a `GridTopology` settles and a `GridRuntimeController` is successfully built (`docs/llds/intech-grid.md § Initialization Lifecycle`, step 5's `Ready` outcome) — `module_shape` is that controller's own `module_shape` property (§4 of the Intech Grid LLD revision below). This function never runs for a `static` controller.

1. **One-time legacy migration check** (§5) runs first, but only when the registry currently holds zero `kind="grid"` entries — see §5 for the exact precondition and effect. After it (whether or not it fired), the ordinary matching logic below always runs.
2. `candidates = [nc for nc in load_registry(named_controllers_dir) if nc.kind == "grid" and nc.module_shape == module_shape]`.
3. **Zero candidates** (a shape never seen before, or never saved under): create a new `NamedController` — `id` generated by `next_grid_id(named_controllers_dir)` (§4), `display_name = default_display_name(module_shape)` (§4), `kind = "grid"`, `module_shape = module_shape` — persist it, and return `Activated(controller)`. No prompt, no confirmation step: an unseen shape is not ambiguous, it is simply new, and Grid's existing zero-configuration feel (`docs/high-level-design.md`'s Goals) is preserved by never blocking on it.
4. **Exactly one candidate**: return `Activated(candidate)` — the same zero-friction behavior as Korg's auto-wrap, now for a shape DragonMIDI has already named once.
5. **Two or more candidates**: return `Ambiguous(tuple(candidates))` and create nothing. This is the one case Named Controller matching blocks on — more than one saved arrangement shares this exact module-type shape, and §1's governing constraint means DragonMIDI genuinely cannot tell them apart from topology alone. `docs/llds/app-ui.md`'s ambiguity dialog is the only consumer of this outcome; it is the caller's job to keep the previously-active controller (if any) deactivated and to not install any mapping until the user has picked one of the candidates or explicitly created a new entry (looping back to step 3's zero-candidate path, but now deliberately, under a user-chosen name rather than the generated default).

## 4. Supporting Helpers

```text
def next_grid_id(named_controllers_dir: Path) -> str
```

Returns `f"grid-{n}"` where `n` is one greater than the **highest existing numeric suffix** among `kind == "grid"` entries whose `id` matches `grid-<int>` (not a count of entries — a count would collide if any `grid-N` entry had ever been deleted, e.g. entries `grid-1`/`grid-3` present, `grid-2` deleted: a count of 2 would regenerate the already-taken `grid-3`). Scanning, not a stored counter, consistent with this module having no mutable state of its own beyond the files it reads and writes. Deterministic and test-friendly: a fresh registry's first Grid entry is always `"grid-1"`. A legacy-migration-created `"Intech Grid"` entry (§5) does not match `grid-<int>` and is ignored by this scan, so it never perturbs the numbering.

```text
def default_display_name(module_shape: tuple[str, ...]) -> str
```

Returns `"Intech Grid (" + "+".join(module_shape) + ")"`, e.g. `"Intech Grid (PBF4+VSN1+PBF4)"` — informative enough to recognize at a glance, freely renamable afterward (§6).

```text
def rename_named_controller(named_controllers_dir: Path, id: str, new_display_name: str) -> NamedController
```

Loads the existing record by `id`, replaces only `display_name`, re-persists under the same filename, and returns the updated record. `id`, `kind`, `profile_name`/`module_shape` are immutable after creation — this function cannot change them. If no record with that `id` exists, raises (a programming-error case — the UI never offers to rename a `NamedController` it didn't just read from the registry).

## 5. Legacy Migration

**Precondition**: `resolve_grid_named_controller()` is called, `load_registry(named_controllers_dir)` contains zero entries with `kind == "grid"`, **and** a legacy preset file exists at `configurations_dir / "Intech Grid.json"` (the literal filename `GridRuntimeController.name`'s pre-this-phase constant already produces, per `docs/llds/intech-grid.md § Persistence`).

**Effect**: create and persist exactly one `NamedController` — `id = "Intech Grid"` (reusing the legacy filename stem outright, so the existing preset file is found by the new keying scheme with zero data migration), `display_name = "Intech Grid"`, `kind = "grid"`, `module_shape` set to whatever shape is settled on *this* connection (not any historical shape — none was ever recorded before this phase, so "whatever is connected the first time post-upgrade" is the only available and the semantically correct choice, since it reproduces exactly what the pre-existing constant-key behavior already did for every connection). This runs at most once per installation — after it, the registry holds one `kind="grid"` entry, so the precondition above can never be true again.

**Why this is safe to do unconditionally, not behind a confirmation prompt**: it fires only when there is a legacy file to protect and only before any `NamedController` has ever been created for Grid — by definition, a state only a pre-this-phase installation's first post-upgrade connection can be in. A fresh installation with no legacy file simply falls through to §3's ordinary zero-candidate path (creating `"grid-1"` instead of `"Intech Grid"`), which is equally correct and loses nothing, since there was never a file to protect.

## 6. UI-Facing Surface (owned by `docs/llds/app-ui.md`; summarized here for context)

This LLD exposes exactly three call shapes a Qt layer needs: `ensure_static_named_controller()` (Korg, no UI decision ever required), `resolve_grid_named_controller()` (Grid, returning `Activated` or `Ambiguous`), and `rename_named_controller()` (either kind, invoked from a small rename affordance). `docs/llds/app-ui.md` owns: where the active Named Controller's `display_name` is shown (reusing the existing connection-status text slot, per the same precedent `docs/llds/intech-grid.md § UI Implications` already established for Grid's own five-state status), the ambiguity-resolution dialog shown on `Ambiguous`, and the rename affordance's widget. None of those are this LLD's concern beyond the three call shapes above.

## 7. Interaction with Topology Change Policy

A structural topology change mid-session still marks the active `GridRuntimeController` `STALE` exactly as before (`docs/llds/intech-grid.md § Topology Change Policy`) — this LLD adds no second, independent staleness concept. `resolve_grid_named_controller()` runs again only at the next fresh settle (an explicit controller-profile reselection, per the existing Initialization Lifecycle), never against a `STALE` controller's already-superseded shape. A rearrangement that changes the module-type shape naturally falls through to §3's zero/one/many logic exactly as a first-ever connection of that shape would — there is no separate "shape changed since last time" code path to keep in sync with the ordinary one, because there isn't one; the ordinary one already handles it.

## 8. Named Configuration: Many Per Hardware Key (Phase 1.4)

**The "exactly one `NamedController` per hardware key" assumption (§§1–3) is lifted.** A hardware key — `profile_name` for `kind == "static"`, `module_shape` for `kind == "grid"` — may now be shared by zero or more saved `NamedController` records, each a distinct, independently loadable mapping under its own `id`/Preset Store file. Nothing about §3's automatic zero/one/many *connect-time* resolution changes: it still activates a sole match silently and still blocks on two or more matches, asking the user to choose — multiple saved configurations sharing a shape is now the *expected* result of deliberate Save As use rather than only an accidental collision, but the matching logic that discovers them and the safety posture around never guessing is identical to before this section.

`is_builtin` (§1's new field) is set once, at creation, by exactly two call sites — `ensure_static_named_controller` (§2) and the legacy-migration branch of `resolve_grid_named_controller` (§5) — and never toggled afterward. Every other creation path (`create_grid_named_controller`, and the new `create_static_named_controller` below) defaults it to `False`. `rename_named_controller` (§4) does not touch it.

**New functions:**

```text
def configurations_for_profile(named_controllers_dir: Path, profile_name: str) -> tuple[NamedController, ...]
def configurations_for_grid(named_controllers_dir: Path) -> tuple[NamedController, ...]
def next_static_sibling_id(named_controllers_dir: Path, profile_name: str) -> str
def create_static_named_controller(named_controllers_dir: Path, profile_name: str, display_name: str) -> NamedController
def shape_matches_connected_hardware(controller: NamedController, connected_shape: tuple[str, ...]) -> bool
```

- `configurations_for_profile` returns every `kind == "static"` record whose `profile_name` equals the given one, ordered by `created_at` (the builtin — `id == profile_name` — sorts first by construction, since it is always created before any sibling can exist). Safe to load any of them against the active hardware unconditionally: a Korg profile's physical shape cannot vary, so there is nothing to validate (§1's existing "nothing for the zero/one/many flow to disambiguate" reasoning applies equally here).
- `configurations_for_grid` returns **every** `kind == "grid"` record, regardless of `module_shape` — deliberately not filtered to the currently-connected shape. A saved "Stewart Platform Controller" must remain listable (and renamable) from the Load surface even while a different rig is connected; the caller (`docs/llds/app-ui.md`'s Load dialog) is responsible for checking `shape_matches_connected_hardware` per candidate and disabling selection of a mismatched one, not this function.
- `next_static_sibling_id` returns `f"{profile_name} ({n})"`, where `n` is one greater than the highest existing numeric suffix among ids matching that exact pattern for this `profile_name` — the same "scan the highest suffix, not a count" robustness `next_grid_id` (§4) already uses, so a deleted sibling's number is never silently reissued. Starts at `2`, since the bare `profile_name` (the builtin) is implicitly "configuration 1."
- `create_static_named_controller` is Korg's Save-As counterpart to `create_grid_named_controller` (§4): a fresh `id` from `next_static_sibling_id`, the caller-supplied `display_name`, `kind = "static"`, `profile_name` set, `is_builtin = False` — persisted and returned.
- `shape_matches_connected_hardware` is a pure equality check (`controller.module_shape == connected_shape`) — trivial in logic, given its own name and docstring because `docs/llds/app-ui.md`'s Load dialog and `app.py`'s Load handler both need the identical check and must not drift into two slightly different comparisons written independently. Attempting to load a `kind == "grid"` configuration whose `module_shape` fails this check is refused with a clear message (`docs/llds/app-ui.md § Save/Save As/Load UI`); it is never silently applied onto mismatched topology. Not needed, and not provided, for `kind == "static"` — see `configurations_for_profile` above.

**Builtin-overwrite protection is enforced by the caller, not by a new write-guard in this module.** `save_named_controller` (§1) still writes whatever `NamedController` it is given — it has no concept of "the active one" or "pending edits" to refuse. The protection is architectural, living in `docs/llds/app-ui.md`'s Save handler: Save while `self._active_named_controller.is_builtin` is `True` always routes to the Save-As flow instead of calling the Preset Store's write for that `id`; nothing in `preset_store.py` or this module enforces it a second time.

## 9. Non-Goals (restates `docs/high-level-design.md`'s, scoped to this LLD's territory)

- Per-physical-module persistent identity, or any attempt to approximate one beyond module-type shape (§1's governing constraint).
- Automatic resolution of an `Ambiguous` match (§3) by any heuristic (most-recently-used, alphabetical-first, etc.) — always surfaced to the user, never guessed. Unaffected by §8: the connect-time zero/one/many flow is unchanged.
- Detecting or warning about an intra-shape rearrangement (swapping two same-type modules) — accepted, matches the existing Bank-positional-persistence limitation (`docs/llds/intech-grid.md § Persistence`).
- Deleting a `NamedController` record from this LLD's own API — still out of scope; `docs/llds/app-ui.md` may add a UI-level delete affordance later if needed, calling straight file removal, with no special handling required here.
- Versioning or history of a single saved configuration's prior mappings. §8 allows many *configurations* per hardware key, each with its own `id`/file, but each configuration is still exactly one current mapping, overwritten wholesale by Save — not a sequence of snapshots.
- Copying a saved configuration's mapping onto a different hardware key. `create_static_named_controller`/`create_grid_named_controller` always create a sibling under the *same* `profile_name`/`module_shape` as their caller supplies — neither this module nor `docs/llds/app-ui.md`'s Save As offers to retarget a configuration's mapping to different hardware.

## Test Strategy

No hardware or Qt required — every test below drives `named_controller_registry.py`'s pure functions against a temp directory, the same "fake backend, real logic" pattern `test_preset_store.py`/`test_controller_profile_loader.py` already use.

| # | Scenario | Proposed home |
|---|---|---|
| 1 | `ensure_static_named_controller` creates on first call, returns the same record unchanged on a second call | `test_named_controller_registry.py` |
| 2 | `resolve_grid_named_controller` with an empty registry and no legacy file creates `"grid-1"` with the default shape-derived display name | same |
| 3 | A second, different shape creates `"grid-2"`, independent of `"grid-1"`'s existence | same |
| 4 | The same shape resolved twice returns `Activated` with the identical `id` both times (no duplicate created) | same |
| 5 | Two `NamedController`s saved under the same `module_shape` (simulating two prior sessions' zero-candidate creations under different names) yield `Ambiguous` with both candidates on the next resolve | same |
| 6 | Legacy migration: an empty registry plus an on-disk `Intech Grid.json` preset file creates `id="Intech Grid"` bound to the shape passed in, and this fires at most once (a second `resolve_grid_named_controller` call with a *different* shape does not re-trigger migration, since the registry is no longer empty) | same |
| 7 | `rename_named_controller` changes `display_name` only; `id`, `kind`, `module_shape`/`profile_name` are unchanged, and a subsequent `load_registry` reflects the new name under the same filename | same |
| 8 | A malformed/hand-edited registry file is skipped with a logged warning, not raised, and does not prevent other valid files from loading | same |
| 9 | `ensure_static_named_controller` creates its record with `is_builtin == True`; `create_static_named_controller` creates one with `is_builtin == False` | same |
| 10 | `configurations_for_profile` returns only `kind == "static"` records matching the given `profile_name`, including the builtin, in `created_at` order; a record under a different `profile_name` is excluded | same |
| 11 | `next_static_sibling_id` returns `"{profile_name} (2)"` for a profile with only its builtin saved; given existing siblings `"{profile_name} (2)"`/`"{profile_name} (4)"` (3 deleted), returns `"{profile_name} (5)"`, not `"{profile_name} (4)"` | same |
| 12 | `create_static_named_controller` called twice for the same `profile_name` under different display names produces two distinct ids, both resolvable via `configurations_for_profile` | same |
| 13 | `configurations_for_grid` returns every `kind == "grid"` record regardless of `module_shape`, including ones that do not match any currently-plausible shape | same |
| 14 | A migration-created Grid record (`NAMEDCTRL-MIGRATE-001`) has `is_builtin == True`; a shape's zero-candidate auto-created record (`NAMEDCTRL-MATCH-002`) has `is_builtin == False` | same |
| 15 | `shape_matches_connected_hardware` returns `True` only when `module_shape` is an exact tuple match (order-sensitive) to the connected shape, `False` for a reordered or differently-sized shape | same |
| 16 | A hand-written registry file shaped like a pre-Phase-1.4 static record (no `is_builtin` key) parses with `is_builtin == False` via `load_registry`, then is retroactively corrected to `True` and re-persisted the next time `ensure_static_named_controller` is called for it, with every other field unchanged | same |

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Matching key for Grid | Ordered module-*type* shape (tuple of recognized type names) | Per-module `(x, y)`-position fingerprint; a user-entered hardware checksum | No persistent per-module identity exists (§1); position is already established as non-identity by the existing USB-root normalization. Type shape is the coarsest signal that is nonetheless genuinely stable across rearrangement/reconnection. |
| `id`/`display_name` separation | Two independent fields; rename touches only `display_name` | One mutable `name` field doubling as both | A rename must never risk detaching a saved mapping from its Preset Store file; keeping the Preset Store key (`id`) immutable after creation makes that structurally impossible rather than a discipline to maintain. |
| Zero-match behavior | Auto-create and activate immediately, no prompt | Always prompt to name a new arrangement before activating | Matches Korg's and Grid's own existing zero-configuration precedent; an unseen shape is new, not ambiguous — nothing to confirm. |
| Many-match behavior | Block; surface `Ambiguous`; never guess | Pick the most-recently-used candidate; pick alphabetically first | Exactly the "cannot silently activate motion-relevant mappings onto ambiguous hardware" principle the task driving this phase states outright; any automatic tiebreak is a guess dressed as a default. |
| Grid id generation | Deterministic `grid-{n}`, scanning existing entries | `uuid4` | Deterministic, human-legible filenames and reproducible test behavior; this registry is small (one entry per saved rig, not per event), so scan-based generation costs nothing meaningful. |
| Legacy migration trigger | Registry-empty-and-legacy-file-exists, checked inside `resolve_grid_named_controller` itself | A separate one-time startup migration script/step | Keeps the migration colocated with the exact logic it is a precondition for, with no new application-startup hook; the precondition is self-disarming (true at most once per installation) without needing a persisted "have I migrated" flag of its own. |
| Named Configuration multiplicity (Phase 1.4) | Generalize this registry directly — lift the one-per-hardware-key assumption, reuse the existing records/folder/file format | A separate Named Configuration registry/table referencing a `NamedController` as a hardware anchor | The information needed (id, display_name, hardware key, created_at) is exactly what `NamedController` already is; a second persisted structure for the same shape of data is the "redundant persistence mechanism" the driving task explicitly warns against, for no separation this module's existing kind/profile_name/module_shape fields don't already provide. |
| Builtin-protection mechanism (Phase 1.4) | Explicit `is_builtin: bool` field, set once at creation | Infer "is this the builtin" from a naming convention (e.g. `id == profile_name`, or `id == "Intech Grid"`) | A convention collides the moment a user's own Save As happens to produce a matching id/name (a user could legitimately want to rename a sibling back to look like the bare profile name); an explicit flag set only by the two trusted creation call sites is unambiguous regardless of what any record's `id`/`display_name` currently reads. |
| Grid Load list scope (Phase 1.4) | `configurations_for_grid` returns every saved Grid configuration, regardless of shape; the UI disables selection of a shape-mismatched one with a reason shown | Filter to only configurations matching the currently-connected shape | A silently-filtered list would make a genuinely saved "Stewart Platform Controller" configuration look deleted the moment a different rig is connected; showing it (disabled, with a clear reason) is what makes `shape_matches_connected_hardware`'s validation an observable, testable behavior rather than a tautology. |
| Save on an active builtin (Phase 1.4) | Routes directly into the Save-As flow (prompts for a name) | Disable the Save button entirely while a builtin is active, with no path forward except a separately-labeled Save As | A disabled Save button either needs its own explanatory tooltip (extra UI surface) or looks broken; routing Save itself into Save-As's existing prompt reuses one mechanism and one user-facing message ("this is a built-in default — name your copy") instead of two. |
| Pre-Phase-1.4 static record upgrade (Phase 1.4) | Self-heal to `is_builtin = True` the next time `ensure_static_named_controller` finds one still `False` | Leave existing installations' default records permanently unprotected; require a one-time manual migration step | An upgrading user's existing default configuration is semantically identical to what a fresh install's protected default is — leaving it unprotected only because of *when* it was created is an arbitrary distinction with no user-facing justification, and a silent in-place correction needs no new migration step or user action. |

**Accepted, not a bug**: `display_name` is never deduplicated — two `NamedController`s (even of different `kind`) may share an identical `display_name` after a rename. Since `display_name` is display-only and never used as a key (§1), this cannot corrupt a mapping or cause a false match; at most it makes an ambiguity-resolution list (§3 step 5) momentarily confusing to read, which is an argument for showing `module_shape`/`created_at` alongside `display_name` in that dialog (`docs/llds/app-ui.md`'s concern), not for adding uniqueness enforcement here.

## Open Questions

1. **Deletion UX** — not designed here (§9); add when a real need for it surfaces.
2. **Whether a Named Controller's `module_shape` should ever be user-editable** (e.g. to deliberately merge two saved identities) — no request for this exists; left unaddressed rather than speculatively designed.
3. **Multi-Grid-chain interaction** (`docs/llds/intech-grid.md`'s existing "ambiguous Grid CDC candidates" state, unrelated to this LLD's `Ambiguous` outcome) — the two ambiguity kinds are surfaced through the same status mechanism but are conceptually distinct (hardware-discovery ambiguity vs. saved-identity ambiguity); `docs/llds/app-ui.md` is responsible for not conflating their UI text.
4. **Whether `configurations_for_grid`'s unfiltered-by-shape listing should be capped or paginated** once a registry accumulates many saved rigs across many shapes — no real-world count exists yet to size this against; revisit if it surfaces as a usability problem.

## References

- `docs/high-level-design.md § Named Controller Registry`, `§ Key Design Decisions` — the architectural commitments this LLD elaborates.
- `docs/llds/intech-grid.md § Runtime Topology Model`, `§ Persistence` — the source of `module_shape` and the Preset Store keying this LLD now feeds.
- `docs/llds/static-mapping.md § Preset Store` — the unchanged file format/bounds-checking this LLD's resolved `id` is handed to.
- `docs/llds/app-ui.md § Save/Save As/Load UI` (Phase 1.4) and its preceding Named Controller UI section (Phase 1.3) — the Qt-facing consumer of this LLD's call shapes, including § 8's new ones.
