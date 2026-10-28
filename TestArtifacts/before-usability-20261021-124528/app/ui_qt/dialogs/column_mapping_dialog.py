from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QScrollArea, QVBoxLayout, QWidget


class ColumnMappingDialog(QDialog):
    def __init__(self,parent,source_columns:list[str],target_columns:list[str],suggested:dict[str,str]|None=None,title="Column Mapping"):
        super().__init__(parent); self.setWindowTitle(title); self.resize(620,650); self._boxes={}; suggested=suggested or {}
        root=QVBoxLayout(self); info=QLabel("Map source columns to application fields. Leave a source column as (Ignore) when it should not be imported."); info.setWordWrap(True); root.addWidget(info)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); content=QWidget(); form=QFormLayout(content)
        choices=["(Ignore)"]+list(target_columns)
        for source in source_columns:
            box=QComboBox(); box.addItems(choices); target=suggested.get(source); box.setCurrentText(target if target in choices else "(Ignore)"); self._boxes[source]=box; form.addRow(source,box)
        scroll.setWidget(content); root.addWidget(scroll,1)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def mapping(self)->dict[str,str]:
        return {source:box.currentText() for source,box in self._boxes.items() if box.currentText()!="(Ignore)"}
