"""Cell-level undo history. Large worksheets are not copied on each keystroke."""
from dataclasses import dataclass


@dataclass
class CellEdit:
    label: str
    before: dict
    after: dict
    previous_count: int


@dataclass
class ColumnEdit:
    label: str
    before: dict
    after: dict


class WorksheetHistory:
    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []

    def clear(self):
        self.undo_stack.clear()
        self.redo_stack.clear()

    def push(self, command):
        self.undo_stack.append(command)
        self.redo_stack.clear()
        # Bound history by changed cells as well as command count.
        def cells(command):
            if isinstance(command, ColumnEdit):
                return sum(len(row) for state in (command.before, command.after) for row in state["records"])
            return len(command.before)
        while len(self.undo_stack) > 1 and (len(self.undo_stack) > 100 or sum(cells(c) for c in self.undo_stack) > 250000):
            self.undo_stack.pop(0)

