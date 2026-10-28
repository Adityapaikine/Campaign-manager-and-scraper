import csv
import gc
import shutil
import time
from unittest.mock import patch

import pandas as pd
import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QPushButton

from app.constants import MISSING_VALUE
from app.core.campaign_models import CampaignProfile
from app.core.reference_list_store import ReferenceListStore
from app.core.reference_lists import load_reference_data
from app.ui_qt.controller import ApplicationController
from app.ui_qt.dialogs.lead_import_dialog import LeadImportDialog
from app.ui_qt.main_window import MainWindow
from app.ui_qt.widgets.lead_table import LeadFilterProxyModel, LeadTableModel


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([header, *rows])
    return str(path)


def lead(company="Acme", domain="acme.example", email="jane@acme.example", **updates):
    row = {"First Name": "Jane", "Last Name": "Doe", "Company Name": company,
           "Company Website": domain, "Business Email ID": email,
           "Prospect LinkedIn Link": "https://www.linkedin.com/in/jane-doe"}
    row.update(updates)
    return row


def upload_lists(controller, tmp_path):
    tal = write_csv(tmp_path / "targets.csv", ["Account", "Website"], [["Acme", "acme.example"]])
    suppression = write_csv(tmp_path / "blocked.csv", ["Email"], [["blocked@other.example"]])
    controller.load_reference(tal, "tal")
    controller.load_reference(suppression, "suppression")
    return tal, suppression


@pytest.mark.parametrize("company,domain,email,status,reason", [
    ("Acme", "acme.example", "jane@acme.example", "Valid", "Phase-3 validation passed"),
    ("Other", "other.example", "jane@other.example", "Disqualified", "Tal not Mapped"),
    ("Other", "other.example", "blocked@other.example", "Disqualified", "Suppression matched"),
    ("Acme", "acme.example", "blocked@other.example", "Disqualified", "Suppression matched"),
    ("-", "-", "-", "Disqualified", "Tal not Mapped"),
])
def test_validation_writes_requested_cells_and_checkpoint(tmp_path, company, domain, email, status, reason):
    controller = ApplicationController()
    upload_lists(controller, tmp_path)
    row = controller.data_manager.append_record(lead(company, domain, email))
    controller.validate()
    assert (row["QA Status"], row["Primary Reason"]) == (status, reason)
    recovered = ApplicationController()
    recovered.recover(controller.checkpoints.latest())
    assert recovered.data_manager.records[0]["QA Status"] == status
    assert recovered.data_manager.records[0]["Primary Reason"] == reason


def test_saved_lists_survive_restart_source_removal_new_session_and_relocation(tmp_path):
    controller = ApplicationController()
    paths = upload_lists(controller, tmp_path)
    for path in paths:
        from pathlib import Path
        Path(path).rename(Path(path).with_suffix(".moved"))
    restarted = ApplicationController()
    assert restarted.tal_data.count == restarted.suppression_data.count == 1
    assert "targets.csv (1 rows, saved)" in restarted.reference_summary()
    restarted.new_session()
    row = restarted.data_manager.append_record(lead("Other", "other.example", "blocked@other.example"))
    restarted.validate()
    assert row["Primary Reason"] == "Suppression matched"
    moved = tmp_path / "another PC" / "reference_lists"
    shutil.copytree(controller.reference_store.folder, moved)
    with patch("app.ui_qt.controller.ReferenceListStore", return_value=ReferenceListStore(moved)):
        relocated = ApplicationController()
    assert relocated.tal_data.count == relocated.suppression_data.count == 1


def test_replacement_and_failed_upload_keep_other_list_and_clear_old_result(tmp_path):
    controller = ApplicationController()
    upload_lists(controller, tmp_path)
    row = controller.data_manager.append_record(lead("Other", "other.example", "jane@other.example"))
    controller.validate()
    assert row["Primary Reason"] == "Tal not Mapped"
    bad = write_csv(tmp_path / "bad.csv", ["Unrelated"], [["value"]])
    with pytest.raises(ValueError):
        controller.load_reference(bad, "tal")
    assert ApplicationController().tal_data.source_name == "targets.csv"
    good = write_csv(tmp_path / "new-targets.csv", ["Website"], [["other.example"]])
    with patch.object(controller.reference_store, "save", side_effect=OSError("Disk full")):
        with pytest.raises(OSError):
            controller.load_reference(good, "tal")
    assert controller.tal_data.source_name == "targets.csv"
    controller.load_reference(good, "tal")
    controller.validate()
    assert row["QA Status"] == "Valid"
    assert row["Primary Reason"] != "Tal not Mapped"
    assert controller.suppression_data.source_name == "blocked.csv"
    assert ApplicationController().tal_data.source_name == "new-targets.csv"


def test_no_lists_does_not_disqualify_and_new_upload_enables_matching(tmp_path):
    controller = ApplicationController()
    row = controller.data_manager.append_record(lead())
    controller.validate()
    assert row["QA Status"] == "Valid"
    controller.settings.require_tal_match = controller.settings.enable_suppression = False
    upload_lists(controller, tmp_path)
    assert controller.validator.require_tal_match and controller.validator.enable_suppression
    restarted = ApplicationController()
    assert restarted.settings.require_tal_match and restarted.settings.enable_suppression


def test_corrupt_saved_list_blocks_validation_until_replaced(tmp_path):
    controller = ApplicationController()
    paths = upload_lists(controller, tmp_path)
    (controller.reference_store.folder / "tal.json").write_text("invalid json")
    restarted = ApplicationController()
    restarted.data_manager.append_record(lead())
    with pytest.raises(ValueError, match="Upload that list again"):
        restarted.validate()
    restarted.load_reference(paths[0], "tal")
    restarted.validate()
    assert not restarted.reference_errors


def test_exports_visible_columns_and_disqualified_filter(tmp_path, qt):
    controller = ApplicationController()
    upload_lists(controller, tmp_path)
    for row in [lead(), lead("Other", "other.example", "jane@other.example")]:
        controller.data_manager.append_record(row)
    controller.validate()
    target = tmp_path / "results.xlsx"
    controller.export(str(target))
    df = pd.read_excel(target)
    assert df.loc[1, "QA Status"] == "Disqualified"
    assert df.loc[1, "Primary Reason"] == "Tal not Mapped"
    model = LeadTableModel(controller)
    assert model.data(model.index(1, controller.data_manager.headers.index("QA Status"))) == "Disqualified"
    proxy = LeadFilterProxyModel(controller)
    proxy.setSourceModel(model)
    proxy.set_status("Disqualified")
    assert proxy.rowCount() == 1


def test_manual_lists_stay_in_their_workspace_when_campaign_is_activated(tmp_path):
    controller = ApplicationController()
    upload_lists(controller, tmp_path)
    profile = CampaignProfile(campaign_id="test", campaign_name="Test", source_root=str(tmp_path))
    with patch("app.ui_qt.workspace_workflow.build_campaign_validators", return_value=(None, None, [])):
        controller.activate_campaign(profile, persist=False)
    assert controller.validator.tal_validator is None
    assert controller.validator.suppression_validator is None
    controller.switch_to_general()
    assert controller.validator.tal_validator.data.source_name == "targets.csv"
    assert controller.validator.suppression_validator.data.source_name == "blocked.csv"


def test_fuzzy_tal_stays_manual_review(tmp_path):
    controller = ApplicationController()
    controller.load_reference(write_csv(tmp_path / "fuzzy.csv", ["Company"], [["Acme Industries"]]), "tal")
    row = controller.data_manager.append_record(lead("Acme Industriez", "other.example", "jane@other.example"))
    controller.validate()
    assert controller.validation_results[0].tal_status == "Possible Match"
    assert row["QA Status"] == "Manual Review"


def test_cancelled_validation_saves_only_completed_rows(tmp_path):
    from app.core.batch_control import BatchControl
    controller = ApplicationController()
    upload_lists(controller, tmp_path)
    for i in range(60):
        controller.data_manager.append_record(lead("Other", "other.example", f"person{i}@other.example"))
    control = BatchControl()
    controller.validate(control=control, progress_callback=lambda done, total: control.cancel())
    rows = controller.data_manager.records
    assert controller.validator.last_run_cancelled
    assert len(controller.validation_results) == 25
    assert all(row["QA Status"] == "Disqualified" for row in rows[:25])
    assert all(row["QA Status"] == MISSING_VALUE for row in rows[25:])
    assert controller.checkpoints.latest().payload["records"][24]["Primary Reason"] == "Tal not Mapped"


def test_duplicate_mapping_does_not_replace_saved_list(tmp_path):
    controller = ApplicationController()
    upload_lists(controller, tmp_path)
    path = write_csv(tmp_path / "duplicate.csv", ["Account", "Alias"], [["New", "Other"]])
    with pytest.raises(ValueError, match="Two source columns"):
        controller.load_reference(path, "tal", {"Account": "Company Name", "Alias": "Company Name"})
    assert ApplicationController().tal_data.source_name == "targets.csv"


def test_replacing_suppression_removes_old_disqualification(tmp_path):
    controller = ApplicationController()
    upload_lists(controller, tmp_path)
    row = controller.data_manager.append_record(lead(email="blocked@other.example"))
    controller.validate()
    assert row["Primary Reason"] == "Suppression matched"
    path = write_csv(tmp_path / "new-suppression.csv", ["Email"], [["someone@else.example"]])
    controller.load_reference(path, "suppression")
    controller.validate()
    assert row["QA Status"] != "Disqualified"
    assert row["Primary Reason"] != "Suppression matched"
    assert ApplicationController().tal_data.source_name == "targets.csv"


def wait_for_jobs(qt, window):
    until = time.monotonic() + 15
    while window._jobs and time.monotonic() < until:
        qt.processEvents()
        time.sleep(0.01)
    assert not window._jobs, "The reference upload or validation did not finish"


def test_actual_upload_mapping_restart_and_validate_button(tmp_path, qt):
    tal = tmp_path / "TAL.xlsx"
    with pd.ExcelWriter(tal) as writer:
        pd.DataFrame(columns=["Account"]).to_excel(writer, sheet_name="Empty template", index=False)
        pd.DataFrame({"Account": ["Acme"], "Website": ["acme.example"]}).to_excel(writer, sheet_name="Accounts", index=False)
    suppression = write_csv(tmp_path / "Suppression.csv", ["Email"], [["blocked@other.example"]])
    accepted, errors = [], []
    with patch.object(MainWindow, "_offer_recovery"), patch.object(MainWindow, "refresh_qwen_status"), \
         patch.object(QMessageBox, "critical", side_effect=lambda *args: errors.append(args[2])):
        window = MainWindow()
        timer = QTimer()
        def accept_mapping():
            dialog = QApplication.activeModalWidget()
            if isinstance(dialog, LeadImportDialog):
                accepted.append((dialog.reference_kind, dialog.sheet_selector.currentData()))
                dialog.import_button.click()
        timer.timeout.connect(accept_mapping)
        timer.start(20)
        try:
            window.show()
            window.navigate("leads")
            for kind, source in (("tal", str(tal)), ("suppression", suppression)):
                with patch.object(QFileDialog, "getOpenFileName", return_value=(source, "")):
                    window.load_reference(kind)
                    wait_for_jobs(qt, window)
            assert accepted == [("tal", "Accounts"), ("suppression", "Suppression.csv")]
            assert "TAL.xlsx (1 rows, saved)" in window.leads_page.reference_label.text()
        finally:
            timer.stop()
            window.close()
            qt.processEvents()
        window = MainWindow()
        try:
            window.show()
            window.navigate("leads")
            assert window.controller.tal_data.count == window.controller.suppression_data.count == 1
            for row in (lead("Other", "other.example", "jane@other.example"),
                        lead("Other", "other.example", "blocked@other.example")):
                window.controller.data_manager.append_record(row)
            window.leads_page.refresh()
            next(button for button in window.leads_page.findChildren(QPushButton) if button.text() == "Validate").click()
            wait_for_jobs(qt, window)
            assert not errors, errors
            rows = window.controller.data_manager.records
            assert [row["QA Status"] for row in rows] == ["Disqualified", "Disqualified"]
            assert [row["Primary Reason"] for row in rows] == ["Tal not Mapped", "Suppression matched"]
            model = window.leads_page.model
            reason_column = window.controller.data_manager.headers.index("Primary Reason")
            assert model.data(model.index(0, reason_column)) == "Tal not Mapped"
            assert model.data(model.index(1, reason_column)) == "Suppression matched"
            window.resize(1540, 940)
            window.leads_page.table.scrollTo(window.leads_page.proxy.mapFromSource(model.index(0, reason_column)))
            qt.processEvents()
            from pathlib import Path
            image_path = Path(__file__).resolve().parents[1] / "TestArtifacts" / "saved_reference_validation.png"
            assert window.grab().save(str(image_path))
        finally:
            window.close()
            qt.processEvents()
            gc.collect()
