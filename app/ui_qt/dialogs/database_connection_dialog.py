"""Connect, discover a table, and explicitly confirm application/header mappings."""
from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QHeaderView, QScrollArea,
)

from app.constants import STANDARD_HEADERS
from app.core.database_connections import (
    COMPANY_KEY, PROSPECT_KEY, DatabaseConfig, DatabaseError, ENGINES,
    ODBC_DOWNLOAD_URL, RemoteLeadSource, suggested_mapping,
)
from app.ui_qt.widgets.workers import FunctionWorker


class DatabaseConnectionDialog(QDialog):
    def __init__(self, parent, profiles):
        super().__init__(parent)
        self.profiles = profiles
        self._busy = False
        self._worker = None
        self._columns = []
        self._verified = None
        self._drafts = {}
        self._previous_engine = None
        self.mapping_boxes = {}
        self.setWindowTitle("Database connection & column mapping")
        self.resize(780, 720)
        root = QVBoxLayout(self)
        title = QLabel("Choose your lead lookup database")
        title.setObjectName("sectionTitle")
        root.addWidget(title)
        self.engine = QComboBox()
        self.engine.setAccessibleName("Database type")
        for key, label in ENGINES.items():
            self.engine.addItem(label, key)
        root.addWidget(self.engine)
        self.local_note = QLabel("Use the existing local lead reference table. Your saved local leads remain available when switching database sources.")
        self.local_note.setWordWrap(True)
        root.addWidget(self.local_note)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.connection_page = QWidget()
        connection_layout = QVBoxLayout(self.connection_page)
        connection_layout.setContentsMargins(6, 6, 6, 6)
        connection_layout.setSpacing(4)
        form = QFormLayout()
        form.setVerticalSpacing(4)
        connection_layout.addLayout(form)
        self.host = QLineEdit()
        self.host.setPlaceholderText("Server name or IP; SQL Server can use SERVER\\INSTANCE")
        form.addRow("Server / host", self.host)
        self.port = QSpinBox(); self.port.setRange(0, 65535); self.port.setSpecialValueText("Default / named instance")
        self.port.setToolTip("Use 0 for a SQL Server named instance; PostgreSQL defaults to 5432.")
        form.addRow("Port", self.port)
        self.database = QLineEdit(); form.addRow("Database name", self.database)
        self.auth = QComboBox()
        self.auth.addItem("Username and password", "password")
        self.auth.addItem("Windows authentication", "windows")
        form.addRow("Authentication", self.auth)
        self.username = QLineEdit(); form.addRow("Username", self.username)
        self.password = QLineEdit(); self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setPlaceholderText("Kept only for this application session")
        form.addRow("Password", self.password)
        self.timeout = QSpinBox(); self.timeout.setRange(1, 60); self.timeout.setSuffix(" sec")
        form.addRow("Connection timeout", self.timeout)
        self.sql_options = QWidget(); sql_layout = QHBoxLayout(self.sql_options); sql_layout.setContentsMargins(0, 0, 0, 0)
        self.encrypt = QCheckBox("Encrypt connection")
        self.trust = QCheckBox("Trust server certificate")
        self.trust.setToolTip("Enable only when you intentionally trust a server whose certificate cannot be verified.")
        sql_layout.addWidget(self.encrypt); sql_layout.addWidget(self.trust); sql_layout.addStretch()
        form.addRow(self.sql_options)
        self.pg_options = QWidget(); pg = QFormLayout(self.pg_options); pg.setContentsMargins(0, 0, 0, 0)
        self.sslmode = QComboBox()
        for label, value in (("Verify certificate and hostname", "verify-full"), ("Require encryption", "require"), ("Disable SSL", "disable")):
            self.sslmode.addItem(label, value)
        pg.addRow("PostgreSQL SSL", self.sslmode)
        holder = QWidget(); ca_row = QHBoxLayout(holder); ca_row.setContentsMargins(0, 0, 0, 0)
        self.sslrootcert = QLineEdit(); self.sslrootcert.setPlaceholderText("Optional root CA certificate path")
        browse = QPushButton("Browse…"); browse.clicked.connect(self.browse_certificate)
        ca_row.addWidget(self.sslrootcert, 1); ca_row.addWidget(browse)
        pg.addRow("Root certificate", holder)
        form.addRow(self.pg_options)
        self.driver_note = QLabel(f'SQL Server uses Microsoft ODBC Driver 18 or 17. <a href="{ODBC_DOWNLOAD_URL}">Download driver</a>')
        self.driver_note.setOpenExternalLinks(True); self.driver_note.setWordWrap(True)
        connection_layout.addWidget(self.driver_note)
        self.connect_button = QPushButton("Test connection & load tables")
        self.connect_button.setObjectName("primaryButton")
        self.connect_button.clicked.connect(self.connect_clicked)
        connection_layout.addWidget(self.connect_button)
        self.table = QComboBox(); self.table.setAccessibleName("Database table or view")
        connection_layout.addWidget(QLabel("Table or view")); connection_layout.addWidget(self.table)
        connection_layout.addStretch()
        connection_scroll = QScrollArea()
        connection_scroll.setWidgetResizable(True)
        connection_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        connection_scroll.setWidget(self.connection_page)
        self.tabs.addTab(connection_scroll, "1. Connection")
        mapping_page = QWidget(); mapping_layout = QVBoxLayout(mapping_page)
        note = QLabel("Choose which database column supplies each application header. Review suggested matches and leave unused fields unmapped. "
                      "Prospect fields require Prospect LinkedIn Link; company fields require Company Website.")
        note.setWordWrap(True); mapping_layout.addWidget(note)
        self.mapping_table = QTableWidget(0, 2)
        self.mapping_table.setHorizontalHeaderLabels(["Application header", "Database column"])
        self.mapping_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.mapping_table.verticalHeader().hide()
        self.mapping_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        mapping_layout.addWidget(self.mapping_table, 1)
        self.mapping_note = QLabel(); self.mapping_note.setWordWrap(True)
        mapping_layout.addWidget(self.mapping_note)
        self.tabs.addTab(mapping_page, "2. Column mapping")
        self.status = QLabel(); self.status.setTextFormat(Qt.TextFormat.PlainText); self.status.setWordWrap(True)
        root.addWidget(self.status)
        footnote = QLabel("Connection details and mappings are saved locally. Passwords are not saved to disk. External databases are used only to read lookup values.")
        footnote.setWordWrap(True); footnote.setObjectName("muted"); root.addWidget(footnote)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        self.save_button = self.buttons.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setText("Use this database")
        self.save_button.setObjectName("primaryButton")
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)
        self.engine.currentIndexChanged.connect(self.engine_changed)
        for widget in (self.host, self.database, self.username, self.password, self.sslrootcert):
            widget.textChanged.connect(self.invalidate)
        for widget in (self.port, self.timeout):
            widget.valueChanged.connect(self.invalidate)
        for widget in (self.auth, self.sslmode):
            widget.currentIndexChanged.connect(self.invalidate)
        for widget in (self.encrypt, self.trust):
            widget.toggled.connect(self.invalidate)
        self.auth.currentIndexChanged.connect(self.update_auth)
        self.table.currentIndexChanged.connect(self.table_changed)
        current = profiles.load().engine
        self.engine.blockSignals(True); self.engine.setCurrentIndex(max(0, self.engine.findData(current))); self.engine.blockSignals(False)
        self.engine_changed()

    def engine_changed(self, *_):
        if self._previous_engine is not None:
            self._drafts[self._previous_engine] = (self.config(engine=self._previous_engine), self.password.text())
        engine = self.engine.currentData()
        config, password = self._drafts.get(engine, (self.profiles.load(engine), None))
        if password is None:
            password = self.profiles.password(config) or ""
        self._previous_engine = engine
        self.host.setText(config.host); self.port.setValue(config.port or (5432 if engine == "postgres" else 0))
        self.database.setText(config.database); self.username.setText(config.username); self.password.setText(password)
        self.auth.setCurrentIndex(max(0, self.auth.findData(config.auth)))
        self.auth.setEnabled(engine == "mssql")
        self.timeout.setValue(config.timeout)
        self.encrypt.setChecked(config.encrypt); self.trust.setChecked(config.trust_certificate)
        self.sslmode.setCurrentIndex(max(0, self.sslmode.findData(config.sslmode)))
        self.sslrootcert.setText(config.sslrootcert)
        self.sql_options.setVisible(engine == "mssql"); self.driver_note.setVisible(engine == "mssql")
        self.pg_options.setVisible(engine == "postgres")
        self.tabs.setVisible(engine != "local"); self.local_note.setVisible(engine == "local")
        self.invalidate()
        self.update_auth()
        self.tabs.setCurrentIndex(0)
        self.status.setText("Local reference database selected." if engine == "local" else "Enter your connection details, then test the connection.")

    def config(self, *, engine=None):
        table = self.table.currentData() or ("", "")
        return DatabaseConfig(engine=engine or self.engine.currentData(), host=self.host.text().strip(),
            port=self.port.value(), database=self.database.text().strip(), username=self.username.text().strip(),
            auth=self.auth.currentData(), timeout=self.timeout.value(), encrypt=self.encrypt.isChecked(),
            trust_certificate=self.trust.isChecked(), sslmode=self.sslmode.currentData(), sslrootcert=self.sslrootcert.text().strip(),
            schema=table[0], table=table[1], mapping=self.mapping())

    def mapping(self):
        return {header: box.currentData() for header, box in self.mapping_boxes.items() if box.currentData()}

    def update_auth(self, *_):
        password_auth = self.auth.currentData() == "password"
        self.username.setEnabled(password_auth); self.password.setEnabled(password_auth)

    def invalidate(self, *_):
        self._verified = None; self._columns = []
        self.table.blockSignals(True); self.table.clear(); self.table.blockSignals(False)
        self.mapping_boxes.clear(); self.mapping_table.setRowCount(0)
        self.mapping_note.clear()
        self.status.setText("Connection details changed. Test the connection and review the mapping.")
        self.save_button.setEnabled(not self._busy and self.engine.currentData() == "local")

    def browse_certificate(self):
        path, _ = QFileDialog.getOpenFileName(self, "PostgreSQL root CA certificate", "", "Certificates (*.crt *.pem);;All files (*)")
        if path:
            self.sslrootcert.setText(path)

    def _run(self, fn, done, status):
        self._busy = True
        self.engine.setEnabled(False); self.tabs.setEnabled(False); self.buttons.setEnabled(False)
        self.status.setText(status)
        worker = FunctionWorker(fn); self._worker = worker
        def finish():
            self._busy = False; self._worker = None
            self.engine.setEnabled(True); self.tabs.setEnabled(True); self.buttons.setEnabled(True)
        def success(result):
            finish()
            done(result)
        def error(trace):
            finish()
            self._verified = None; self.save_button.setEnabled(False)
            # Core service exceptions are sanitized and have suppressed driver traceback chains.
            self.status.setText(trace.splitlines()[-1].removeprefix("app.core.database_connections.DatabaseError: "))
        worker.signals.finished.connect(success); worker.signals.error.connect(error)
        QThreadPool.globalInstance().start(worker)

    def connect_clicked(self):
        try:
            config = self.config(); config.validate()
        except DatabaseError as exc:
            self.status.setText(str(exc)); return
        saved = self._drafts.get(config.engine, (self.profiles.load(config.engine), ""))[0]
        self.invalidate()
        def loaded(tables):
            self.table.blockSignals(True)
            self.table.addItem("Choose a table or view…", None)
            for schema, table in tables:
                self.table.addItem(f"{schema}.{table}", (schema, table))
            self.table.blockSignals(False)
            self.status.setText(f"Connected. {len(tables):,} tables/views available. Choose one to map its columns.")
            index = self.table.findData((saved.schema, saved.table))
            if index >= 0:
                self.table.setCurrentIndex(index)
        source = RemoteLeadSource(config, self.password.text())
        self._run(source.tables, loaded, "Connecting and loading tables…")

    def table_changed(self, *_):
        self._verified = None; self.save_button.setEnabled(False)
        self._columns = []; self.mapping_boxes.clear(); self.mapping_table.setRowCount(0)
        if not self.table.currentData():
            return
        config = self.config()
        saved = self._drafts.get(config.engine, (self.profiles.load(config.engine), ""))[0]
        previous = saved.mapping if (config.credential_key(), config.schema, config.table) == (saved.credential_key(), saved.schema, saved.table) else {}
        def loaded(columns):
            self._columns = columns
            self._verified = (config.credential_key(), config.schema, config.table)
            suggestions = suggested_mapping(columns, previous)
            # Keep matching keys and usable lookup fields near the top.
            from app.core.lead_reference import POPULATABLE_FIELDS
            headers = list(dict.fromkeys([PROSPECT_KEY, COMPANY_KEY, *POPULATABLE_FIELDS, *STANDARD_HEADERS]))
            self.mapping_table.setRowCount(len(headers))
            for row, header in enumerate(headers):
                self.mapping_table.setItem(row, 0, QTableWidgetItem(header))
                box = QComboBox(); box.setAccessibleName("Database column for " + header)
                box.addItem("— Not mapped —", "")
                for column in columns:
                    box.addItem(column, column)
                box.setCurrentIndex(max(0, box.findData(suggestions.get(header, ""))))
                box.currentIndexChanged.connect(self.update_mapping)
                self.mapping_boxes[header] = box
                self.mapping_table.setCellWidget(row, 1, box)
            self.status.setText(f"Connected. Review the mapping for {config.schema}.{config.table}, then choose Use this database.")
            self.update_mapping(); self.tabs.setCurrentIndex(1)
        self._run(RemoteLeadSource(config, self.password.text()).columns, loaded, "Reading table headers and checking access…")

    def update_mapping(self, *_):
        config = self.config()
        try:
            config.validate(require_table=True)
            available = len(config.available_fields())
            self.mapping_note.setText(f"{len(config.mapping)} headers mapped · {available} fields available to populate. Review suggestions before saving.")
            valid = self._verified == (config.credential_key(), config.schema, config.table)
        except DatabaseError as exc:
            self.mapping_note.setText(str(exc)); valid = False
        self.save_button.setEnabled(valid and not self._busy)

    def accept(self):
        if self._busy:
            return
        config = self.config()
        try:
            config.validate(require_table=config.engine != "local")
            if config.engine != "local" and self._verified != (config.credential_key(), config.schema, config.table):
                raise DatabaseError("Test the connection and review this table's columns before saving.")
            self.profiles.save(config, self.password.text())
        except (DatabaseError, OSError) as exc:
            self.status.setText(str(exc)); return
        super().accept()

    def reject(self):
        if not self._busy:
            super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
        else:
            super().closeEvent(event)
