"""Behavior and visual checks for the reference-inspired desktop presentation."""
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QDialog, QApplication

from app.ui_qt.controller import ApplicationController
from app.ui_qt.main_window import MainWindow
from app.ui_qt.pages.leads_page import LeadsPage
from app.ui_qt.widgets.lead_details import LeadEditDialog


def populated():
    controller = ApplicationController()
    controller.data_manager.extend([
        {"First Name": "Ada", "Last Name": "Lovelace", "Company Name": "Acme", "Company Website": "acme.example", "Revenue": "100"},
        {"First Name": "Grace", "Last Name": "Hopper", "Company Name": "Beta", "Company Website": "beta.example", "Revenue": "20"},
    ], "Synthetic test data")
    return controller


def test_needs_validation_includes_new_rows_and_excludes_validated(qt):
    controller = populated(); page = LeadsPage(controller)
    try:
        page.status.setCurrentText("Needs validation")
        assert page.visible_rows() == [0, 1]
        controller.validate(indices=[1]); page.refresh()
        assert page.visible_rows() == [0]
        page.model.setData(page.model.index(1, controller.data_manager.headers.index("Job Title")), "Engineer")
        assert set(page.visible_rows()) == {0, 1}
    finally:
        page.close()


def test_details_edit_follows_source_row_and_is_one_undo_operation(qt):
    controller = populated(); page = LeadsPage(controller)
    try:
        column = controller.data_manager.headers.index("Revenue")
        page.table.sortByColumn(column, Qt.SortOrder.AscendingOrder)
        page.table.setCurrentIndex(page.proxy.index(0, column))
        assert page.details_panel.current_row == 1
        assert page.details_panel.name.text() == "Grace Hopper"
        def edit(dialog):
            dialog.fields["Phone Number"].setText("+1 202-555-0101")
            dialog.fields["Dispo"].setText("Follow Up")
            dialog.fields["Comment"].setPlainText("Call next week.\nAsk about the project.")
            return QDialog.DialogCode.Accepted
        with patch.object(LeadEditDialog, "exec", edit):
            page.details_panel.edit_button.click()
        assert controller.data_manager.records[0]["Dispo"] == "-"
        assert controller.data_manager.records[1]["Dispo"] == "Follow Up"
        assert controller.data_manager.records[1]["QA Status"] == "Needs validation"
        assert len(controller.history.undo_stack) == 1
        page.undo_edit()
        assert controller.data_manager.records[1]["Dispo"] == "-"
        page.redo_edit()
        assert controller.data_manager.records[1]["Phone Number"] == "+1 202-555-0101"
        before = [dict(record) for record in controller.data_manager.records]
        with patch.object(LeadEditDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            page.edit_lead(1)
        assert controller.data_manager.records == before
    finally:
        page.close()


def test_details_blank_selection_filters_and_busy_state(qt):
    controller = populated(); page = LeadsPage(controller)
    try:
        page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(1, 0)))
        assert page.details_panel.edit_button.isEnabled()
        page.set_data_busy(True)
        page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(0, 0)))
        assert not page.details_panel.edit_button.isEnabled()
        assert not page.details_panel.recheck_button.isEnabled()
        page.set_data_busy(False)
        assert page.details_panel.edit_button.isEnabled()
        page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(10, 0)))
        assert page.details_panel.current_row is None
        assert not page.details_panel.edit_button.isEnabled()
        assert not page.details_panel.recheck_button.isEnabled()
        page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(1, 0)))
        page.search.setText("Acme")
        assert page.details_panel.current_row != 1
        page.search.setText("no matching person")
        assert page.count_label.text() == "0 of 2 leads"
        assert "No leads match" in page.empty_hint.text()
    finally:
        page.close()


def test_reference_drawer_ignores_blank_rows_and_resets_suggested_field(qt):
    from app.ui_qt.widgets.validation_drawer import ValidationDrawer
    controller = populated(); drawer = ValidationDrawer(controller)
    drawer.suggested_field = "Business Email ID"
    drawer.refresh(0)
    assert drawer.suggested_field == "Company Name"
    drawer.refresh(10)
    assert drawer.current_row is None
    assert not drawer.edit_button.isEnabled()
    assert not drawer.revalidate_button.isEnabled()
    drawer.close()


def test_edit_notes_opens_at_notes_and_saves_through_worksheet_history(qt):
    controller = populated(); page = LeadsPage(controller); page.show()
    page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(0, 0)))
    captured = []
    def save():
        dialog = QApplication.activeModalWidget()
        if isinstance(dialog, LeadEditDialog):
            captured.append(dialog.focusWidget() == dialog.fields["Notes"])
            dialog.fields["Notes"].setPlainText("Follow up next week.")
            dialog.accept()
    timer = QTimer(); timer.timeout.connect(save); timer.start(50)
    try:
        page.details_panel.notes_button.click()
        assert captured == [True]
        assert controller.data_manager.records[0]["Notes"] == "Follow up next week."
        assert len(controller.history.undo_stack) == 1
    finally:
        timer.stop(); page.close()


def test_details_keep_imported_text_literal(qt):
    controller = populated()
    controller.data_manager.records[0].update({"First Name": "<b>Ada</b>", "Comment": "<img src='local.png'>"})
    page = LeadsPage(controller)
    page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(0, 0)))
    assert page.details_panel.name.text() == "<b>Ada</b> Lovelace"
    assert page.details_panel.name.textFormat() == Qt.TextFormat.PlainText
    assert page.details_panel.comment.text() == "<img src='local.png'>"
    page.close()


def test_refresh_keeps_selected_lead_and_workspace_switch_clears_it(qt):
    controller = populated(); page = LeadsPage(controller)
    page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(1, 0)))
    controller.validate(indices=[1]); page.refresh()
    assert page.details_panel.current_row == 1
    assert page.details_panel.name.text() == "Grace Hopper"
    controller.workspace_key = "another-workspace"
    page.refresh()
    assert page.details_panel.current_row is None
    page.close()


def test_full_ui_layout_and_synthetic_previews(qt):
    artifacts = Path(__file__).resolve().parents[1] / "TestArtifacts"
    with patch.object(MainWindow, "_offer_recovery"), patch.object(MainWindow, "refresh_qwen_status"):
        window = MainWindow()
        try:
            window.controller.settings.appearance_mode = "Light"
            window.controller.settings.color_scheme = "Professional Blue"; window.apply_theme()
            window.resize(1680, 960); window.show()
            assert window.stack.currentWidget() == window.scraper_page
            names = [("Rahul", "Kapoor"), ("Priya", "Sharma"), ("Aisha", "Khan"), ("Rohan", "Mehta"), ("Neha", "Verma")]
            dispositions = ["Connected", "Follow Up", "Not Interested", "Connected", "No Answer", "Follow Up", "Busy"]
            comments = ["Interested in the product.", "Call back next week.", "Not looking at the moment.", "Shared details via email.", "Rang, no response.", "Call after 3 PM.", "Will call again."]
            for i in range(28):
                first, last = names[i % len(names)]
                window.controller.data_manager.append_record({
                    "Date": "21-Oct-2026", "Campaign Name": ["Q4 Home Loan", "Credit Card Promo", "Personal Loan"][i % 3],
                    "First Name": first, "Last Name": last, "Agent Name": names[(i+2) % 5][0] + " " + names[(i+2) % 5][1],
                    "Calling Agent Name": names[(i+2) % 5][0] + " " + names[(i+2) % 5][1],
                    "Phone Number": f"+1 202-555-{100+i:04}", "Business Email ID": f"{first.lower()}.{last.lower()}@example.com",
                    "Company Name": "Example Company", "Company Website": "example.com", "Job Title": "Operations Manager",
                    "Dispo": dispositions[i % 7], "Comment": comments[i % 7], "Notes": "Synthetic preview lead. No customer data used.",
                }, source_name="Synthetic UI preview")
            window._refresh_all(); page = window.leads_page
            page.view_selector.setCurrentText("Lead overview")
            window.qwen_badge.setText("Qwen: Off"); window.navigate("leads")
            page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(0, 0)))
            qt.processEvents()
            assert page.details_panel.isVisible()
            assert page.details_button.isChecked()
            assert page.details_panel.name.text() == "Rahul Kapoor"
            assert window.grab().save(str(artifacts / "redesigned_lead_workspace.png"))
            for width, height, filename in ((1366, 800, "redesigned_laptop.png"), (1120, 740, "redesigned_compact.png")):
                window.resize(width, height); qt.processEvents()
                assert window.width() <= width + 10
                assert page.table.viewport().width() > 400
                assert not page.details_panel.isVisible()
                assert window.grab().save(str(artifacts / filename))
            page.details_button.click(); qt.processEvents()
            assert page.details_panel.isVisible()
            assert window.width() <= 1130
            page.details_button.click()
            window.resize(1680, 960); qt.processEvents()
            page.details_button.click(); qt.processEvents()
            window.controller.settings.appearance_mode = "Dark"; window.apply_theme(); qt.processEvents()
            assert window.grab().save(str(artifacts / "redesigned_dark.png"))
            window.controller.settings.appearance_mode = "Light"; window.apply_theme()
            page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(35, 0)))
            assert window.current_source_row() is None
            assert not window.validation_drawer.revalidate_button.isEnabled()
            for key in window.pages:
                window.navigate(key); qt.processEvents()
            window.navigate("scraper"); qt.processEvents()
            assert window.grab().save(str(artifacts / "redesigned_scraper.png"))
        finally:
            window.close(); qt.processEvents()
