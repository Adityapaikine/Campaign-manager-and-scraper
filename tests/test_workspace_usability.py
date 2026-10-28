from pathlib import Path
import time
from unittest.mock import patch

import pandas as pd
import pytest
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from app.constants import MISSING_VALUE
from app.core.campaign_models import CampaignProfile, CampaignRule
from app.core.column_filter import matches_condition
from app.core.reference_lists import available_fields
from app.ui_qt.controller import ApplicationController
from app.ui_qt.dialogs.filter_dialog import ColumnFilterDialog
from app.ui_qt.dialogs.lead_import_dialog import LeadImportDialog
from app.ui_qt.dialogs.workspace_dialogs import ReferenceManagerDialog
from app.ui_qt.main_window import MainWindow
from app.ui_qt.pages.leads_page import LeadsPage
from app.ui_qt.widgets.lead_table import LeadFilterProxyModel, LeadTableModel


def lead(index=0, company="Acme", domain="acme.example", **updates):
    return {"First Name": f"Person{index}", "Last Name": "Example", "Company Name": company,
            "Company Website": domain, "Business Email ID": f"person{index}@{domain}",
            "Country": "India", **updates}


def controller_with_rows(rows):
    controller = ApplicationController()
    for record in rows:
        controller.data_manager.append_record(record)
    return controller


def table_for(controller):
    model = LeadTableModel(controller)
    proxy = LeadFilterProxyModel(controller)
    proxy.setSourceModel(model)
    return model, proxy


def test_per_column_filters_combine_search_and_keep_empty_selection(qt):
    controller = controller_with_rows([lead(0), lead(1, Country="USA"), lead(2, "Beta", "beta.example"),
                                       lead(3, "ACME", "acme.example"), lead(4, "(Blanks)", "x.example"),
                                       lead(5, "-", "y.example")])
    _, proxy = table_for(controller)
    company = controller.data_manager.headers.index("Company Name")
    country = controller.data_manager.headers.index("Country")
    proxy.set_column_filter(company, {"acme"})
    assert proxy.rowCount() == 3
    proxy.set_column_filter(country, {"India"})
    assert proxy.rowCount() == 2
    assert set(proxy.column_values(company)) == {"Acme", "Beta", "(Blanks)", ""}
    proxy.set_column_filter(country, set())
    assert proxy.rowCount() == 0
    proxy.set_column_filter(country, None)
    assert proxy.rowCount() == 3
    proxy.set_column_filter(company, {""})
    assert proxy.rowCount() == 1
    assert proxy.mapToSource(proxy.index(0, 0)).row() == 5
    proxy.set_column_filter(company, {"(Blanks)"})
    assert proxy.mapToSource(proxy.index(0, 0)).row() == 4
    proxy.clear_filters()
    proxy.set_search("Beta")
    assert proxy.rowCount() == 1


@pytest.mark.parametrize("value,rule,expected", [
    ("Alpha Company", {"type":"text", "operator":"contains", "value":"COMP"}, True),
    ("Alpha Company", {"type":"text", "operator":"equals", "value":"Al*?"}, True),
    ("10", {"type":"number", "operator":"gt", "value":"9"}, True),
    ("1,200", {"type":"number", "operator":"equals", "value":"1200"}, True),
    ("NaN", {"type":"number", "operator":"gt", "value":"0"}, False),
    ("21-Oct-2026", {"type":"date", "operator":"gte", "value":"2026-10-20"}, True),
    ("", {"type":"text", "operator":"blank"}, True),
    ("-", {"type":"text", "operator":"not_blank"}, False),
])
def test_filter_conditions(value, rule, expected):
    assert matches_condition(value, rule) == expected


def test_filter_popup_search_select_none_and_cancel(qt):
    dialog = ColumnFilterDialog(None, "Company", ["Acme", "Beta", ""], set())
    assert dialog.selected_values() == set()
    dialog.select_all.click()
    dialog.search.setText("Beta")
    assert dialog.selected_values() == {"beta"}
    dialog.clear_all.click()
    assert dialog.selected_values() == set()
    dialog.reject()
    assert not dialog.result()


def test_column_header_dropdown_and_filter_indicator(qt):
    controller = controller_with_rows([lead(0), lead(1, "Beta", "beta.example")])
    page = LeadsPage(controller); page.resize(1100, 720); page.show()
    page.view_selector.setCurrentText("Research")
    column = controller.data_manager.headers.index("Company Name")
    table = page.frozen_table
    header = table.horizontalHeader()
    accepted = []
    def choose():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, ColumnFilterDialog):
            dialog.search.setText("Beta")
            accepted.append(True)
            dialog.accept()
    timer = QTimer(); timer.timeout.connect(choose); timer.start(20)
    try:
        point = QPoint(header.sectionViewportPosition(column) + header.sectionSize(column) - 12, header.height() // 2)
        QTest.mouseClick(header.viewport(), Qt.MouseButton.LeftButton, pos=point)
        assert accepted
        assert len(page.visible_rows()) == 1
        assert page.visible_rows() == [1]
        assert column in header.filtered_columns
        assert "Company Name" in page.filter_hint.text()
    finally:
        timer.stop(); page.close()


def test_numeric_sort_and_selected_source_rows(qt):
    controller = controller_with_rows([lead(0, Revenue="100"), lead(1, Revenue="9"), lead(2, Revenue="20")])
    page = LeadsPage(controller)
    column = controller.data_manager.headers.index("Revenue")
    page.table.sortByColumn(column, Qt.SortOrder.AscendingOrder)
    assert page.visible_rows() == [1, 2, 0]
    page.table.setCurrentIndex(page.proxy.index(0, column))
    assert page.selected_rows() == [1]
    page.close()


def test_edit_undo_redo_and_stale_qa_is_not_exported(tmp_path, qt):
    controller = controller_with_rows([lead(0)])
    controller.validate()
    model, _ = table_for(controller)
    column = controller.data_manager.headers.index("Company Name")
    assert model.setData(model.index(0, column), "Updated")
    assert controller.data_manager.records[0]["QA Status"] == "Needs validation"
    with pytest.raises(ValueError, match="No leads"):
        controller.export(str(tmp_path / "qualified.xlsx"), scope="qualified")
    assert controller.undo_edit()
    assert controller.data_manager.records[0]["Company Name"] == "Acme"
    assert controller.redo_edit()
    assert controller.data_manager.records[0]["Company Name"] == "Updated"


def test_paste_filtered_rows_undo_append_and_clear(qt):
    controller = controller_with_rows([lead(0), lead(1, "Beta", "beta.example"), lead(2, "Beta", "beta.example")])
    page = LeadsPage(controller)
    company = controller.data_manager.headers.index("Company Name")
    first = controller.data_manager.headers.index("First Name")
    page.proxy.set_column_filter(company, {"Beta"})
    page.table.setCurrentIndex(page.proxy.index(0, first))
    QApplication.clipboard().setText("Changed1\nChanged2\nAdded")
    page.table.paste_clipboard()
    assert [row["First Name"] for row in controller.data_manager.records] == ["Person0", "Changed1", "Changed2", "Added"]
    assert len(controller.history.undo_stack) == 1
    page.undo_edit()
    assert [row["First Name"] for row in controller.data_manager.records] == ["Person0", "Person1", "Person2"]
    page.redo_edit()
    assert len(controller.data_manager.records) == 4
    page.model.clear_cells([page.model.index(1, first)])
    assert controller.data_manager.records[1]["First Name"] == MISSING_VALUE
    page.undo_edit()
    assert controller.data_manager.records[1]["First Name"] == "Changed1"
    page.close()


def test_custom_views_freeze_and_restore(qt):
    controller = controller_with_rows([lead()])
    controller.settings_service.set("lead_column_views", {"Calling": {"columns": ["First Name", "Company Name", "Phone Number"], "freeze": True}})
    page = LeadsPage(controller)
    page.view_selector.setCurrentText("Calling")
    headers = controller.data_manager.headers
    assert not page.frozen_table.isColumnHidden(headers.index("First Name"))
    assert page.table.isColumnHidden(headers.index("First Name"))
    assert not page.table.isColumnHidden(headers.index("Phone Number"))
    assert page.table.isColumnHidden(headers.index("Revenue"))
    page.close()
    reopened = LeadsPage(ApplicationController())
    assert reopened.view_selector.currentText() == "Calling"
    assert reopened.freeze_identity.isChecked()
    reopened.close()


def test_mapping_remembers_manual_choices_and_ignored_columns(qt):
    frame = pd.DataFrame({"Contact": ["Jane"], "Account": ["Acme"], "IgnoreMe": ["x"]})
    controller = ApplicationController()
    dialog = LeadImportDialog(None, {"Data": frame}, controller.data_manager.headers)
    dialog._boxes["Contact"].setCurrentText("First Name")
    dialog._boxes["IgnoreMe"].setCurrentText("(Ignore)")
    dialog.save_mapping()
    reopened = LeadImportDialog(None, {"Data": frame}, controller.data_manager.headers)
    assert reopened.mapping()["Contact"] == "First Name"
    assert "IgnoreMe" not in reopened.mapping()
    assert "restored" in reopened.mapping_note.text()
    different = LeadImportDialog(None, {"Data": frame}, available_fields("tal"), reference_kind="tal")
    assert "restored" not in different.mapping_note.text()
    dialog.close(); reopened.close(); different.close()


def test_campaign_workspaces_keep_rows_lists_and_settings_separate(tmp_path):
    controller = controller_with_rows([lead(0, "General", "general.example")])
    tal = tmp_path / "general.csv"; pd.DataFrame({"Company": ["General"]}).to_csv(tal, index=False)
    controller.load_reference(str(tal), "tal")
    profile = CampaignProfile("alpha", "Alpha campaign", str(tmp_path))
    controller.campaign_store.save(profile)
    controller.activate_campaign(profile)
    assert controller.data_manager.records == []
    assert controller.tal_data is None
    controller.data_manager.append_record(lead(1, "Alpha", "alpha.example"))
    campaign_list = tmp_path / "alpha.csv"; pd.DataFrame({"Company": ["Alpha"]}).to_csv(campaign_list, index=False)
    controller.load_reference(str(campaign_list), "tal")
    controller.settings.minimum_email_confidence = 88
    controller.save_settings()
    controller.validate()
    restored = ApplicationController()
    assert restored.active_campaign.campaign_id == "alpha"
    assert restored.data_manager.records[0]["Company Name"] == "Alpha"
    assert restored.tal_data.source_name == "alpha.csv"
    assert restored.settings.minimum_email_confidence == 88
    restored.switch_to_general()
    assert restored.data_manager.records[0]["Company Name"] == "General"
    assert restored.tal_data.source_name == "general.csv"
    assert restored.settings.minimum_email_confidence == 75
    restored.activate_campaign(profile)
    assert restored.data_manager.records[0]["Company Name"] == "Alpha"


def test_subset_validation_keeps_unrelated_results_and_updates_duplicate_peers():
    controller = controller_with_rows([lead(0), lead(1), lead(2)])
    controller.validate()
    untouched = controller.validation_results[2]
    controller.edit_cells({(1, "Business Email ID"): "person0@acme.example"})
    assert controller.dirty_rows == {0, 1}
    controller.validate(indices=[1])
    assert controller.row_states[0] == controller.row_states[1] == "Duplicate"
    assert controller.validation_results[2] is untouched
    controller.edit_cells({(1, "Business Email ID"): "person1@acme.example"})
    controller.validate(indices=[1])
    assert controller.row_states[0] == controller.row_states[1] == "Valid"
    assert not controller.dirty_rows


def test_campaign_cap_is_still_applied_during_selected_validation(tmp_path):
    controller = ApplicationController()
    profile = CampaignProfile("cap", "Cap", str(tmp_path), rules=[CampaignRule("Company", "domain_cap_default", "max", 1, status="Confirmed")])
    controller.activate_campaign(profile, persist=False)
    for i in range(3): controller.data_manager.append_record(lead(i))
    controller.validate(indices=[2])
    assert controller.last_validation_count == 3
    assert controller.row_states[0] == "Valid"
    assert controller.row_states[1] == controller.row_states[2] == "Invalid"


def test_export_scopes_match_validation_details_and_filter_order(tmp_path):
    controller = controller_with_rows([lead(0), lead(1, "Other", "other.example"), lead(2)])
    path = tmp_path / "tal.csv"; pd.DataFrame({"Company": ["Acme"]}).to_csv(path, index=False)
    controller.load_reference(str(path), "tal")
    controller.validate()
    for scope, expected, indices in (("all", ["Person0", "Person1", "Person2"], None),
                                     ("qualified", ["Person0", "Person2"], None),
                                     ("disqualified", ["Person1"], None),
                                     ("filtered", ["Person2", "Person0"], [2, 0])):
        target = tmp_path / f"{scope}.xlsx"
        controller.export(str(target), scope=scope, row_indices=indices)
        data = pd.read_excel(target, sheet_name="Lead Data")
        details = pd.read_excel(target, sheet_name="Validation Details")
        assert data["First Name"].tolist() == expected
        assert len(data) == len(details)
        assert data["Business Email ID"].tolist() == details["Business Email ID"].tolist()


def test_reference_manager_preview_remove_and_restore_campaign(tmp_path, qt):
    controller = controller_with_rows([lead()])
    path = tmp_path / "reference.csv"; pd.DataFrame({"Company": ["Acme", "Beta"]}).to_csv(path, index=False)
    controller.load_reference(str(path), "tal")
    dialog = ReferenceManagerDialog(None, controller)
    assert dialog.table.rowCount() == 2
    assert "Uploaded" in dialog.info.text()
    dialog.search.setText("Beta")
    assert dialog.table.rowCount() == 1
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        dialog.remove.click()
    assert controller.tal_data is None
    assert controller.validator.tal_validator is None
    assert controller.data_manager.records[0]["QA Status"] == "Needs validation"
    assert list((controller.reference_store.folder / "removed").glob("tal-*.json"))
    dialog.close()


def test_review_panel_and_full_interface_preview(tmp_path, qt):
    with patch.object(MainWindow, "_offer_recovery"), patch.object(MainWindow, "refresh_qwen_status"):
        window = MainWindow()
        try:
            window.resize(1540, 960); window.show(); window.navigate("leads")
            for i in range(18):
                window.controller.data_manager.append_record(lead(i, "Acme" if i % 2 else "Other", "acme.example" if i % 2 else "other.example"))
            path = tmp_path / "Target accounts.csv"; pd.DataFrame({"Company": ["Acme"]}).to_csv(path, index=False)
            window.controller.load_reference(str(path), "tal")
            window.controller.validate()
            window._refresh_all()
            window.leads_page.view_selector.setCurrentText("QA Review")
            window.leads_page.focus_source_cell(0, "QA Status")
            window.validation_drawer.refresh(0)
            assert "Target accounts.csv" in window.validation_drawer.detail.toPlainText()
            assert "Next step:" in window.validation_drawer.detail.toPlainText()
            root = Path(__file__).resolve().parents[1] / "TestArtifacts"
            window.validation_dock.hide(); qt.processEvents()
            window.grab().save(str(root / "workspace_usability.png"))
            window.resize(1120, 740); qt.processEvents()
            assert window.width() <= 1140
            window.grab().save(str(root / "workspace_compact.png"))
            window.controller.settings.appearance_mode = "Dark"; window.apply_theme()
            window.resize(1540, 960); qt.processEvents()
            window.grab().save(str(root / "workspace_dark.png"))
            window.controller.settings.appearance_mode = "Light"; window.apply_theme()
            dialog = ColumnFilterDialog(window, "Company Name", ["Acme", "Other", ""])
            dialog.show(); qt.processEvents(); dialog.grab().save(str(root / "excel_column_filter.png")); dialog.close()
        finally:
            window.close(); qt.processEvents()


def test_keyboard_filter_shortcut_is_scoped_to_focused_table(qt):
    from PySide6.QtGui import QShortcut
    page = LeadsPage(controller_with_rows([lead()]))
    page.view_selector.setCurrentText("QA Review")
    for table in (page.table, page.frozen_table):
        assert all(shortcut.context() == Qt.ShortcutContext.WidgetWithChildrenShortcut for shortcut in table.findChildren(QShortcut))
    page.close()


def test_campaign_paths_follow_copied_portable_folder(tmp_path, monkeypatch):
    import app.core.campaign_manager as manager
    from app.core.campaign_models import CampaignFileInfo
    current = tmp_path / "new PC" / "Data" / "LeadManager" / "campaigns"
    package = current / "123_Example"
    package.mkdir(parents=True)
    (package / "tal.csv").write_text("Company\nAcme\n")
    monkeypatch.setattr(manager, "CAMPAIGN_DIR", current)
    old = tmp_path / "old PC" / "Data" / "LeadManager" / "campaigns" / "123_Example"
    profile = CampaignProfile("portable", "Portable", str(old), files=[CampaignFileInfo("tal.csv", str(old / "tal.csv"), "tal", "csv")])
    store = manager.CampaignProfileStore()
    store.save(profile)
    restored = store.get("portable")
    assert Path(restored.source_root) == package
    assert Path(restored.files[0].absolute_path) == package / "tal.csv"


def test_corrupt_destination_workspace_preserves_open_leads(tmp_path):
    controller = controller_with_rows([lead()])
    profile = CampaignProfile("broken", "Broken", str(tmp_path))
    folder = controller.workspace_store.directory(controller.workspace_store.key(profile.campaign_id))
    folder.mkdir(parents=True)
    path = folder / "worksheet.json.gz"
    path.write_bytes(b"not a valid compressed worksheet")
    with pytest.raises(ValueError, match="preserved"):
        controller.activate_campaign(profile, persist=False)
    assert controller.workspace_key == "general"
    assert controller.data_manager.records[0]["First Name"] == "Person0"
    assert path.read_bytes() == b"not a valid compressed worksheet"


def test_edit_and_keyboard_undo_keep_the_active_cell(qt):
    from PySide6.QtCore import QPersistentModelIndex
    controller = controller_with_rows([lead()])
    page = LeadsPage(controller); page.show()
    column = controller.data_manager.headers.index("First Name")
    page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(0, column)))
    current = QPersistentModelIndex(page.table.currentIndex())
    page.model.setData(page.model.index(0, column), "Edited")
    assert current.isValid()
    assert page.table.currentIndex().data() == "Edited"
    page.table.setFocus()
    QTest.keyClick(page.table, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert page.table.currentIndex().isValid()
    assert page.table.currentIndex().data() == "Person0"
    QTest.keyClick(page.table, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    assert page.table.currentIndex().data() == "Edited"
    page.close()


def test_rows_menu_and_filtered_export_use_visible_source_rows(tmp_path, qt):
    from PySide6.QtWidgets import QToolButton, QFileDialog
    from app.ui_qt.dialogs.workspace_dialogs import ExportChoiceDialog
    def wait_jobs(window):
        deadline = time.monotonic() + 15
        while window._jobs and time.monotonic() < deadline:
            qt.processEvents(); time.sleep(0.01)
        assert not window._jobs
    errors = []
    with patch.object(MainWindow, "_offer_recovery"), patch.object(MainWindow, "refresh_qwen_status"), \
         patch.object(QMessageBox, "critical", side_effect=lambda *args: errors.append(args[2])):
        window = MainWindow(); window.show(); window.navigate("leads")
        try:
            for i in range(4):
                window.controller.data_manager.append_record(lead(i, "Acme" if i % 2 == 0 else "Beta", "acme.example" if i % 2 == 0 else "beta.example"))
            window._refresh_all()
            page = window.leads_page
            column = window.controller.data_manager.headers.index("Company Name")
            page.proxy.set_column_filter(column, {"Beta"})
            page.table.setCurrentIndex(page.proxy.index(0, column))
            menu = next(button.menu() for button in page.findChildren(QToolButton) if button.text() == "Rows")
            next(action for action in menu.actions() if action.text() == "Validate selected rows").trigger()
            wait_jobs(window)
            assert set(window.controller.validation_results) == {1}
            target = tmp_path / "filtered.xlsx"
            def choose_export():
                dialog = QApplication.activeModalWidget()
                if isinstance(dialog, ExportChoiceDialog):
                    dialog.scope.setCurrentIndex(dialog.scope.findData("filtered"))
                    dialog.accept()
            timer = QTimer(); timer.timeout.connect(choose_export); timer.start(20)
            try:
                with patch.object(QFileDialog, "getSaveFileName", return_value=(str(target), "")):
                    window.export_data()
                wait_jobs(window)
            finally:
                timer.stop()
            assert not errors, errors
            assert pd.read_excel(target)["First Name"].tolist() == ["Person1", "Person3"]
        finally:
            window.close(); qt.processEvents()
