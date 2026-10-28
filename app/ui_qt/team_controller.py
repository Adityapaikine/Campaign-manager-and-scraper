"""Reuse the worksheet engine without opening any legacy/shared database files."""
import json
from types import SimpleNamespace
from app.constants import STANDARD_HEADERS
from app.core.data_manager import DataManager
from app.core.validator import ValidationEngine
from app.core.worksheet_history import WorksheetHistory
from app.ui_qt.workspace_workflow import WorkspaceWorkflow
from app.ui_qt.controller import AppSettings

META=('Lead ID','CID','Team Lead','Workflow Status','Current Department','Assigned User','Original Owner','Transfer Status')

class Preferences:
    def __init__(self,values=None): self.values=values or {}; self.dirty={}
    def get(self,key,default=None): return self.values.get(key,default)
    def set(self,key,value): self.values[key]=value; self.dirty[key]=value
    def update_many(self,values):
        for key,value in values.items(): self.set(key,value)

class TeamController(WorkspaceWorkflow):
    def __init__(self,client,preferences=None):
        self.client=client; self.settings_service=Preferences(preferences); self.settings=AppSettings(appearance_mode='Light')
        self.data_manager=DataManager(); self.validator=ValidationEngine()
        self.history=WorksheetHistory(); self.row_states={}; self.validation_results={}; self.validation_reasons={}; self.email_results={}
        self.dirty_rows=set(); self._pending_dependency_groups=[]; self.active_campaign=None; self.workspace_key='team'
        self.campaigns=[]; self.campaign_store=SimpleNamespace(list=lambda:[SimpleNamespace(**c) for c in self.campaigns])
        self.mode='draft'; self.sheet=None; self.original=[]; self.lead_rows=[]; self.dirty=False; self.field_permissions={}; self.error_callback=lambda message:None
        from app.core.database_connections import DatabaseProfiles
        self.database_profiles=DatabaseProfiles(self.settings_service)
        self.module_access=None; self._ai_service=None; self._qwen_runtime=None

    def load_settings(self):
        values=self.settings_service.get('app_settings',{})
        defaults=AppSettings(appearance_mode='Light')
        for name in defaults.__dataclass_fields__:
            value=values.get(name,getattr(defaults,name)) if isinstance(values,dict) else getattr(defaults,name)
            if type(value) is type(getattr(defaults,name)):setattr(defaults,name,value)
        self.settings=defaults

    def save_settings(self):
        from dataclasses import asdict
        self.settings_service.set('app_settings',asdict(self.settings))

    @property
    def client_data_dir(self):
        import os,hashlib
        from pathlib import Path
        identity=str(getattr(self.client,'url',getattr(self.client,'base_url','local')))+'|'+self.client.user['id']
        key=hashlib.sha256(identity.encode()).hexdigest()[:24]
        root=Path(os.getenv('LEAD_CLIENT_DATA_DIR',str(Path(os.getenv('LOCALAPPDATA',Path.home()))/'LeadWorkspace'/'Clients')))
        return root/key

    @property
    def qwen_runtime(self):
        from app.ai.qwen_runtime import QwenRuntimeManager
        s=self.settings
        if self._qwen_runtime is None:
            self._qwen_runtime=QwenRuntimeManager(folder=s.qwen_folder,executable=s.qwen_executable,model=s.qwen_model,host=s.qwen_host,port=s.qwen_port,extra_args=s.qwen_extra_args)
        else:
            self._qwen_runtime.configure(folder=s.qwen_folder,executable=s.qwen_executable,model=s.qwen_model,host=s.qwen_host,port=s.qwen_port,extra_args=s.qwen_extra_args)
        return self._qwen_runtime

    @property
    def ai_service(self):
        from app.ai.ai_service import LocalAIService,AIServiceConfig
        s=self.settings
        config=AIServiceConfig(enabled=s.qwen_enabled and s.ai_features_enabled,start_on_demand=s.ai_start_on_demand,
            cache_enabled=s.ai_cache_enabled,cache_days=s.ai_cache_days,minimum_confidence=s.ai_min_confidence,
            max_prompt_chars=s.ai_max_prompt_chars,max_parallel_calls=s.ai_max_parallel_calls,request_timeout=s.ai_request_timeout)
        if self._ai_service is None:
            self._ai_service=LocalAIService(self.qwen_runtime,config,database=self.client_data_dir/'ai-cache.sqlite3')
        else:self._ai_service.runtime=self.qwen_runtime; self._ai_service.reconfigure(config)
        return self._ai_service

    def shutdown_local_tools(self):
        if self._qwen_runtime and self.settings.qwen_stop_on_exit:self._qwen_runtime.shutdown_quick()

    def reference_summary(self):
        if self.read_only_sheet:
            sheet=self.sheet
            return f"Read-only · {sheet.get('owner_name','Unknown owner')}"+(' · Archived' if sheet.get('archived') else '')
        return ('Personal draft · not committed to the campaign' if self.mode=='draft' else 'Shared campaign records · changes require Save')+(' · Unsaved changes' if self.dirty else ' · Saved')

    @property
    def read_only_sheet(self):
        return self.mode=='draft' and bool((self.sheet or {}).get('read_only'))

    def can_edit_cell(self,row,field):
        if self.read_only_sheet:return False
        if self.module_access is not None and not self.module_access.get('leads',{}).get('allowed'):return False
        if field in META or field in ('QA Status','Primary Reason'): return False
        if self.mode=='draft': return self.sheet is not None and self.field_permissions.get(field,'Edit')=='Edit'
        if row>=len(self.lead_rows): return False
        lead=self.lead_rows[row]; user=self.client.user or {}
        permitted=(user.get('role')=='Super User' or (lead['department_id']==user.get('department_id') and
                   (user.get('role') in ('Department Manager','Team Lead') or lead['assigned_id']==user.get('id'))))
        return permitted and not lead['archived'] and (user.get('role')=='Super User' or lead['state'] not in ('Approved','Quality Qualified','Delivery Approved','Delivered')) and lead['field_access'].get(field,'Read Only')=='Edit'

    def edit_cells(self,edits,label='Edit cells',**kwargs):
        actual={cell:value for cell,value in edits.items() if str(value)!=self.data_manager.raw_value(*cell)}
        if any(not self.can_edit_cell(*cell) for cell in actual):
            self.error_callback('The selection includes fields or leads you cannot edit. No cells were changed.'); return False
        changed=super().edit_cells(actual,label,**kwargs)
        self.dirty=self.dirty or changed; return changed

    def change_columns(self,names,*,delete=False):
        if self.read_only_sheet:raise ValueError('This worksheet is read-only. Duplicate it into your working drafts to change columns.')
        if self.mode!='draft': raise ValueError('Add or remove columns in a personal draft sheet.')
        if any(n in META for n in names): raise ValueError('Ownership and campaign columns are managed by the service.')
        super().change_columns(names,delete=delete); self.dirty=True

    def _history_edit(self,redo=False):
        if self.read_only_sheet:return False
        from app.core.worksheet_history import ColumnEdit
        stack=self.history.redo_stack if redo else self.history.undo_stack
        if not stack:return False
        command=stack[-1]
        allowed=self.mode=='draft' if isinstance(command,ColumnEdit) else all(self.can_edit_cell(*cell) for cell in (command.after if redo else command.before))
        if not allowed:
            self.error_callback('This change includes fields you can no longer edit.'); return False
        changed=super().redo_edit() if redo else super().undo_edit()
        self.dirty=self.dirty or changed; return changed

    def undo_edit(self):return self._history_edit()

    def redo_edit(self):return self._history_edit(redo=True)

    def recalculate_formulas(self):
        if self.read_only_sheet:return False
        changed=super().recalculate_formulas()
        self.dirty=self.dirty or bool(changed); return changed

    def load_sheet(self,result):
        payload=result['payload']; self.mode='draft'; self.sheet=result; self.workspace_key=result['id']
        self._load(payload.get('records',[]),payload.get('custom_columns',[]),payload.get('formulas',[]))

    def load_leads(self,result):
        self.mode='records'; self.sheet=None; self.workspace_key='records'; self.lead_rows=result['rows']
        records=[]; columns=[]
        for lead in self.lead_rows:
            row={**lead['record'],'CID':lead['campaign_id'],'Team Lead':lead['team_lead'],'Lead ID':lead['id'],
                 'Workflow Status':lead['state'],'Current Department':lead.get('department_name') or 'Unassigned','Assigned User':lead.get('assigned_name') or 'Unassigned',
                 'Original Owner':lead.get('owner_name') or 'Unassigned','Transfer Status':lead.get('transfer_status') or 'Not transferred'}
            records.append(row)
            for field in row:
                if field not in STANDARD_HEADERS and field not in columns: columns.append(field)
        columns=[c for c in columns if c not in ('CID','Team Lead')]+['CID','Team Lead']
        self._load(records,columns,[])
        self.row_states={i:r['validation_result'].get('status','Needs validation') for i,r in enumerate(self.lead_rows)}
        self.validation_reasons={i:r['validation_result'].get('messages',[]) for i,r in enumerate(self.lead_rows)}

    def _load(self,records,columns,formulas):
        self.data_manager=DataManager(); self.data_manager.add_columns(columns); self.data_manager.replace_all(records)
        self.data_manager.restore_formulas(formulas); self.history.clear(); self.dirty_rows.clear()
        self.row_states.clear(); self.validation_reasons.clear(); self.validation_results.clear(); self._pending_dependency_groups=[]
        self.original=[dict(r) for r in self.data_manager.records]; self.dirty=False

    def draft_payload(self):
        # QA conclusions are recomputed by the service, never trusted from a client.
        rows=[{k:v for k,v in row.items() if k not in META and k not in ('QA Status','Primary Reason') and self.field_permissions.get(k,'Edit')=='Edit'} for row in self.data_manager.records]
        ids=(self.sheet or {}).get('payload',{}).get('row_ids',[])
        import uuid
        ids=(ids+[str(uuid.uuid4()) for _ in range(max(0,len(rows)-len(ids)))])[:len(rows)]
        return {'records':rows,'row_ids':ids,'custom_columns':self.data_manager.custom_columns,'formulas':self.data_manager.formula_payload(),'headers':self.data_manager.headers}

    def pending_edits(self):
        result=[]
        for i,row in enumerate(self.data_manager.records):
            if i>=len(self.lead_rows): continue
            changes={field:value for field,value in row.items() if self.can_edit_cell(i,field) and value!=self.original[i].get(field)}
            if changes: result.append({'lead_id':self.lead_rows[i]['id'],'version':self.lead_rows[i]['version'],'changes':changes})
        return result
