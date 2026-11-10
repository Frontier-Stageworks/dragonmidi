"""The Named Controller Ambiguous dialog (`docs/llds/app-ui.md § Named
Controller UI`, Phase 1.3) - shown only when `resolve_grid_named_controller()`
(`named_controller_registry.py`) returns `Ambiguous`: two or more saved Named
Controllers share the module-type shape that just settled, and
`docs/llds/named-controller.md`'s governing constraint means DragonMIDI
genuinely cannot tell them apart from topology alone. Offers no "decide
later" dismissal that leaves Grid active with no chosen identity - closing
without a selection leaves the caller's `exec()` returning `None`, which
`app.py` treats the same as `UnsupportedTopology`/`AddressCollision` (no
controller installed).

@spec NAMEDCTRL-AMBIG-001, NAMEDCTRL-AMBIG-002
@spec UI-NAMEDCTRL-002, UI-NAMEDCTRL-003
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

from .named_controller_registry import NamedController, default_display_name, rename_named_controller, shape_matches_connected_hardware

_CREATE_NEW_SENTINEL = object()
_ITEM_PAYLOAD_ROLE = Qt.ItemDataRole.UserRole


class NamedControllerAmbiguousDialog(QDialog):
    def __init__(self, candidates: tuple[NamedController, ...], module_shape: tuple[str, ...]) -> None:
        super().__init__()
        self.setWindowTitle("Multiple saved configurations match")
        self._module_shape = module_shape
        # Either an existing NamedController (picked from the list) or a
        # plain `str` (a new display name to create under, via
        # named_controller_registry.create_grid_named_controller) - never
        # both, resolved by the caller checking the type.
        self._chosen: NamedController | str | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"This hardware ({'+'.join(module_shape)}) matches more than one saved configuration. Choose which one applies:"))

        self._list = QListWidget()
        for candidate in candidates:
            item = QListWidgetItem(f"{candidate.display_name}  (saved {candidate.created_at})")
            item.setData(_ITEM_PAYLOAD_ROLE, candidate)
            self._list.addItem(item)
        create_item = QListWidgetItem("Create new configuration…")
        create_item.setData(_ITEM_PAYLOAD_ROLE, _CREATE_NEW_SENTINEL)
        self._list.addItem(create_item)
        self._list.itemDoubleClicked.connect(lambda _item: self._on_accept())
        layout.addWidget(self._list)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self._on_accept)
        button_row.addWidget(ok_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

    def _on_accept(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        payload = item.data(_ITEM_PAYLOAD_ROLE)
        if payload is _CREATE_NEW_SENTINEL:
            default_name = default_display_name(self._module_shape)
            name, ok = QInputDialog.getText(self, "Name this configuration", "Name:", text=default_name)
            if not ok or not name.strip():
                return
            self._chosen = name.strip()
        else:
            self._chosen = payload
        self.accept()

    def chosen_candidate(self) -> NamedController | str | None:
        """An existing `NamedController` (picked from the list), a plain
        `str` (a new display name - the caller creates the real persisted
        record via `named_controller_registry.create_grid_named_controller`,
        this dialog never writes to disk itself), or `None` if cancelled."""
        return self._chosen


class ConfigurationLoadDialog(QDialog):
    """The explicit, on-demand Load dialog (`docs/llds/app-ui.md § Save/Save
    As/Load UI`, Phase 1.4) - a distinct class from `NamedControllerAmbiguousDialog`
    above, since its candidate source, disablement rule, and rename affordance
    all differ from that connect-time-only dialog, not a reuse of it.

    For a `kind == "grid"` candidate list, `connected_shape` (the currently-
    installed Grid controller's settled `module_shape`) is used to disable
    selection of any candidate whose own `module_shape` doesn't match -
    shown, never hidden, with a tooltip naming the mismatch
    (`shape_matches_connected_hardware`, @spec NAMEDCTRL-CONFIG-006). Passed
    as `None` for a `kind == "static"` candidate list, where every candidate
    is always loadable (a Korg profile's shape never varies).

    @spec UI-SAVELOAD-006, UI-SAVELOAD-007, UI-SAVELOAD-008
    """

    def __init__(
        self,
        named_controllers_dir: Path,
        candidates: tuple[NamedController, ...],
        *,
        connected_shape: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Load configuration")
        self._named_controllers_dir = named_controllers_dir
        self._connected_shape = connected_shape
        self._chosen: NamedController | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Choose a saved configuration to load:"))

        self._list = QListWidget()
        for candidate in candidates:
            self._list.addItem(self._build_item(candidate))
        self._list.itemDoubleClicked.connect(lambda _item: self._on_accept())
        self._list.currentItemChanged.connect(lambda *_args: self._sync_button_states())
        layout.addWidget(self._list)

        button_row = QHBoxLayout()
        self._rename_button = QPushButton("Rename…")
        self._rename_button.clicked.connect(self._on_rename_clicked)
        button_row.addWidget(self._rename_button)
        button_row.addStretch(1)
        self._load_button = QPushButton("Load")
        self._load_button.clicked.connect(self._on_accept)
        button_row.addWidget(self._load_button)
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_row.addWidget(cancel_button)
        layout.addLayout(button_row)

        self._sync_button_states()

    def _mismatch_reason(self, candidate: NamedController) -> str | None:
        if self._connected_shape is None or candidate.module_shape is None:
            return None
        if shape_matches_connected_hardware(candidate, self._connected_shape):
            return None
        return f"Saved for {'+'.join(candidate.module_shape)} — connected hardware is {'+'.join(self._connected_shape)}"

    def _build_item(self, candidate: NamedController) -> QListWidgetItem:
        label = candidate.display_name
        if candidate.is_builtin:
            label += " (built-in)"
        label += f"  (saved {candidate.created_at})"
        item = QListWidgetItem(label)
        item.setData(_ITEM_PAYLOAD_ROLE, candidate)
        reason = self._mismatch_reason(candidate)
        if reason is not None:
            # @spec UI-SAVELOAD-007: shown, never hidden - disabled with a
            # tooltip naming the mismatch, not removed from the list.
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            item.setToolTip(reason)
        return item

    def _sync_button_states(self) -> None:
        item = self._list.currentItem()
        selectable = item is not None and bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)
        self._load_button.setEnabled(selectable)
        candidate = item.data(_ITEM_PAYLOAD_ROLE) if item is not None else None
        # @spec UI-SAVELOAD-008: rename is offered for any non-builtin row,
        # including a shape-mismatched one (renaming doesn't load it).
        self._rename_button.setEnabled(item is not None and candidate is not None and not candidate.is_builtin)

    def _on_rename_clicked(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        candidate: NamedController = item.data(_ITEM_PAYLOAD_ROLE)
        name, ok = QInputDialog.getText(self, "Rename configuration", "Name:", text=candidate.display_name)
        if not ok or not name.strip():
            return
        renamed = rename_named_controller(self._named_controllers_dir, candidate.id, name.strip())
        row = self._list.row(item)
        self._list.takeItem(row)
        self._list.insertItem(row, self._build_item(renamed))
        self._list.setCurrentRow(row)

    def _on_accept(self) -> None:
        item = self._list.currentItem()
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        self._chosen = item.data(_ITEM_PAYLOAD_ROLE)
        self.accept()

    def chosen_configuration(self) -> NamedController | None:
        return self._chosen
