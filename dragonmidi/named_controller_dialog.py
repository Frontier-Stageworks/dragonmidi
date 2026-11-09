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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QInputDialog, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout

from .named_controller_registry import NamedController, default_display_name

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
