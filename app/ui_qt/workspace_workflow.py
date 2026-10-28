"""Worksheet editing and campaign workspace operations shared by the Qt UI."""
from dataclasses import asdict

from app.constants import MISSING_VALUE
from app.core.batch_control import BatchCancelled
from app.core.campaign_activation import build_campaign_validators
from app.core.reference_list_store import ReferenceListStore
from app.core.validator import ValidationIssue, ValidationResult
from app.core.workspace_store import WorkspaceStore
from app.core.worksheet_history import CellEdit, ColumnEdit, WorksheetHistory
from app.utils.text_utils import clean_missing


WORKSPACE_SETTINGS = (
    "require_tal_match", "enable_suppression", "enable_tal_fuzzy_match", "enable_suppression_fuzzy_match",
    "minimum_email_confidence", "revalidate_existing_emails", "email_search_enabled", "email_website_lookup",
    "search_provider_name", "email_search_max_workers", "email_search_timeout", "email_search_retries",
    "email_discovery_cache_days", "export_valid_only", "include_validation_details",
)


class WorkspaceWorkflow:
    def _init_workspaces(self, active):
        self.history = WorksheetHistory()
        self.dirty_rows = set()
        self._pending_dependency_groups = []
        self.workspace_store = WorkspaceStore(self.reference_store.folder.parent / "workspaces")
        self.general_reference_folder = self.reference_store.folder
        self.workspace_key = None
        self.workspace_restored = False
        self.last_validation_count = 0
        self._open_workspace(active, initial=True)

    def _workspace_payload(self):
        return {
            "campaign_id": self.active_campaign.campaign_id if self.active_campaign else None,
            "records": self.data_manager.records, "custom_columns": self.data_manager.custom_columns,
            "formulas": self.data_manager.formula_payload(),
            "row_states": self.row_states, "validation_reasons": self.validation_reasons,
            "validation_results": {str(i): asdict(result) for i, result in self.validation_results.items()},
            "dirty_rows": sorted(self.dirty_rows),
            "dependency_groups": [sorted(group) for group in self._pending_dependency_groups],
            "settings": {key: getattr(self.settings, key) for key in WORKSPACE_SETTINGS},
        }

    def save_workspace(self):
        if self.workspace_key is not None:
            self.workspace_store.save(self.workspace_key, self._workspace_payload())

    def _open_workspace(self, profile, *, initial=False):
        key = self.workspace_store.key(profile.campaign_id if profile else None)
        payload = self.workspace_store.load(key)  # Read before changing the open worksheet.
        if not initial and key == self.workspace_key:
            warnings = self._configure_campaign_references(profile)
            self.mark_rows_dirty(range(len(self.data_manager.records)))
            return warnings
        if not initial:
            self.save_workspace()
        legacy_references = []
        if initial and profile and not self.workspace_store.folder.exists():
            # First upgrade: retain the lists belonging to the previously active campaign.
            for kind in ("tal", "suppression"):
                data = self.reference_store.load(kind)
                if data is not None:
                    legacy_references.append(data)
        self.workspace_key = key
        self.active_campaign = profile
        self.workspace_restored = payload is not None
        self.reference_store = ReferenceListStore(self.general_reference_folder if not profile else
                                                  self.workspace_store.directory(key) / "reference_lists")
        for data in legacy_references:
            self.reference_store.save(data)
        self.tal_data = self.suppression_data = None
        self.reference_errors.clear()
        defaults = type(self.settings)()
        for name in WORKSPACE_SETTINGS:
            default = self.settings_service.get(name, getattr(defaults, name))
            setattr(self.settings, name, (payload or {}).get("settings", {}).get(name, default))
        self.data_manager.custom_columns.clear()
        self.data_manager.add_columns((payload or {}).get("custom_columns") or [])
        self.data_manager.replace_all((payload or {}).get("records") or [], source_name="Saved workspace")
        formula_changes = self.data_manager.restore_formulas((payload or {}).get("formulas"))
        self.row_states = {int(i): value for i, value in (payload or {}).get("row_states", {}).items()}
        self.validation_reasons = {int(i): value for i, value in (payload or {}).get("validation_reasons", {}).items()}
        self.validation_results.clear()
        for i, result in (payload or {}).get("validation_results", {}).items():
            try:
                result = dict(result)
                result["issues"] = [ValidationIssue(**issue) for issue in result.get("issues", [])]
                self.validation_results[int(i)] = ValidationResult(**result)
            except (TypeError, ValueError):
                self.row_states[int(i)] = "Needs validation"
        self.dirty_rows = set((payload or {}).get("dirty_rows", []))
        self._pending_dependency_groups = [set(group) for group in (payload or {}).get("dependency_groups", [])]
        self.dirty_rows.update(i for i in range(len(self.data_manager.records)) if i not in self.validation_results)
        self.email_results.clear()
        self.history.clear()
        warnings = self._configure_campaign_references(profile)
        self._restore_references()
        self._validation_settings = tuple(getattr(self.settings, key) for key in WORKSPACE_SETTINGS[:4])
        self.mark_rows_dirty(row for row, _ in formula_changes)
        return warnings

    def _configure_campaign_references(self, profile):
        tal = suppression = None
        warnings = []
        if profile:
            tal, suppression, warnings = build_campaign_validators(profile,
                tal_fuzzy_enabled=self.settings.enable_tal_fuzzy_match,
                suppression_fuzzy_enabled=self.settings.enable_suppression_fuzzy_match)
        self.active_campaign = profile
        self.validator.configure_campaign(profile)
        self.validator.configure_tal(tal, require_match=self.settings.require_tal_match)
        self.validator.configure_suppression(suppression, enabled=self.settings.enable_suppression)
        for data in (self.tal_data, self.suppression_data):
            if data is not None:
                self._configure_reference(data)
        return warnings

    def switch_to_general(self):
        warnings = self._open_workspace(None)
        self.campaign_store.deactivate()
        self.save_workspace()
        return warnings

    def mark_rows_dirty(self, rows):
        for row in set(rows):
            if 0 <= row < len(self.data_manager.records):
                self.dirty_rows.add(row)
                self.row_states[row] = "Needs validation"
                self.validation_results.pop(row, None)
                self.validation_reasons.pop(row, None)
                self.data_manager.records[row]["QA Status"] = "Needs validation"
                self.data_manager.records[row]["Primary Reason"] = MISSING_VALUE

    def _duplicate_keys(self, record):
        checker = self.validator.duplicate_checker
        return {(name, value) for name in ("_email_key", "_linkedin_key", "_person_domain_key", "_person_company_key")
                if (value := getattr(checker, name)(record)) is not None}

    def _mark_edit_dependencies(self, rows, old_keys):
        keys = set(old_keys)
        for i in rows:
            if i < len(self.data_manager.records):
                keys.update(self._duplicate_keys(self.data_manager.records[i]))
        affected = set(rows)
        for i, record in enumerate(self.data_manager.records):
            if keys.intersection(self._duplicate_keys(record)):
                affected.add(i)
        # Domain caps can change the eligibility of other people in the account.
        profile = self.validator.campaign_rule_validator.profile
        if profile and any(rule.field in {"domain_limits", "domain_caps", "domain_cap_default", "account_cap_default"}
                           and rule.status in {"Confirmed", "Extracted"} for rule in profile.rules):
            affected.update(range(len(self.data_manager.records)))
        self.mark_rows_dirty(affected)
        remaining = []
        for group in self._pending_dependency_groups:
            if affected.intersection(group):
                affected.update(group)
            else:
                remaining.append(group)
        if len(affected) > 1:
            remaining.append(affected)
        self._pending_dependency_groups = remaining

    def edit_cells(self, edits, label="Edit cells", *, remember=True, allow_formulas=True):
        edits = {(row, column): clean_missing(value) for (row, column), value in edits.items()
                 if row >= 0 and column in self.data_manager.headers and column not in {"QA Status", "Primary Reason"}}
        if not allow_formulas:
            edits = {cell: "'" + value if value.startswith(("=", "'")) else value for cell, value in edits.items()}
        before = {cell: self.data_manager.raw_value(*cell) for cell in edits}
        edits = {cell: value for cell, value in edits.items() if value != before[cell]}
        before = {cell: before[cell] for cell in edits}
        if not edits:
            return False
        rows = {row for row, _ in edits}
        # Calculated identifiers can affect duplicate validation on other rows.
        dependency_rows = rows | {row for row, _ in self.data_manager.formulas}
        old_keys = set().union(*(self._duplicate_keys(self.data_manager.records[row])
                                for row in dependency_rows if row < len(self.data_manager.records)))
        previous_count = len(self.data_manager.records)
        while len(self.data_manager.records) <= max(rows):
            self.data_manager.append_record({}, source_name="Manual Entry")
        for (row, column), value in edits.items():
            self.data_manager.update_cell(row, column, value, allow_formulas=True)
        rows.update(row for row, _ in self.data_manager.recalculate())
        self._mark_edit_dependencies(rows, old_keys)
        if remember:
            self.history.push(CellEdit(label, before, edits, previous_count))
        return True

    def undo_edit(self):
        if not self.history.undo_stack:
            return False
        command = self.history.undo_stack.pop()
        if isinstance(command, ColumnEdit):
            self._restore_column_state(command.before)
            self.history.redo_stack.append(command)
            return True
        self.edit_cells(command.before, remember=False)
        if len(self.data_manager.records) > command.previous_count:
            del self.data_manager.records[command.previous_count:]
            for state in (self.row_states, self.validation_results, self.validation_reasons, self.email_results):
                for row in list(state):
                    if row >= command.previous_count:
                        state.pop(row)
            self.dirty_rows.intersection_update(range(command.previous_count))
            self._pending_dependency_groups = [group.intersection(range(command.previous_count)) for group in self._pending_dependency_groups]
            self.data_manager.formulas = {cell: expression for cell, expression in self.data_manager.formulas.items()
                                          if cell[0] < command.previous_count}
            self.recalculate_formulas()
        self.history.redo_stack.append(command)
        return True

    def redo_edit(self):
        if not self.history.redo_stack:
            return False
        command = self.history.redo_stack.pop()
        if isinstance(command, ColumnEdit):
            self._restore_column_state(command.after)
            self.history.undo_stack.append(command)
            return True
        self.edit_cells(command.after, remember=False)
        self.history.undo_stack.append(command)
        return True

    def recalculate_formulas(self):
        rows = {row for row, _ in self.data_manager.formulas}
        old_keys = set().union(*(self._duplicate_keys(self.data_manager.records[row]) for row in rows))
        changed = self.data_manager.recalculate()
        if changed:
            self._mark_edit_dependencies({row for row, _ in changed}, old_keys)
        return changed

    def _column_state(self):
        return {"columns": list(self.data_manager.custom_columns),
                "records": [dict(row) for row in self.data_manager.records],
                "formulas": self.data_manager.formula_payload()}

    def _restore_column_state(self, state):
        self.data_manager.custom_columns[:] = state["columns"]
        self.data_manager.replace_all(state["records"])
        self.data_manager.restore_formulas(state["formulas"])
        self.mark_rows_dirty(range(len(self.data_manager.records)))

    def change_columns(self, names, *, delete=False):
        before = self._column_state()
        if delete:
            self.data_manager.delete_columns(names)
        else:
            self.data_manager.add_columns(names)
            self.data_manager.recalculate()
        self.history.push(ColumnEdit("Delete columns" if delete else "Add columns", before, self._column_state()))
        self.mark_rows_dirty(range(len(self.data_manager.records)))

    def validate_scope(self, indices=None, *, progress_callback=None, control=None):
        if self.reference_errors:
            raise ValueError("\n".join(self.reference_errors.values()))
        records = [dict(row) for row in self.data_manager.records]
        selected = set(range(len(records))) if indices is None else {i for i in indices if 0 <= i < len(records)}
        if not selected:
            self.last_validation_count = 0
            return self.validation_summary()
        for group in self._pending_dependency_groups:
            if selected.intersection(group):
                selected.update(group)
        selected.intersection_update(range(len(records)))
        duplicates = self.validator.duplicate_checker.check(records)
        # Include connected duplicate rows, including previously matched records.
        queue = list(selected)
        while queue:
            i = queue.pop()
            peers = set(duplicates[i].duplicate_rows)
            previous = self.validation_results.get(i)
            if previous:
                peers.update(previous.duplicate_rows)
            for peer in peers - selected:
                selected.add(peer)
                queue.append(peer)
        profile = self.validator.campaign_rule_validator.profile
        if profile and any(rule.field in {"domain_limits", "domain_caps", "domain_cap_default", "account_cap_default"}
                           and rule.status in {"Confirmed", "Extracted"} for rule in profile.rules):
            selected = set(range(len(records)))
        processed = {}
        self.validator.last_run_cancelled = False
        for i in sorted(selected):
            try:
                if control:
                    control.checkpoint()
            except BatchCancelled:
                self.validator.last_run_cancelled = True
                break
            processed[i] = self.validator.validate(records[i], duplicate_result=duplicates[i])
            if progress_callback and (len(processed) % 25 == 0 or len(processed) == len(selected)):
                progress_callback(len(processed), len(selected))
        if processed:
            self.validator._apply_campaign_caps([records[i] for i in processed], list(processed.values()))
        for i, result in processed.items():
            self.validation_results[i] = result
            self.row_states[i] = result.status
            self.validation_reasons[i] = list(result.reasons)
            self.data_manager.records[i]["QA Status"] = result.qa_status
            self.data_manager.records[i]["Primary Reason"] = result.primary_reason
            self.dirty_rows.discard(i)
        self.last_validation_count = len(processed)
        self._pending_dependency_groups = [group.difference(processed) for group in self._pending_dependency_groups
                                           if len(group.difference(processed)) > 1]
        self.save_checkpoint(reason="validation-cancelled" if self.validator.last_run_cancelled else "validation-complete")
        return self.validation_summary()

    def remove_reference(self, kind):
        self.reference_store.remove(kind)
        setattr(self, f"{kind}_data", None)
        self.reference_errors.pop(kind, None)
        self._configure_campaign_references(self.active_campaign)
        self.history.clear()
        self.mark_rows_dirty(range(len(self.data_manager.records)))
        self.save_workspace()
