from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ai.ai_service import AIServiceConfig, LocalAIService
from app.ai.qwen_runtime import QwenRuntimeManager
from app.constants import MISSING_VALUE
from app.core.activity_history import record_activity
from app.core.campaign_activation import build_campaign_validators
from app.core.campaign_manager import CampaignPackageImporter, CampaignProfileStore
from app.core.campaign_models import CampaignProfile
from app.core.checkpoint_service import CheckpointService, CheckpointSnapshot
from app.core.data_manager import DataManager
from app.core.email_finder import EmailFinder, EmailFindingResult
from app.core.email_run_store import EmailRunStore
from app.core.reference_lists import load_reference_data
from app.core.reference_list_store import ReferenceListStore
from app.core.settings_service import SettingsService
from app.core.lead_reference import LeadReferenceStore
from app.core.database_connections import DatabaseProfiles
from app.core.suppression_validator import SuppressionValidator
from app.core.tal_validator import TALValidator
from app.core.validator import ValidationEngine, ValidationResult
from app.excel.exporter import export_records
from app.excel.importer import import_records
from app.utils.config import EXPORT_DIR, LOG_DIR
from app.utils.logger import logger
from app.ui_qt.workspace_workflow import WorkspaceWorkflow, WORKSPACE_SETTINGS


@dataclass
class PreparedLeadImport:
    records: list[dict[str, str]]
    mapping: dict[str, str]
    custom_columns: list[str]
    source_name: str
    sheet_name: str = ""


@dataclass(slots=True)
class AppSettings:
    require_tal_match: bool = True
    enable_suppression: bool = True
    enable_tal_fuzzy_match: bool = True
    enable_suppression_fuzzy_match: bool = True
    minimum_email_confidence: int = 75
    revalidate_existing_emails: bool = False
    email_search_enabled: bool = False
    email_website_lookup: bool = True
    search_provider_name: str = "Auto"
    email_search_max_workers: int = 4
    email_search_timeout: int = 15
    email_search_retries: int = 2
    email_discovery_cache_days: int = 30
    autosave_interval_seconds: int = 60
    autosave_record_interval: int = 100
    checkpoint_keep_last: int = 5
    export_valid_only: bool = False
    include_validation_details: bool = True
    default_export_folder: str = str(EXPORT_DIR)
    appearance_mode: str = "System"
    color_scheme: str = "Professional Blue"
    outside_tal_color: str = "#FFC7CE"
    suppression_match_color: str = "#FFD59A"
    qwen_enabled: bool = False
    qwen_auto_start: bool = False
    qwen_folder: str = ""
    qwen_executable: str = ""
    qwen_model: str = ""
    qwen_host: str = "127.0.0.1"
    qwen_port: int = 8080
    qwen_extra_args: str = ""
    ai_features_enabled: bool = True
    ai_start_on_demand: bool = True
    ai_cache_enabled: bool = True
    ai_cache_days: int = 180
    ai_min_confidence: float = 0.75
    ai_max_prompt_chars: int = 12000
    ai_max_parallel_calls: int = 1
    ai_request_timeout: int = 90
    ai_campaign_auto_read: bool = True
    qwen_stop_on_exit: bool = True


class ApplicationController(WorkspaceWorkflow):
    """UI-agnostic application state used by the Qt presentation layer.

    The old CustomTkinter window historically owned this state. Moving it here lets
    the Qt UI reuse the same core services without duplicating business logic.
    """

    def __init__(self) -> None:
        self.settings_service = SettingsService()
        self.settings = self._load_settings()
        self.data_manager = DataManager()
        self.lead_reference = LeadReferenceStore()
        self.database_profiles = DatabaseProfiles(self.settings_service)
        self.validator = ValidationEngine(
            require_tal_match=self.settings.require_tal_match,
            enable_suppression=self.settings.enable_suppression,
        )
        self.email_finder = EmailFinder()
        self.campaign_store = CampaignProfileStore()
        self.campaign_importer = CampaignPackageImporter()
        self.checkpoints = CheckpointService(keep_last=self.settings.checkpoint_keep_last)

        self.row_states: dict[int, str] = {}
        self.validation_reasons: dict[int, list[str]] = {}
        self.validation_results: dict[int, ValidationResult] = {}
        self.email_results: dict[int, EmailFindingResult] = {}
        self.active_campaign: CampaignProfile | None = None
        self.tal_data = None
        self.suppression_data = None
        self.reference_store = ReferenceListStore()
        self.reference_errors: dict[str, str] = {}

        self.qwen_runtime = QwenRuntimeManager(
            folder=self.settings.qwen_folder,
            executable=self.settings.qwen_executable,
            model=self.settings.qwen_model,
            host=self.settings.qwen_host,
            port=self.settings.qwen_port,
            extra_args=self.settings.qwen_extra_args,
        )
        self.ai_service = LocalAIService(self.qwen_runtime, self._ai_config())

        active = self.campaign_store.active()
        self._init_workspaces(active)
        if self.settings.qwen_enabled and self.settings.qwen_auto_start:
            # UI startup must not block on model loading. Qt schedules this later.
            pass

    def _load_settings(self) -> AppSettings:
        defaults = AppSettings()
        values = {}
        for name in defaults.__dataclass_fields__:
            values[name] = self.settings_service.get(name, getattr(defaults, name))
        return AppSettings(**values)

    def save_settings(self) -> None:
        values = {name: getattr(self.settings, name) for name in self.settings.__dataclass_fields__}
        self.settings_service.update_many({key: value for key, value in values.items()
                                           if self.active_campaign is None or key not in WORKSPACE_SETTINGS})
        validation_settings = tuple(getattr(self.settings, key) for key in WORKSPACE_SETTINGS[:4])
        if validation_settings != self._validation_settings:
            self.mark_rows_dirty(range(len(self.data_manager.records)))
        self._validation_settings = validation_settings
        self.validator.require_tal_match = bool(self.settings.require_tal_match)
        self.validator.enable_suppression = bool(self.settings.enable_suppression)
        if self.validator.tal_validator is not None:
            self.validator.tal_validator.fuzzy_enabled = bool(self.settings.enable_tal_fuzzy_match)
        if self.validator.suppression_validator is not None:
            try:
                self.validator.suppression_validator.fuzzy_enabled = bool(self.settings.enable_suppression_fuzzy_match)
            except Exception:
                pass
        self.checkpoints.keep_last = max(2, int(self.settings.checkpoint_keep_last))
        self.qwen_runtime.folder = Path(self.settings.qwen_folder).expanduser() if self.settings.qwen_folder else None
        self.qwen_runtime.executable_override = Path(self.settings.qwen_executable).expanduser() if self.settings.qwen_executable else None
        self.qwen_runtime.model_override = Path(self.settings.qwen_model).expanduser() if self.settings.qwen_model else None
        self.qwen_runtime.host = self.settings.qwen_host
        self.qwen_runtime.port = int(self.settings.qwen_port)
        self.qwen_runtime.extra_args = self.settings.qwen_extra_args
        self.qwen_runtime._asset_cache = None
        self.qwen_runtime._resolved_folder_cache = None
        self.ai_service.reconfigure(self._ai_config())
        self.save_workspace()
        record_activity("settings", "Qt application settings updated", values)

    def _ai_config(self) -> AIServiceConfig:
        return AIServiceConfig(
            enabled=bool(self.settings.ai_features_enabled and self.settings.qwen_enabled),
            start_on_demand=bool(self.settings.ai_start_on_demand),
            cache_enabled=bool(self.settings.ai_cache_enabled),
            cache_days=int(self.settings.ai_cache_days),
            minimum_confidence=float(self.settings.ai_min_confidence),
            max_prompt_chars=int(self.settings.ai_max_prompt_chars),
            max_parallel_calls=max(1, int(self.settings.ai_max_parallel_calls)),
            request_timeout=float(self.settings.ai_request_timeout),
        )

    def new_session(self) -> None:
        self.data_manager.clear()
        self.data_manager.custom_columns.clear()
        self.clear_derived_state()
        self.history.clear()
        self.dirty_rows.clear()
        self.save_workspace()
        record_activity("session", "New Qt session created", {})

    def clear_derived_state(self) -> None:
        self.row_states.clear()
        self.validation_reasons.clear()
        self.validation_results.clear()
        self.email_results.clear()
        if hasattr(self, "history"):
            self.history.clear()
        if hasattr(self, "dirty_rows"):
            self.dirty_rows.clear()
            self._pending_dependency_groups.clear()
            self.mark_rows_dirty(range(len(self.data_manager.records)))

    def import_leads(self, path: str, mapping: dict[str, str] | None = None, *, dataframe=None) -> tuple[int, dict[str, str]]:
        return self.apply_lead_import(self.prepare_lead_import(path, mapping, dataframe=dataframe))

    def prepare_lead_import(self, path: str, mapping=None, *, dataframe=None) -> PreparedLeadImport:
        """Validate and normalize off-thread without changing the current worksheet."""
        headers = self.data_manager.headers
        new_columns = list(dict.fromkeys(target for target in (mapping or {}).values() if target not in headers))
        staged = DataManager(custom_columns=list(self.data_manager.custom_columns))
        staged.add_columns(new_columns)
        rows, used_mapping = import_records(path, mapping, custom_columns=staged.custom_columns, dataframe=dataframe)
        staged.extend(rows, source_name=Path(path).name)
        return PreparedLeadImport(staged.records, used_mapping, new_columns, Path(path).name,
                                  str(dataframe.attrs.get("source_sheet", "")) if dataframe is not None else "")

    def apply_lead_import(self, prepared: PreparedLeadImport) -> tuple[int, dict[str, str]]:
        """Commit a complete, validated import on the UI thread."""
        if not prepared.records:
            raise ValueError("No data rows were found; the worksheet was not changed.")
        self.data_manager.add_columns(prepared.custom_columns)
        self.data_manager.records.extend(prepared.records)
        self.recalculate_formulas()
        self.history.clear()
        self._pending_dependency_groups.clear()
        count = len(prepared.records)
        self.clear_derived_state()
        try:
            record_activity("import", f"Imported {count:,} lead(s)", {
                "file": prepared.source_name, "worksheet": prepared.sheet_name, "mapping": prepared.mapping})
        except Exception:
            logger.exception("Leads were imported but activity history could not be saved")
        return count, prepared.mapping

    def ensure_lead_database(self):
        return self.lead_reference.seed_workspaces(
            self.workspace_store, active_key=self.workspace_key,
            active_records=[dict(record) for record in self.data_manager.records],
            active_headers=self.data_manager.headers,
        )

    def add_leads_to_database(self):
        self.ensure_lead_database()
        info = self.lead_reference.add_records(
            [dict(record) for record in self.data_manager.records], self.data_manager.headers)
        self._record_database_activity("Added leads to reference database", {"added": info.added, "skipped": info.skipped})
        return info

    def apply_database_population(self, plan):
        # Source row indices are safe only while the original worksheet is unchanged.
        if self.workspace_key != plan.workspace_key or self.data_manager.records != plan.records:
            raise ValueError("The worksheet changed during the database lookup. Run Populate again; no lookup values were applied.")
        changed = self.edit_cells(plan.edits, "Populate from database", allow_formulas=False)
        if changed:
            self._record_database_activity(plan.summary(), {
                "workspace": self.workspace_key, "columns": list(plan.columns),
                "rows": plan.updated_rows, "cells": len(plan.edits), "replace_existing": plan.overwrite,
                "skipped_cells": plan.counts,
            })
        return changed

    def _record_database_activity(self, summary, details):
        try:
            record_activity("database_lookup", summary, details)
        except Exception:
            logger.exception("Database operation completed but its activity could not be recorded")

    def _configure_reference(self, data) -> None:
        if data.kind == "tal":
            self.tal_data = data
            self.validator.configure_tal(
                TALValidator(data, fuzzy_enabled=self.settings.enable_tal_fuzzy_match),
                require_match=self.settings.require_tal_match,
            )
        else:
            self.suppression_data = data
            self.validator.configure_suppression(
                SuppressionValidator(data, fuzzy_enabled=self.settings.enable_suppression_fuzzy_match),
                enabled=self.settings.enable_suppression,
            )

    def _restore_references(self) -> None:
        for kind in ("tal", "suppression"):
            try:
                data = self.reference_store.load(kind)
                if data is not None:
                    self._configure_reference(data)
            except ValueError as exc:
                self.reference_errors[kind] = str(exc)
                logger.exception("Unable to restore saved %s list", kind)

    def reference_summary(self) -> str:
        parts = []
        for kind, label in (("tal", "TAL"), ("suppression", "Suppression")):
            data = getattr(self, f"{kind}_data")
            if kind in self.reference_errors:
                parts.append(self.reference_errors[kind])
            elif data is not None:
                parts.append(f"{label}: {data.source_name} ({data.count:,} rows, saved)")
            elif getattr(self.validator, f"{kind}_validator") is not None:
                parts.append(f"{label}: active campaign list")
            else:
                parts.append(f"{label}: not loaded")
            enabled = self.settings.require_tal_match if kind == "tal" else self.settings.enable_suppression
            if not enabled:
                parts[-1] += " (matching disabled in Settings)"
        return "  |  ".join(parts)

    def load_reference(self, path: str, kind: str, mapping: dict[str, str] | None = None, *, dataframe=None) -> int:
        data = load_reference_data(path, kind, mapping, dataframe=dataframe)
        # Commit to disk before replacing a working list; failed uploads keep it.
        self.reference_store.save(data)
        setting = "require_tal_match" if kind == "tal" else "enable_suppression"
        if self.active_campaign is None:
            self.settings_service.set(setting, True)
        setattr(self.settings, setting, True)
        self._configure_reference(data)
        self.reference_errors.pop(kind, None)
        self.clear_derived_state()
        self.history.clear()
        self.save_workspace()
        record_activity(kind, f"Loaded {kind} reference list", {"file": data.source_name, "records": data.count})
        return data.count

    def validate(self, *, progress_callback=None, control=None, indices=None) -> dict[str, int]:
        summary = self.validate_scope(indices, progress_callback=progress_callback, control=control)
        record_activity("validation", "Qt validation completed", summary)
        return summary

    def validation_summary(self) -> dict[str, int]:
        summary = {
            "Total Records": len(self.data_manager.records),
            "Valid": 0,
            "Warnings": 0,
            "Invalid": 0,
            "Suppressed": 0,
            "Outside TAL": 0,
            "Duplicates": 0,
            "Missing Email": 0,
            "Emails Found": 0,
            "Manual Review": 0,
            "Needs validation": 0,
        }
        for i, record in enumerate(self.data_manager.records):
            status = self.row_states.get(i, "")
            if status.startswith("Valid"):
                summary["Valid"] += 1
            elif status == "Warning":
                summary["Warnings"] += 1
            elif status == "Invalid":
                summary["Invalid"] += 1
            elif status == "Suppressed":
                summary["Suppressed"] += 1
            elif status == "Outside TAL":
                summary["Outside TAL"] += 1
            elif status == "Duplicate":
                summary["Duplicates"] += 1
            elif status == "Manual Review":
                summary["Manual Review"] += 1
            elif status == "Needs validation" or i in self.dirty_rows or not status:
                summary["Needs validation"] += 1
            if str(record.get("Business Email ID", MISSING_VALUE)).strip() in {"", MISSING_VALUE}:
                summary["Missing Email"] += 1
            else:
                summary["Emails Found"] += 1
        return summary

    def find_emails(self, *, progress_callback=None, row_progress_callback=None, control=None) -> list[EmailFindingResult]:
        records = [dict(r) for r in self.data_manager.records]
        self.email_results = {}
        completed = 0
        last_save = time.monotonic()
        def keep_result(result):
            nonlocal completed, last_save
            self.email_results[result.row_index] = result
            if 0 <= result.row_index < len(self.data_manager.records):
                row = self.data_manager.records[result.row_index]
                if result.applied:
                    previous_keys = self._duplicate_keys(row)
                    self.data_manager.update_cell(result.row_index, "Business Email ID", result.candidate)
                    self.data_manager.update_cell(result.row_index, "Email Status", result.status)
                    self._mark_edit_dependencies({result.row_index}, previous_keys)
                elif str(row.get("Business Email ID", MISSING_VALUE)).strip() in {"", MISSING_VALUE}:
                    if result.discovery_status in {"Timed Out", "Search Error"}:
                        row["Email Status"] = "Unfinished (retry available)"
                    elif result.discovery_status == "Search Disabled":
                        row["Email Status"] = "Search setup needed"
                    elif result.status == "Possible" or (result.candidate != MISSING_VALUE and not result.applied):
                        row["Email Status"] = "Needs review (below confidence threshold)"
                    else:
                        row["Email Status"] = result.status
            completed += 1
            if completed % 10 == 0 or time.monotonic() - last_save >= 2:
                self.save_checkpoint(reason="email-progress")
                last_save = time.monotonic()
        results = self.email_finder.find_missing(
            records,
            run_store=EmailRunStore(), result_callback=keep_result,
            minimum_confidence=int(self.settings.minimum_email_confidence),
            revalidate_existing=bool(self.settings.revalidate_existing_emails),
            blocked_statuses=self.row_states,
            enable_web_search=bool(self.settings.email_search_enabled),
            enable_website_lookup=bool(self.settings.email_website_lookup),
            search_provider_name=self.settings.search_provider_name,
            max_workers=int(self.settings.email_search_max_workers),
            request_timeout_seconds=int(self.settings.email_search_timeout),
            retries=int(self.settings.email_search_retries),
            discovery_cache_days=int(self.settings.email_discovery_cache_days),
            progress_callback=progress_callback,
            row_progress_callback=row_progress_callback,
            control=control,
        )
        self.recalculate_formulas()
        self.save_checkpoint(reason="email-cancelled" if self.email_finder.last_run_cancelled else "email-complete")
        report = self.email_finder.last_metrics
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        target = LOG_DIR / "email_performance.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2), encoding="utf-8")
        temporary.replace(target)
        record_activity("email", f"Email engine saved {len(results):,} row results", report)
        return results

    def export(self, path: str, *, scope=None, row_indices=None) -> Path:
        scope = scope or ("qualified" if self.settings.export_valid_only else "all")
        if scope not in {"all", "qualified", "disqualified", "filtered"}:
            raise ValueError("Unknown export selection")
        indices = list(range(len(self.data_manager.records)))
        if scope == "filtered":
            indices = list(dict.fromkeys(i for i in (row_indices or []) if 0 <= i < len(self.data_manager.records)))
        elif scope == "qualified":
            indices = [i for i in indices if i not in self.dirty_rows and self.row_states.get(i, "").startswith("Valid")]
        elif scope == "disqualified":
            indices = [i for i in indices if i not in self.dirty_rows and self.data_manager.records[i].get("QA Status") == "Disqualified"]
        if not indices:
            raise ValueError("No leads match this export choice. Choose another option or run Validate first.")
        records = [self.data_manager.records[i] for i in indices]
        import pandas as pd
        from app.constants import STANDARD_HEADERS
        df = pd.DataFrame(records, columns=self.data_manager.headers).fillna(MISSING_VALUE)
        details = None
        if self.settings.include_validation_details:
            details = []
            for i in indices:
                record = self.data_manager.records[i]
                details.append({
                    "Row": i + 1,
                    "Final Status": self.row_states.get(i, "Not Validated"),
                    "QA Status": record.get("QA Status", MISSING_VALUE),
                    "Primary Reason": record.get("Primary Reason", MISSING_VALUE),
                    "Validation Reason": "; ".join(self.validation_reasons.get(i, [])) or "-",
                    "Email Status": record.get("Email Status", MISSING_VALUE),
                    "Business Email ID": record.get("Business Email ID", MISSING_VALUE),
                })
        exported_rows = set(indices)
        formulas = [{"Source row": row + 1, "Column": column, "Formula": expression,
                     "Calculated value": self.data_manager.records[row].get(column, MISSING_VALUE)}
                    for (row, column), expression in self.data_manager.formulas.items() if row in exported_rows]
        result = export_records(df, path, validation_details=details, custom_columns=self.data_manager.custom_columns,
                                formula_details=formulas)
        record_activity("export", f"Exported {len(records):,} lead(s)", {"file": str(result)})
        return result

    def import_campaign(self, source: str) -> CampaignProfile:
        profile = self.campaign_importer.import_package(source)
        record_activity("campaign", f"Imported campaign {profile.campaign_id}", {"name": profile.campaign_name})
        return profile

    def activate_campaign(self, profile: CampaignProfile, *, persist: bool = True) -> list[str]:
        warnings = self._open_workspace(profile)
        if persist:
            self.campaign_store.activate(profile.campaign_id)
            profile.active = True
        self.save_workspace()
        record_activity("campaign", f"Activated campaign {profile.campaign_id}", {"warnings": warnings})
        return warnings

    def delete_campaign(self, campaign_id: str) -> bool:
        profile = self.campaign_store.get(campaign_id)
        if not profile:
            return False
        if self.active_campaign and self.active_campaign.campaign_id == campaign_id:
            self._open_workspace(None)
        was_active = self.campaign_store.delete(campaign_id)
        record_activity("campaign", f"Deleted campaign {campaign_id}", {"was_active": was_active})
        return was_active

    def save_checkpoint(self, *, reason: str = "autosave", clean_shutdown: bool = False) -> Path:
        target = self.checkpoints.save(
            records=[dict(r) for r in self.data_manager.records],
            custom_columns=self.data_manager.custom_columns,
            formulas=self.data_manager.formula_payload(),
            row_states=self.row_states,
            validation_reasons=self.validation_reasons,
            references={"workspace_key": self.workspace_key},
            settings={name: getattr(self.settings, name) for name in self.settings.__dataclass_fields__},
            clean_shutdown=clean_shutdown,
            reason=reason,
        )
        self.save_workspace()
        return target

    def recover(self, snapshot: CheckpointSnapshot) -> None:
        payload = snapshot.payload
        key = payload.get("references", {}).get("workspace_key")
        if key and key != self.workspace_key:
            raise ValueError("This recovery file belongs to a different campaign workspace.")
        self.data_manager.custom_columns.clear()
        self.data_manager.add_columns(payload.get("custom_columns") or [])
        self.data_manager.replace_all(payload.get("records") or [], source_name="Recovered Session")
        formula_changes = self.data_manager.restore_formulas(payload.get("formulas"))
        self.row_states = {int(k): str(v) for k, v in (payload.get("row_states") or {}).items()}
        self.validation_reasons = {int(k): list(v) for k, v in (payload.get("validation_reasons") or {}).items()}
        self.validation_results.clear()
        self.email_results.clear()
        self.dirty_rows = {i for i in range(len(self.data_manager.records)) if self.row_states.get(i) == "Needs validation"}
        self.history.clear()
        self._pending_dependency_groups.clear()
        self.mark_rows_dirty(row for row, _ in formula_changes)

    def shutdown(self) -> None:
        try:
            self.save_checkpoint(reason="clean-shutdown", clean_shutdown=True)
        except Exception:
            pass
        if self.settings.qwen_stop_on_exit:
            try:
                self.qwen_runtime.stop(wait_seconds=2.0)
            except Exception:
                pass
