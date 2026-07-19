from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .signal_monitor import ChannelState

_DOT_COLOR = {
    ChannelState.LIVE: "#2ecc71",
    ChannelState.ERROR: "#e67e22",
    ChannelState.QUIET: "#7f8c8d",
}


class IndicatorRow(QWidget):
    """One status row: a colored dot (live/error/quiet) plus a label.

    @spec UI-STATUS-001
    """

    def __init__(self, title: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._dot = QLabel("●")
        layout.addWidget(self._dot)
        layout.addWidget(QLabel(title))
        self._detail = QLabel("")
        layout.addWidget(self._detail, 1)
        self.set_state(ChannelState.QUIET, "")

    def set_state(self, state: ChannelState, label: str) -> None:
        self._dot.setStyleSheet(f"color: {_DOT_COLOR[state]}; font-size: 16px;")
        self._detail.setText(label)
