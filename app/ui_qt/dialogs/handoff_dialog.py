"""Explicit selected-row handoff preview, without silently skipping blocked rows."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QLabel,QComboBox,QTableWidget,
    QTableWidgetItem,QHeaderView,QLineEdit,QDialogButtonBox)


class HandoffDialog(QDialog):
    def __init__(self,parent,preview):
        super().__init__(parent); self.preview=preview
        self.setWindowTitle('Send selected leads to another department'); self.resize(840,520)
        root=QVBoxLayout(self)
        title=QLabel(f"Review {preview['count']} selected lead(s)"); title.setObjectName('sectionTitle'); root.addWidget(title)
        self.destination=QComboBox()
        for route in preview['routes']:
            self.destination.addItem(f"{route['name']} · requires {route['required_state']}",route)
        root.addWidget(self.destination)
        self.summary=QLabel(); self.summary.setWordWrap(True); root.addWidget(self.summary)
        self.table=QTableWidget(0,3); self.table.setHorizontalHeaderLabels(['Selected lead','Current stage','Readiness'])
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table,1)
        self.note=QLineEdit(); self.note.setMaxLength(2000); self.note.setPlaceholderText('Optional handoff note'); root.addWidget(self.note)
        explanation=QLabel('The receiving lead will find these records using Incoming leads, then Assign selected. Original ownership and history are preserved.'); explanation.setWordWrap(True); root.addWidget(explanation)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.send_button=buttons.button(QDialogButtonBox.StandardButton.Ok); self.send_button.setObjectName('primaryButton')
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
        self.destination.currentIndexChanged.connect(self.update_route); self.update_route()

    def update_route(self):
        route=self.destination.currentData()
        if not route:self.send_button.setEnabled(False); return
        total=self.preview['count']; ready=route['ready']; self.table.setRowCount(total)
        for i,row in enumerate(route['rows']):
            for j,value in enumerate((row['name'],row['state'],row['reason'])):
                item=QTableWidgetItem(value); item.setToolTip(row['id'] if j==0 else value); self.table.setItem(i,j,item)
        self.table.resizeRowsToContents()
        self.summary.setText(f"{ready} of {total} ready for {route['name']}. "+
            ('All selected leads will be sent.' if ready==total else 'Resolve the blocked rows or select only ready leads. No rows will be sent until the entire selection is eligible.'))
        self.send_button.setText('Push to '+route['name']); self.send_button.setEnabled(ready==total and total>0)

    def values(self):return {'route_id':self.destination.currentData()['id'],'note':self.note.text().strip()}

    def accept(self):
        if self.send_button.isEnabled():super().accept()
