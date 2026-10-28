"""External connector contract and UI tests; never use a user's database server."""
from contextlib import contextmanager
from dataclasses import asdict, replace
from pathlib import Path
import sys
import time
import traceback
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox

from app.core.database_connections import (
    DatabaseConfig, DatabaseError, DatabaseProfiles, RemoteLeadSource, _identifier,
    _odbc_value, suggested_mapping,
)
from app.core.lead_reference import COMPANY_KEY, PROSPECT_KEY, ReferenceInfo
from app.core.settings_service import SettingsService
from app.ui_qt.controller import ApplicationController
from app.ui_qt.dialogs.database_connection_dialog import DatabaseConnectionDialog
from app.ui_qt.dialogs.populate_dialog import PopulateColumnsDialog
from app.ui_qt.main_window import MainWindow


def profile(engine="postgres"):
    return DatabaseConfig(engine=engine, host="db.example", port=5432 if engine == "postgres" else 1433,
                          database="leads", username="reader", schema="research", table="prospects",
                          mapping={PROSPECT_KEY: "linkedin_url", COMPANY_KEY: "website", "Business Email ID": "work_email", "Company Name": "business_name"})


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.result = []
        self.closed = False

    def execute(self, sql, params=None):
        self.connection.queries.append((sql, params))
        assert sql.startswith("SELECT "), "Connectors must not issue writes"
        if "INFORMATION_SCHEMA.TABLES" in sql:
            self.result = [("research", "prospects")]
        elif "INFORMATION_SCHEMA.COLUMNS" in sql:
            self.result = [(name,) for name in self.connection.columns]
        elif "WHERE 1=0" in sql:
            self.result = []
        elif "linkedin_url" in sql:
            self.result = [("https://linkedin.com/in/person-a", "person@acme.example")]
        else:
            self.result = [("https://www.acme.example", "Acme"), ("acme.example/", "Acme")]
        return self

    def fetchall(self):
        return self.result

    def fetchmany(self, size):
        assert size == 1000
        result, self.result = self.result[:size], self.result[size:]
        return result

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self):
        self.columns = ["linkedin_url", "website", "work_email", "business_name"]
        self.queries, self.cursors = [], []
        self.closed = False

    def cursor(self, **kwargs):
        cursor = FakeCursor(self)
        self.cursors.append((cursor, kwargs))
        return cursor

    def close(self):
        self.closed = True


@pytest.mark.parametrize("engine", ["postgres", "mssql"])
def test_metadata_mapping_and_real_lookup_algorithm_with_driver_contract(engine, monkeypatch):
    connections, calls = [], []
    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        connection = FakeConnection(); connections.append(connection)
        return connection
    if engine == "postgres":
        monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=connect, IsolationLevel=SimpleNamespace(REPEATABLE_READ="repeatable")))
    else:
        monkeypatch.setitem(sys.modules, "pyodbc", SimpleNamespace(connect=connect, drivers=lambda: ["ODBC Driver 18 for SQL Server"]))
    config = profile(engine)
    source = RemoteLeadSource(config, "test-only-password")
    assert source.tables() == [("research", "prospects")]
    assert source.info().available_fields == ("Business Email ID", "Company Name", "Company Website")
    target = [{PROSPECT_KEY: "linkedin.com/in/person-a", COMPANY_KEY: "acme.example"}]
    result = source.plan(target, ["Business Email ID", "Company Name"], [0], workspace_key="general")
    assert result.edits == {(0, "Business Email ID"): "person@acme.example", (0, "Company Name"): "Acme"}
    assert all(connection.closed for connection in connections)
    assert all(cursor.closed for connection in connections for cursor, _ in connection.cursors)
    for connection in connections:
        for sql, params in connection.queries:
            if "INFORMATION_SCHEMA.COLUMNS" in sql:
                assert params == ("research", "prospects")
                assert ("%s" if engine == "postgres" else "?") in sql
    if engine == "postgres":
        assert calls[0][1]["sslmode"] == "verify-full"
        assert connections[0].read_only
        assert connections[0].isolation_level == "repeatable"
        assert any(kwargs.get("name") for _, kwargs in connections[-1].cursors)
    else:
        assert "Encrypt={yes}" in calls[0][0][0]
        assert "TrustServerCertificate={no}" in calls[0][0][0]
        assert calls[0][1]["timeout"] == 15
        assert connections[0].timeout == 60


def test_sql_server_windows_auth_uses_no_password_and_handles_named_instance(monkeypatch):
    calls = []
    def connect(text, **kwargs):
        calls.append(text); return FakeConnection()
    monkeypatch.setitem(sys.modules, "pyodbc", SimpleNamespace(connect=connect, drivers=lambda: ["ODBC Driver 17 for SQL Server"]))
    config = replace(profile("mssql"), auth="windows", username="", host=r"SERVER\INSTANCE", port=0)
    RemoteLeadSource(config, "must-not-be-sent").tables()
    assert "SERVER={SERVER\\INSTANCE}" in calls[0]
    assert "Trusted_Connection={yes}" in calls[0]
    assert "PWD=" not in calls[0] and "UID=" not in calls[0]
    assert "must-not-be-sent" not in calls[0]


def test_sql_identifiers_and_connection_values_are_escaped():
    assert _identifier('a"; DROP TABLE x; --', "postgres") == '"a""; DROP TABLE x; --"'
    assert _identifier("a]; DROP TABLE x; --", "mssql") == "[a]]; DROP TABLE x; --]"
    assert _odbc_value("secret};UID=other") == "{secret}};UID=other}"
    with pytest.raises(DatabaseError):
        _identifier("bad\x00name", "postgres")


def test_password_is_session_only_and_connections_restore_independently():
    settings = SettingsService(); profiles = DatabaseProfiles(settings)
    config = profile()
    profiles.save(config, "never-save-this-password")
    assert profiles.password(config) == "never-save-this-password"
    assert "never-save-this-password" not in str(settings.all())
    restored = DatabaseProfiles(settings)
    assert restored.load() == config
    assert restored.password(config) is None
    profiles.save(profile("mssql"), "another-password")
    profiles.save(DatabaseConfig())
    assert profiles.load().engine == "local"
    assert profiles.load("postgres") == config
    assert profiles.load("mssql").engine == "mssql"
    assert "password" not in asdict(DatabaseConfig.from_dict({**asdict(config), "password": "secret"}))


def test_mapping_suggestions_are_unambiguous_and_manual_mapping_wins():
    assert suggested_mapping(["linkedin_url", "company_website", "job_title"])[PROSPECT_KEY] == "linkedin_url"
    assert "Business Email ID" not in suggested_mapping(["email", "email_address"])
    assert suggested_mapping(["work_email", "email"], {"Business Email ID": "work_email"})["Business Email ID"] == "work_email"
    config = profile()
    config.mapping["Job Title"] = "work_email"
    with pytest.raises(DatabaseError, match="only one"):
        config.validate(require_table=True)


def test_missing_keys_disable_fields_and_changed_schema_requires_mapping():
    config = profile()
    config.mapping.pop(PROSPECT_KEY)
    assert "Business Email ID" not in config.available_fields()
    source = RemoteLeadSource(config)
    with pytest.raises(DatabaseError, match="lookup keys"):
        source.plan([{COMPANY_KEY: "acme.example"}], ["Business Email ID"], [0], workspace_key="general")
    with pytest.raises(DatabaseError, match="headers have changed"):
        source._check_mapping(["website", "business_name"])


@pytest.mark.parametrize("engine", ["postgres", "mssql"])
def test_driver_failure_is_actionable_and_never_leaks_secrets(engine, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("password authentication failed: PWD=private-test-secret; connection string")
    if engine == "postgres":
        monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fail))
    else:
        monkeypatch.setitem(sys.modules, "pyodbc", SimpleNamespace(connect=fail, drivers=lambda: ["ODBC Driver 18 for SQL Server"]))
    try:
        RemoteLeadSource(profile(engine), "private-test-secret").tables()
    except DatabaseError as exc:
        assert "sign-in failed" in str(exc)
        trace = traceback.format_exc()
        assert "private-test-secret" not in str(exc)
        # Suppressed underlying exception text cannot reach the generic worker log.
        assert "RuntimeError: password authentication" not in trace
    else:
        pytest.fail("Connection failure was ignored")


def test_missing_sql_server_driver_does_not_claim_connection(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyodbc", SimpleNamespace(drivers=lambda: ["SQL Server"]))
    with pytest.raises(DatabaseError, match="ODBC Driver 18"):
        RemoteLeadSource(profile("mssql")).tables()


def wait(qt, condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        qt.processEvents(); time.sleep(0.01)
    assert condition()


def test_connection_dialog_requires_test_mapping_and_explicit_save(qt):
    from app.ui_qt.qt_theme import build_stylesheet
    qt.setStyleSheet(build_stylesheet("Professional Blue", False))
    profiles = DatabaseProfiles(SettingsService())
    dialog = DatabaseConnectionDialog(None, profiles)
    dialog.engine.setCurrentIndex(dialog.engine.findData("postgres"))
    dialog.host.setText("db.example"); dialog.database.setText("leads"); dialog.username.setText("reader"); dialog.password.setText("test-only")
    dialog.show(); qt.processEvents()
    artifacts = Path(__file__).resolve().parents[1] / "TestArtifacts"
    assert dialog.height() <= 720
    dialog.grab().save(str(artifacts / "external_database_connection.png"))
    assert not dialog.save_button.isEnabled()
    with patch.object(RemoteLeadSource, "tables", return_value=[("research", "prospects")]), patch.object(RemoteLeadSource, "columns", return_value=["linkedin_url", "website", "work_email", "business_name"]):
        dialog.connect_button.click()
        wait(qt, lambda: not dialog._busy)
        dialog.table.setCurrentIndex(1)
        wait(qt, lambda: bool(dialog.mapping_boxes))
    assert dialog.tabs.currentIndex() == 1
    assert dialog.mapping_boxes[PROSPECT_KEY].currentData() == "linkedin_url"
    email = dialog.mapping_boxes["Business Email ID"]
    email.setCurrentIndex(email.findData("work_email"))
    company = dialog.mapping_boxes["Company Name"]
    company.setCurrentIndex(company.findData("business_name"))
    assert dialog.save_button.isEnabled()
    # Connection changes invalidate both discovery and mapping; previous source stays active.
    assert profiles.load().engine == "local"
    dialog.show(); qt.processEvents()
    dialog.grab().save(str(artifacts / "external_database_mapping.png"))
    dialog.accept()
    assert profiles.load().mapping["Business Email ID"] == "work_email"
    assert profiles.password(profiles.load()) == "test-only"
    other = DatabaseConnectionDialog(None, profiles)
    assert not other.save_button.isEnabled()
    other.host.setText("changed.example")
    assert not other.mapping_boxes
    other.reject()
    assert profiles.load().host == "db.example"
    dialog.close(); other.close()


def test_populate_chooser_disables_unmapped_fields(qt):
    info = ReferenceInfo("db.example/leads", None, label="PostgreSQL", table="research.prospects", available_fields=("Company Name",))
    dialog = PopulateColumnsDialog(None, info, {"all": [0], "selected": [], "visible": [0]})
    assert not dialog.fields["Business Email ID"].isEnabled()
    dialog.select_fields(list(dialog.fields), True)
    assert dialog.selected_columns() == ["Company Name"]
    dialog.close()


def test_remote_population_main_window_uses_selected_source_and_password_prompt(qt):
    connections = []
    @contextmanager
    def connect(source):
        assert source.password == "entered-in-app"
        connection = FakeConnection(); connections.append(connection)
        yield connection
        connection.close()
    with patch.object(MainWindow, "_offer_recovery"), patch.object(MainWindow, "refresh_qwen_status"):
        window = MainWindow()
        try:
            window.autosave_timer.stop()
            controller = window.controller
            controller.database_profiles.save(profile(), "old-session")
            controller.database_profiles = DatabaseProfiles(controller.settings_service)
            controller.data_manager.append_record({PROSPECT_KEY: "linkedin.com/in/person-a", COMPANY_KEY: "acme.example"})
            window._refresh_all()
            results, errors = [], []
            def choose(dialog):
                dialog.fields["Business Email ID"].setChecked(True)
                return QDialog.DialogCode.Accepted
            with patch.object(RemoteLeadSource, "connect", connect), patch.object(PopulateColumnsDialog, "exec", choose), patch.object(QInputDialog, "getText", return_value=("entered-in-app", True)) as prompt, patch.object(QMessageBox, "exec", lambda box: results.append(box.text())), patch.object(window, "_worker_error", errors.append), patch.object(controller, "ensure_lead_database", side_effect=AssertionError("Must not fall back to local")):
                window.populate_from_database()
                wait(qt, lambda: bool(results or errors))
            assert not errors
            assert prompt.call_count == 1
            assert controller.data_manager.records[0]["Business Email ID"] == "person@acme.example"
            assert len(controller.history.undo_stack) == 1
            assert controller.database_profiles.password(profile()) == "entered-in-app"
        finally:
            window.thread_pool.waitForDone(5000); qt.processEvents(); window.close(); qt.processEvents()
