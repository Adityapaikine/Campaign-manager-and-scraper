"""Compact forms used by the authenticated desktop workspace."""
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QRunnable, QThreadPool
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton,QFormLayout,QComboBox,
    QDialogButtonBox,QListWidget,QListWidgetItem,QTextEdit,QTableWidget,QTableWidgetItem,QHeaderView,QCheckBox,QScrollArea,QWidget)
from app.team.client import TeamClient

class TaskSignals(QObject):
    result=Signal(object); error=Signal(str)

class TeamTask(QRunnable):
    def __init__(self,fn): super().__init__(); self.fn=fn; self.signals=TaskSignals()
    def run(self):
        try: value=self.fn()
        except Exception as exc: self.signals.error.emit(str(exc))
        else: self.signals.result.emit(value)

class LoginDialog(QDialog):
    def __init__(self,parent=None,url='http://127.0.0.1:8765'):
        super().__init__(parent); self.setWindowTitle('Sign in · Lead Workspace'); self.resize(470,350)
        root=QVBoxLayout(self); title=QLabel('Lead Workspace'); title.setObjectName('pageTitle'); root.addWidget(title)
        note=QLabel('Sign in to the shared service. Your campaigns, leads and worksheets follow your account.'); note.setWordWrap(True); note.setObjectName('muted'); root.addWidget(note)
        setup=QLabel('First use on the server PC: run Setup Team Server.bat to create your Super User. There is no default password.'); setup.setWordWrap(True); setup.setObjectName('muted'); root.addWidget(setup)
        form=QFormLayout(); root.addLayout(form)
        self.url=QLineEdit(url); self.username=QLineEdit(); self.password=QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        for name,control in [('Server',self.url),('Username or email',self.username),('Password',self.password)]: form.addRow(name,control)
        self.error=QLabel(); self.error.setWordWrap(True); root.addWidget(self.error)
        self.login_button=QPushButton('Sign in'); self.login_button.setObjectName('primaryButton'); self.login_button.clicked.connect(self.sign_in); root.addWidget(self.login_button)
        self.password.returnPressed.connect(self.sign_in); self.client=None; self.busy=False
    def sign_in(self):
        if self.busy:return
        try: client=TeamClient(self.url.text().strip())
        except ValueError as exc: self.error.setText(str(exc)); return
        self.busy=True; self.login_button.setEnabled(False); self.error.setText('Connecting…')
        username,password=self.username.text(),self.password.text()
        self.task=TeamTask(lambda:client.login(username,password))
        def done(_): self.client=client; self.password.clear(); self.busy=False; self.accept()
        def failed(message): self.busy=False; self.login_button.setEnabled(True); self.password.clear(); self.error.setText(message)
        self.task.signals.result.connect(done); self.task.signals.error.connect(failed); QThreadPool.globalInstance().start(self.task)
    def reject(self):
        if not self.busy: super().reject()

class CampaignPicker(QDialog):
    def __init__(self,parent,campaigns):
        super().__init__(parent); self.setWindowTitle('Select Campaign'); self.resize(540,420); root=QVBoxLayout(self)
        search=QLineEdit(); search.setPlaceholderText('Search campaign name or CID'); root.addWidget(search)
        self.list=QListWidget(); root.addWidget(self.list)
        for campaign in campaigns:
            item=QListWidgetItem(campaign['campaign_name']+'  ·  '+campaign['campaign_id']); item.setData(Qt.ItemDataRole.UserRole,campaign); self.list.addItem(item)
        search.textChanged.connect(lambda value:[self.list.item(i).setHidden(value.casefold() not in self.list.item(i).text().casefold()) for i in range(self.list.count())])
        self.list.itemDoubleClicked.connect(lambda _:self.accept())
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Open|QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    def selected(self): return self.list.currentItem().data(Qt.ItemDataRole.UserRole) if self.list.currentItem() else None
    def accept(self):
        if self.selected(): super().accept()

class FormDialog(QDialog):
    """Field specifications: label, initial value, choices (None for plain text)."""
    def __init__(self,parent,title,fields):
        super().__init__(parent); self.setWindowTitle(title); self.resize(650,650); root=QVBoxLayout(self)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); body=QWidget(); form=QFormLayout(body); scroll.setWidget(body); root.addWidget(scroll)
        self.controls={}
        for key,(label,value,choices) in fields.items():
            if choices is not None and isinstance(value,list):
                control=QListWidget(); control.setMaximumHeight(110)
                for name,data in choices:
                    item=QListWidgetItem(name); item.setData(Qt.ItemDataRole.UserRole,data); item.setCheckState(Qt.CheckState.Checked if data in value else Qt.CheckState.Unchecked); control.addItem(item)
            elif choices is not None:
                control=QComboBox()
                for name,data in choices: control.addItem(name,data)
                idx=control.findData(value); control.setCurrentIndex(max(0,idx))
            elif isinstance(value,bool): control=QCheckBox(); control.setChecked(value)
            elif key in ('note','comment','body','config','values'):
                control=QTextEdit(); control.setPlainText(value or '')
            else:
                control=QLineEdit(str(value or ''))
                if 'password' in key: control.setEchoMode(QLineEdit.EchoMode.Password)
            form.addRow(label,control); self.controls[key]=control
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); root.addWidget(buttons)
    def values(self):
        out={}
        for key,control in self.controls.items():
            out[key]=[control.item(i).data(Qt.ItemDataRole.UserRole) for i in range(control.count()) if control.item(i).checkState()==Qt.CheckState.Checked] if isinstance(control,QListWidget) else control.currentData() if isinstance(control,QComboBox) else control.isChecked() if isinstance(control,QCheckBox) else control.toPlainText() if isinstance(control,QTextEdit) else control.text()
        return out

class RowsDialog(QDialog):
    def __init__(self,parent,title,rows):
        super().__init__(parent); self.setWindowTitle(title); self.resize(950,560); root=QVBoxLayout(self)
        table=QTableWidget(); root.addWidget(table); self.table=table
        headers=list(dict.fromkeys(key for row in rows for key in row)); table.setColumnCount(len(headers)); table.setHorizontalHeaderLabels(headers); table.setRowCount(len(rows))
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); table.setAlternatingRowColors(True)
        for r,row in enumerate(rows):
            for c,key in enumerate(headers):
                value=row.get(key,''); item=QTableWidgetItem(str(value)); item.setToolTip(str(value)); table.setItem(r,c,item)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive); table.resizeColumnsToContents()
        close=QDialogButtonBox(QDialogButtonBox.StandardButton.Close); close.rejected.connect(self.reject); root.addWidget(close)
