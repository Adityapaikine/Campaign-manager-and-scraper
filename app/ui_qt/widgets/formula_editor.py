"""Arrow-key reference picking without moving or committing the output cell."""
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit


class FormulaLineEdit(QLineEdit):
    draft_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.origin = None
        self.resolve_reference = None
        self.highlight_reference = None
        self.reference_cursor = None
        self.reference_anchor = None
        self.reference_span = None
        self._picking = False
        self.text_navigation = False
        self.textChanged.connect(self._text_changed)
        self.editingFinished.connect(self.clear_reference)

    def clear_reference(self):
        self.reference_cursor = self.reference_anchor = self.reference_span = None
        if self.highlight_reference:
            self.highlight_reference(None)

    def _text_changed(self, text):
        if not self._picking:
            self.clear_reference()
        self.draft_changed.emit(text)

    def _expects_reference(self):
        if not self.text().startswith("=") or self.text_navigation:
            return False
        if self.reference_span:
            start, end = self.reference_span
            if self.cursorPosition() == end and not self.hasSelectedText():
                return True
            self.clear_reference()
        prefix = self.text()[:self.cursorPosition()]
        # Operators inside quoted text and unfinished [Header] names are text edits.
        unquoted = re.sub(r'"(?:[^"]|"")*"', "", prefix)
        if '"' in unquoted or unquoted.count("[") != unquoted.count("]"):
            return False
        return bool(re.search(r"[=+\-*/^&(<>,;:]\s*$", prefix)) and not self.hasSelectedText()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F2 and self.text().startswith("="):
            self.text_navigation = not self.text_navigation
            self.clear_reference(); event.accept(); return
        arrows = {Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down}
        modifiers = event.modifiers()
        if (event.key() in arrows and not modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)
                and self.origin is not None and self.resolve_reference and self._expects_reference()):
            previous = self.reference_cursor or self.origin
            target = self.resolve_reference(previous, event.key())
            if target is None:
                event.accept(); return
            extend = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
            anchor = self.reference_anchor if extend and self.reference_anchor else target
            self.reference_cursor, self.reference_anchor = target, anchor
            from app.ui_qt.widgets.lead_table import column_letters
            def address(cell): return f"{column_letters(cell[1])}{cell[0] + 1}"
            if anchor != target:
                first = (min(anchor[0], target[0]), min(anchor[1], target[1]))
                last = (max(anchor[0], target[0]), max(anchor[1], target[1]))
                reference = f"{address(first)}:{address(last)}"
            else:
                first = last = target
                reference = address(target)
            start, end = self.reference_span or (self.cursorPosition(), self.cursorPosition())
            self._picking = True
            try:
                self.setText(self.text()[:start] + reference + self.text()[end:])
                self.setCursorPosition(start + len(reference))
                self.reference_span = (start, start + len(reference))
            finally:
                self._picking = False
            if self.completer():
                self.completer().popup().hide()
            if self.highlight_reference:
                self.highlight_reference((first, last))
            event.accept(); return
        # F4/text editing ends the current point selection. A later operator starts
        # a new reference relative to the unchanged formula output cell.
        if event.key() not in {Qt.Key.Key_Shift, Qt.Key.Key_Control}:
            self.clear_reference()
        super().keyPressEvent(event)
