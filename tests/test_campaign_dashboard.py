from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QDialog

from app.core.campaign_dashboard import CampaignProgress, CampaignTrackingStore, campaign_progress, count_value, daily_target, parse_date
from app.core.campaign_models import CampaignProfile, CampaignRule
from app.ui_qt.controller import ApplicationController
from app.ui_qt.dialogs.campaign_plan_dialog import CampaignPlanDialog
from app.ui_qt.pages.dashboard_page import DashboardPage


def profile(c, cid, name=None, rules=None):
    p = CampaignProfile(cid, name or cid, "", rules=rules or [])
    c.campaign_store.save(p); return p


def leads_payload(count, qualified=0, disqualified=0):
    records, states = [], {}
    for i in range(count):
        records.append({"First Name": f"Person {i}", "QA Status": "Disqualified" if qualified <= i < qualified+disqualified else "Qualified" if i < qualified else "-"})
        states[str(i)] = "Valid" if i < qualified else "Invalid" if i < qualified+disqualified else "Needs validation"
    return {"records": records, "row_states": states, "dirty_rows": list(range(qualified+disqualified, count))}


def saved(c, cid, count, qualified=0, disqualified=0):
    c.workspace_store.save(c.workspace_store.key(cid), leads_payload(count, qualified, disqualified))


@pytest.mark.parametrize("allocation,start,end,expected", [
    (100, date(2026,10,1), date(2026,10,3), 34), (100, date(2026,10,1), date(2026,10,1), 100),
    (0, date(2026,10,1), date(2026,10,5), 0), (29, date(2024,2,1), date(2024,2,29), 1),
    (10, date(2026,10,5), date(2026,10,1), None), (100, None, date(2026,10,3), None),
    (None, date(2026,10,1), date(2026,10,3), None),
])
def test_inclusive_calendar_daily_target(allocation, start, end, expected):
    assert daily_target(allocation, start, end) == expected


def test_rules_supply_defaults_without_guessing_deliveries_or_status():
    c = ApplicationController()
    profile(c, "A", rules=[CampaignRule("Campaign", "lead_goal", "equals", "1,000"),
                            CampaignRule("Campaign", "start_date", "equals", "01-Oct-2026"),
                            CampaignRule("Campaign", "end_date", "equals", "2026-10-10")])
    profile(c, "B", rules=[CampaignRule("Campaign", "lead_goal", "equals", "999", status="Needs Review")])
    rows, warnings = campaign_progress(c); rows = {r.campaign_id: r for r in rows}
    assert rows["A"].average == 100 and rows["A"].delivered is None and rows["A"].status is None
    assert rows["A"].remaining is None and rows["B"].allocation is None
    assert not warnings


def test_cross_workspace_live_counts_dirty_rows_and_general_mapping():
    c = ApplicationController(); profile(c, "A", "Alpha"); profile(c, "B", "Beta")
    saved(c, "A", 4, 2, 1); saved(c, "B", 5, 3, 1)
    c.data_manager.append_record({"Campaign Name": "Alpha", "QA Status": "Qualified"})
    c.data_manager.append_record({"Campaign Name": "B", "QA Status": "Disqualified"})
    c.data_manager.append_record({"Campaign Name": "Unknown"})
    c.row_states = {0: "Valid", 1: "Invalid"}; c.dirty_rows = {0}
    rows, warnings = campaign_progress(c); rows = {r.campaign_id: r for r in rows}
    assert (rows["A"].total, rows["A"].qualified, rows["A"].disqualified, rows["A"].pending) == (5,2,1,2)
    assert (rows["B"].total, rows["B"].qualified, rows["B"].disqualified) == (6,3,2)
    assert rows[""].total == 1 and warnings
    # The open campaign's unsaved data replaces its old disk snapshot.
    c.workspace_key = c.workspace_store.key("A"); c.data_manager.replace_all([{"First Name": "Unsaved"}])
    c.row_states = {}; c.dirty_rows = {0}
    rows, _ = campaign_progress(c); rows = {r.campaign_id: r for r in rows}
    assert rows["A"].total == 1 and rows["B"].total == 5


def test_duplicate_names_stay_unassigned_and_explicit_cid_resolves():
    c = ApplicationController(); profile(c, "A", "Same"); profile(c, "B", "Same")
    c.data_manager.add_columns(["CID"])
    c.data_manager.append_record({"Campaign Name": "Same"})
    c.data_manager.append_record({"Campaign Name": "Same", "CID": "B"})
    c.data_manager.append_record({"Campaign Name": "B", "CID": "Unknown"})
    rows, _ = campaign_progress(c); rows = {r.campaign_id: r for r in rows}
    assert rows[""].total == 2 and rows["A"].total == 0 and rows["B"].total == 1


def test_corrupt_workspace_is_unavailable_not_zero(tmp_path):
    c = ApplicationController(); profile(c, "A")
    folder = c.workspace_store.directory(c.workspace_store.key("A")); folder.mkdir(parents=True)
    path = folder / "worksheet.json.gz"; path.write_bytes(b"broken snapshot")
    rows, warnings = campaign_progress(c)
    assert rows[0].total is None and warnings and path.read_bytes() == b"broken snapshot"


def test_manual_delivery_status_persistence_and_profile_independence():
    c = ApplicationController(); p = profile(c, "A")
    store = CampaignTrackingStore()
    store.save("A", allocation=100, start=date(2026,10,1), end=date(2026,10,3), delivered=40, status="Paused")
    row = campaign_progress(c)[0][0]
    assert row.remaining == 60 and row.average == 34 and row.status == "Paused"
    assert "30/day" in row.pace_note(date(2026,10,2))
    assert "Past the end date" in row.pace_note(date(2026,10,4))
    c.campaign_store.save(p)
    assert CampaignTrackingStore().all()["A"]["delivered"] == 40
    store.save("A", allocation=100, start=None, end=None, delivered=120, status="Closed")
    assert campaign_progress(c)[0][0].remaining == 0
    with pytest.raises(ValueError): store.save("A", allocation=1, start=date(2026,2,2), end=date(2026,2,1), delivered=0, status="Running")
    with pytest.raises(ValueError): store.save("A", allocation=-1, start=None, end=None, delivered=0, status=None)
    with pytest.raises(ValueError): store.save("A", allocation=1, start=None, end=None, delivered=0, status="Active")
    c.campaign_store.delete("A"); assert "A" not in store.all()


def test_invalid_saved_validation_metadata_is_unavailable():
    c = ApplicationController(); profile(c, "A")
    payload = leads_payload(2); payload["row_states"] = None
    c.workspace_store.save(c.workspace_store.key("A"), payload)
    rows, warnings = campaign_progress(c)
    assert rows[0].total is None and warnings


def test_dashboard_headers_sort_filter_chart_totals_and_edit(qt):
    c = ApplicationController(); profile(c, "A", "Alpha"); profile(c, "B", "Beta")
    saved(c, "A", 12, 8, 2); saved(c, "B", 3, 1, 1)
    store = CampaignTrackingStore()
    for cid, allocation, delivered, state in [("A",100,50,"Running"),("B",20,10,"Paused")]:
        store.save(cid, allocation=allocation, start=date(2026,10,1), end=date(2026,10,10), delivered=delivered, status=state)
    page = DashboardPage(c)
    try:
        assert page.table.columnCount() == 12 and page.table.rowCount() == 2
        page.table.sortItems(5, Qt.SortOrder.AscendingOrder)
        assert page.table.item(0,1).text() == "B"
        assert page.cards["total"].value_label.text() == "15"
        series = page.charts.quality_view.chart().series()[0]
        assert series.sum() == 15
        page.status.setCurrentText("Running")
        assert page.table.rowCount() == 1 and page.cards["total"].value_label.text() == "12"
        assert page.charts.quality_view.chart().series()[0].sum() == 12
        def edit(dialog):
            dialog.allocation.setValue(101); dialog.delivered.setValue(70); dialog.status.setCurrentText("Closed")
            return QDialog.DialogCode.Accepted
        with patch.object(CampaignPlanDialog, "exec", edit): page.edit_plan()
        assert page.table.rowCount() == 0 and store.all()["A"]["delivered"] == 70
        page.status.setCurrentText("All statuses"); page.search.setText("alpha")
        assert page.table.rowCount() == 1 and page.table.item(0,9).text() == "31" and page.table.item(0,10).text() == "11"
        page.search.setText("does not exist"); assert page.table.rowCount() == 0 and not page.edit_button.isEnabled()
    finally: page.close()


def test_plan_preview_and_invalid_dates(qt):
    dialog = CampaignPlanDialog(None, CampaignProgress("A", "Alpha", allocation=100, start=date(2026,10,1), end=date(2026,10,3)))
    assert "34" in dialog.preview.text()
    dialog.end.setDate(QDate(2026,9,1)); dialog.accept()
    assert not dialog.result() and "before" in dialog.error.text()
    dialog.end.setDate(QDate(2026,10,1)); dialog.accept()
    assert dialog.result() and daily_target(dialog.values()["allocation"], dialog.values()["start"], dialog.values()["end"]) == 100
    dialog.close()


def test_counts_and_dates_reject_unknown_values():
    assert count_value("1,000") == 1000 and count_value("1.5") is None and count_value("NaN") is None
    assert parse_date("2026-10-01T12:00:00") == date(2026,10,1)
    assert parse_date("not a date") is None


def test_campaign_dashboard_preview_and_compact_layout(qt):
    from app.ui_qt.main_window import MainWindow
    from PySide6.QtTest import QTest
    artifacts = Path(__file__).resolve().parents[1] / "TestArtifacts"
    with patch.object(MainWindow, "_offer_recovery"), patch.object(MainWindow, "refresh_qwen_status"):
        window = MainWindow()
        try:
            c = window.controller; store = CampaignTrackingStore()
            for i, (name, allocation, delivered, status) in enumerate([
                ("Cloud Infrastructure",500,320,"Running"), ("Enterprise Security",300,120,"Running"),
                ("Finance Leaders",200,200,"Closed"), ("Manufacturing Insights",400,90,"Paused"),
                ("Healthcare Innovation",250,75,"Running"), ("Retail Transformation",150,40,"Running"),
            ], 1):
                cid = f"C-{100+i}"; profile(c, cid, name); saved(c, cid, 180+i*20, 100+i*10, 30)
                store.save(cid, allocation=allocation, delivered=delivered, start=date(2026,10,1), end=date(2026,10,31), status=status)
            window.controller.settings.appearance_mode = "Light"
            window.controller.settings.color_scheme = "Professional Blue"; window.apply_theme()
            window.resize(1680, 960); window.show(); window.navigate("dashboard"); QTest.qWait(100)
            assert window.dashboard_page.table.rowCount() == 6
            assert window.grab().save(str(artifacts / "campaign_dashboard.png"))
            window.resize(1120, 740); QTest.qWait(100)
            assert window.width() <= 1130 and window.height() <= 750
            assert window.grab().save(str(artifacts / "campaign_dashboard_compact.png"))
            window.controller.settings.appearance_mode = "Dark"; window.apply_theme(); window.dashboard_page.refresh(); QTest.qWait(100)
            assert window.grab().save(str(artifacts / "campaign_dashboard_dark.png"))
            dialog = CampaignPlanDialog(window.dashboard_page, window.dashboard_page.rows[0]); dialog.show(); qt.processEvents()
            assert dialog.grab().save(str(artifacts / "campaign_plan_editor.png")); dialog.close()
        finally: window.close(); qt.processEvents()
