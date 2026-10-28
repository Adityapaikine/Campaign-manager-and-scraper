"""Database population regressions; all databases and leads here are synthetic."""
from pathlib import Path
import sqlite3
import time
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from app.constants import STANDARD_HEADERS
from app.core.lead_reference import (
    COMPANY_FIELDS, PROSPECT_FIELDS, LeadReferenceStore, ReferenceInfo, company_key, prospect_key,
)
from app.core.workspace_store import WorkspaceStore
from app.ui_qt.controller import ApplicationController
from app.ui_qt.dialogs.populate_dialog import PopulateColumnsDialog
from app.ui_qt.main_window import MainWindow


def source(**changes):
    return {"First Name": "Ada", "Last Name": "Example", "Prospect LinkedIn Link": "https://www.linkedin.com/in/ada-example/",
            "Company Website": "https://www.acme.example/", "Business Email ID": "ada@acme.example",
            "Company Name": "Acme", "Industry": "Technology", "Job Title": "Director",
            "Phone Number": "+1 202 555 0100", "Zip Code": "00123", "SIC Code": "0012", **changes}


def reference(tmp_path, records=None):
    store = LeadReferenceStore(tmp_path / "reference.sqlite3")
    store.seed_workspaces(WorkspaceStore(tmp_path / "empty"))
    store.add_records(records if records is not None else [source()])
    return store


@pytest.mark.parametrize("left,right", [
    ("HTTP://www.LinkedIn.com/in/Ada-Example/?trk=test#top", "linkedin.com/in/ada-example"),
    ("in.linkedin.com/in/ada-example", "https://linkedin.com/in/ada-example/"),
    ("linkedin.com/in/ada%2Dexample", "linkedin.com/in/ada-example"),
])
def test_prospect_url_matching(left, right):
    assert prospect_key(left) == prospect_key(right) == "/in/ada-example"


@pytest.mark.parametrize("value", [None, "-", "", "https://linkedin.com/company/acme", "linkedin.com.evil.example/in/ada",
                                         "ftp://linkedin.com/in/ada", "https://x@linkedin.com/in/ada", "https://[broken"])
def test_invalid_prospect_links_do_not_match(value):
    assert prospect_key(value) is None


def test_company_domains_keep_distinct_subdomains():
    assert company_key("HTTP://WWW.ACME.EXAMPLE/team/?a=1") == company_key("acme.example/") == "acme.example"
    assert company_key("division.acme.example") != company_key("acme.example")
    for value in (None, "-", "Not a website", "ada@acme.example", "ftp://acme.example", "https://acme.example:wrong"):
        assert company_key(value) is None


def test_seed_exact_headers_custom_columns_duplicates_and_restart(tmp_path):
    workspace = WorkspaceStore(tmp_path / "workspaces")
    special = 'Account "priority"'
    record = source(**{special: "001"})
    workspace.save("general", {"records": [record, record], "custom_columns": [special]})
    store = LeadReferenceStore(tmp_path / "db.sqlite3")
    info = store.seed_workspaces(workspace)
    assert (info.count, info.added) == (2, 2)
    with sqlite3.connect(store.path) as db:
        assert [r[1] for r in db.execute('PRAGMA table_info(lead_reference)')] == list(STANDARD_HEADERS) + [special]
        db.row_factory = sqlite3.Row
        saved = dict(db.execute('SELECT * FROM lead_reference LIMIT 1').fetchone())
        assert all(saved[key] == value for key, value in record.items())
    assert store.seed_workspaces(workspace).added == 0
    assert store.add_records([record], [special]).skipped == 1
    assert workspace.load("general")["records"] == [record, record]


def test_seed_uses_unsaved_active_rows_and_rolls_back_corrupt_workspace(tmp_path):
    workspace = WorkspaceStore(tmp_path / "workspaces")
    workspace.save("general", {"records": [source(**{"Job Title": "Old"})]})
    store = LeadReferenceStore(tmp_path / "db.sqlite3")
    assert store.seed_workspaces(workspace, active_key="general", active_records=[source()]).count == 1
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT "Job Title" FROM lead_reference').fetchone()[0] == "Director"
    broken = workspace.directory(workspace.key("broken"))
    broken.mkdir(parents=True)
    (broken / "worksheet.json.gz").write_bytes(b"broken")
    another = LeadReferenceStore(tmp_path / "other.sqlite3")
    with pytest.raises(ValueError):
        another.seed_workspaces(workspace)
    with sqlite3.connect(another.path) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()


def test_prospect_and_company_columns_use_separate_keys(tmp_path):
    store = reference(tmp_path, [source(), source(**{"Prospect LinkedIn Link": "linkedin.com/in/other", "Business Email ID": "other@beta.example",
                                                    "Company Website": "beta.example", "Company Name": "Beta", "Industry": "Finance"})])
    target = {"Prospect LinkedIn Link": "linkedin.com/in/ada-example", "Company Website": "beta.example"}
    plan = store.plan([target], ["Business Email ID", "Company Name", "Industry", "Zip Code"], [0], workspace_key="general")
    assert plan.edits == {(0, "Business Email ID"): "ada@acme.example", (0, "Company Name"): "Beta",
                          (0, "Industry"): "Finance", (0, "Zip Code"): "00123"}
    assert target == {"Prospect LinkedIn Link": "linkedin.com/in/ada-example", "Company Website": "beta.example"}


def test_company_only_match_never_populates_someone_elses_email(tmp_path):
    store = reference(tmp_path)
    plan = store.plan([{"Company Website": "acme.example"}], ["Business Email ID", "Company Name"], [0], workspace_key="general")
    assert plan.edits == {(0, "Company Name"): "Acme"}
    assert plan.counts["invalid_key"] == 1


def test_every_requested_field_and_only_selected_columns(tmp_path):
    saved = source(**{field: f"Saved {field}" for field in PROSPECT_FIELDS + COMPANY_FIELDS if field != "Company Website"})
    store = reference(tmp_path, [saved])
    target = {"Prospect LinkedIn Link": "linkedin.com/in/ada-example", "Company Website": "acme.example", "Notes": "Keep me"}
    fields = list(PROSPECT_FIELDS + COMPANY_FIELDS)
    plan = store.plan([target], fields, [0], workspace_key="general", overwrite=True)
    assert set(plan.edits) == {(0, field) for field in fields}
    assert all(plan.edits[0, field] == saved[field] for field in fields)
    assert target["Notes"] == "Keep me"
    for fields in ([], ["Notes"], ["QA Status"], ["Prospect LinkedIn Link"]):
        with pytest.raises(ValueError):
            store.plan([target], fields, [0], workspace_key="general")


def test_fill_blanks_overwrite_and_empty_sources_never_erase(tmp_path):
    store = reference(tmp_path)
    target = source(**{"Job Title": "Manager", "Phone Number": "Keep phone", "Revenue": "Keep revenue", "Zip Code": "-"})
    plan = store.plan([target], ["Job Title", "Revenue", "Zip Code"], [0], workspace_key="general")
    assert plan.edits == {(0, "Zip Code"): "00123"}
    assert plan.counts["existing"] == 2
    replace = store.plan([target], ["Job Title", "Revenue"], [0], workspace_key="general", overwrite=True)
    assert replace.edits == {(0, "Job Title"): "Director"}
    assert replace.counts["empty_source"] == 1


def test_duplicates_use_consensus_per_field_and_report_conflicts(tmp_path):
    store = reference(tmp_path, [source(), source(**{"Business Email ID": "different@acme.example", "Phone Number": "-"})])
    target = {"Prospect LinkedIn Link": "linkedin.com/in/ada-example", "Company Website": "acme.example"}
    plan = store.plan([target], ["Business Email ID", "Phone Number", "Company Name"], [0], workspace_key="general")
    assert plan.edits == {(0, "Phone Number"): "+1 202 555 0100", (0, "Company Name"): "Acme"}
    assert plan.counts["conflict"] == 1
    assert "Lead row 1" in plan.details()


def test_unmatched_and_direct_database_edits_are_visible(tmp_path):
    store = reference(tmp_path)
    with sqlite3.connect(store.path) as db:
        db.execute('UPDATE lead_reference SET "Job Title"=?', ("Updated title",))
    rows = [{"Prospect LinkedIn Link": "linkedin.com/in/ada-example"}, {"Prospect LinkedIn Link": "linkedin.com/in/absent"}]
    plan = store.plan(rows, ["Job Title"], [0, 1], workspace_key="general")
    assert plan.edits == {(0, "Job Title"): "Updated title"}
    assert plan.counts["unmatched"] == 1
    assert rows[0].get("Job Title") is None


def test_population_undo_redo_persistence_and_stale_guard(tmp_path):
    controller = ApplicationController()
    controller.lead_reference = reference(tmp_path)
    controller.data_manager.append_record({"Prospect LinkedIn Link": "linkedin.com/in/ada-example", "Company Website": "acme.example"})
    plan = controller.lead_reference.plan(controller.data_manager.records, ["Business Email ID", "Company Name"], [0], workspace_key=controller.workspace_key)
    assert controller.apply_database_population(plan)
    assert len(controller.history.undo_stack) == 1
    assert controller.data_manager.records[0]["QA Status"] == "Needs validation"
    controller.save_workspace()
    restored = ApplicationController()
    assert restored.data_manager.records[0]["Business Email ID"] == "ada@acme.example"
    assert controller.undo_edit()
    assert controller.data_manager.records[0]["Business Email ID"] == "-"
    assert controller.redo_edit()
    assert controller.data_manager.records[0]["Company Name"] == "Acme"
    with pytest.raises(ValueError, match="worksheet changed"):
        controller.apply_database_population(plan)
    plan = controller.lead_reference.plan(controller.data_manager.records, ["Job Title"], [0], workspace_key="different-workspace")
    with pytest.raises(ValueError, match="worksheet changed"):
        controller.apply_database_population(plan)


def test_column_dialog_asks_every_time_and_empty_scopes_are_disabled(qt, tmp_path):
    scopes = {"all": [0, 1], "visible": [1], "selected": []}
    info = ReferenceInfo(tmp_path / "db.sqlite3", 2)
    first = PopulateColumnsDialog(None, info, scopes)
    assert first.selected_columns() == []
    assert not first.submit.isEnabled()
    first.fields["Business Email ID"].setChecked(True)
    assert first.submit.isEnabled()
    assert first.selected_rows() == [1]
    first.scope.setCurrentIndex(first.scope.findData("selected"))
    assert not first.submit.isEnabled()
    first.reject()
    second = PopulateColumnsDialog(None, info, scopes)
    assert not second.selected_columns()
    assert not second.overwrite.isChecked()
    first.close(); second.close()


def test_full_async_population_with_filtered_sorted_source_rows(qt, tmp_path):
    with patch.object(MainWindow, "_offer_recovery"), patch.object(MainWindow, "refresh_qwen_status"):
        window = MainWindow()
        try:
            window.autosave_timer.stop()
            controller = window.controller
            controller.lead_reference = reference(tmp_path)
            controller.data_manager.append_record({"First Name": "Zed", "Company Website": "other.example"})
            controller.data_manager.append_record({"First Name": "Ada", "Prospect LinkedIn Link": "linkedin.com/in/ada-example", "Company Website": "acme.example"})
            window._refresh_all()
            page = window.leads_page
            page.table.sortByColumn(controller.data_manager.headers.index("First Name"), Qt.SortOrder.AscendingOrder)
            page.search.setText("Ada")
            page.table.setCurrentIndex(page.proxy.index(0, 0))
            assert page.selected_rows() == [1]
            window.controller.settings.appearance_mode = "Light"
            window.apply_theme()
            window.resize(1366, 800); window.show(); window.navigate("leads"); qt.processEvents()
            captures = Path(__file__).resolve().parents[1] / "TestArtifacts"
            results, errors = [], []
            def choose(dialog):
                assert dialog.selected_columns() == []
                dialog.fields["Business Email ID"].setChecked(True)
                dialog.fields["Company Name"].setChecked(True)
                dialog.show(); qt.processEvents()
                assert dialog.grab().save(str(captures / "populate_database_dialog.png"))
                dialog.accept()
                return QDialog.DialogCode.Accepted
            with patch.object(PopulateColumnsDialog, "exec", choose), patch.object(QMessageBox, "exec", lambda box: results.append(box.text())), patch.object(window, "_worker_error", errors.append):
                page.populate_button.click()
                deadline = time.monotonic() + 12
                while not (results or errors) and time.monotonic() < deadline:
                    qt.processEvents()
                    time.sleep(0.01)
            assert not errors
            assert results and "Populated 2 cells in 1 of 1 leads" in results[0]
            assert controller.data_manager.records[0]["Business Email ID"] == "-"
            assert controller.data_manager.records[1]["Business Email ID"] == "ada@acme.example"
            saved = controller.workspace_store.load(controller.workspace_key)
            assert saved["records"][1]["Company Name"] == "Acme"
            assert page.populate_button.isEnabled()
            assert window.grab().save(str(captures / "populate_database_workspace.png"))
        finally:
            window.thread_pool.waitForDone(5000)
            qt.processEvents()
            window.close(); qt.processEvents()
