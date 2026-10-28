"""Shared-account adapters for the established research pages."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QTableWidget,
    QPlainTextEdit,QMessageBox)
from app.ui_qt.qt_theme import build_stylesheet


class UnifiedModules:
    def apply_theme(self):
        s=self.controller.settings
        self.setStyleSheet(build_stylesheet(s.color_scheme,s.appearance_mode=='Dark')+'''
            QListWidget#moduleNavigation { background: transparent; border: none; outline: none; }
            QListWidget#moduleNavigation::item { border-radius: 6px; padding: 5px 6px; }
            QListWidget#moduleNavigation::item:selected { background: #DEECFF; color: #0868F9; }
            QListWidget#moduleNavigation::item:hover { background: #E8F1FF; }
        ''')
        if hasattr(self,'excel_workspace'):self.excel_workspace.apply_theme(s.appearance_mode=='Dark')

    def create_module_page(self,module):
        if module=='scraper':
            import os
            os.environ['LEAD_USER_SCRAPER_DIR']=str(self.controller.client_data_dir/'Scraper')
            from app.ui_qt.pages.scraper_page import ScraperPage,engine
            # A process has one signed-in account. Never reuse the old global
            # browser session for another account on this PC.
            engine.CHROME_PROFILE_DIR=self.controller.client_data_dir/'Scraper'/'chrome_profile'
            self.scraper_page=ScraperPage(self.controller)
            self.scraper_page.transfer_requested.connect(self.import_scraper_results)
            self.scraper_page.transfer_button.setText('Send to Lead Workspace')
            return self.scraper_page
        if module=='ai':
            from app.ui_qt.pages.ai_page import AIPage
            self.ai_page=AIPage(self.controller)
            self.ai_page.rule_builder_requested.connect(self.ai_build_rules)
            self.ai_page.normalize_requested.connect(self.ai_normalize)
            self.ai_page.qa_requested.connect(self.ai_qa)
            self.ai_page.explain_requested.connect(lambda row:self.ai_qa(row,explain=True))
            self.ai_page.intelligence_requested.connect(self.ai_intelligence)
            return self.ai_page
        if module=='settings':
            from app.ui_qt.pages.settings_page import SettingsPage
            self.settings_page=SettingsPage(self.controller)
            self.settings_page.settings_applied.connect(self.persist_app_settings)
            self.settings_page.database_connection_requested.connect(lambda:self.request_module_action('leads',self.configure_reference_database))
            for signal,action in [(self.settings_page.qwen_start_requested,'start'),(self.settings_page.qwen_stop_requested,'stop'),
                                  (self.settings_page.qwen_restart_requested,'restart'),(self.settings_page.qwen_refresh_requested,'discover')]:
                signal.connect(lambda a=action:self.qwen_action(a))
            # Campaign validation is authoritative on the server; personal
            # appearance settings must not silently change campaign rules.
            for control in (self.settings_page.require_tal,self.settings_page.enable_suppression,self.settings_page.tal_fuzzy,self.settings_page.supp_fuzzy):
                control.setEnabled(False); control.setToolTip('Managed centrally in Campaign Manager for the selected campaign.')
            note=QLabel('Campaign rules are managed in Campaign Manager. Row colours below are personal preferences.'); note.setWordWrap(True)
            self.settings_page.validation.layout().insertWidget(0,note)
            for control in (self.settings_page.checkpoint_records,self.settings_page.keep_checkpoints):
                control.setEnabled(False); control.setToolTip('Shared drafts use service autosave and Save recovery draft in the workspace More menu.')
            self.settings_page.qwen_autostart.setEnabled(False); self.settings_page.qwen_autostart.setToolTip('Start the local runtime from these controls or on demand after an access check.')
            self.settings_page.ai_campaign_read.setEnabled(False); self.settings_page.ai_campaign_read.setToolTip('Review campaign rules in Campaign Manager; AI suggestions remain in AI Center until reviewed.')
            return self.settings_page
        page=QWidget(); layout=QVBoxLayout(page)
        title=QLabel({'tools':'Activity & Diagnostics','validation':'Validation Summary','info':'Help & Support'}[module]); title.setObjectName('pageTitle'); layout.addWidget(title)
        if module=='tools':
            note=QLabel('Super Users see the service audit trail. Other permitted users see their own activity.'); note.setWordWrap(True); layout.addWidget(note)
            self.audit_offset=0
            bar=QHBoxLayout(); refresh=QPushButton('Refresh activity'); refresh.clicked.connect(lambda:self.refresh_tools(reset=True)); bar.addWidget(refresh)
            bar.addStretch(1); self.audit_previous=QPushButton('Newer'); self.audit_previous.clicked.connect(lambda:self.page_activity(-200)); bar.addWidget(self.audit_previous)
            self.audit_page_label=QLabel(); bar.addWidget(self.audit_page_label)
            self.audit_next=QPushButton('Older'); self.audit_next.clicked.connect(lambda:self.page_activity(200)); bar.addWidget(self.audit_next); layout.addLayout(bar)
            self.audit_table=QTableWidget(); self.audit_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); layout.addWidget(self.audit_table,1)
            self.diagnostics=QLabel(); self.diagnostics.setWordWrap(True); layout.addWidget(self.diagnostics)
        elif module=='validation':
            self.validation_note=QLabel(); self.validation_note.setWordWrap(True); layout.addWidget(self.validation_note)
            bar=QHBoxLayout(); refresh=QPushButton('Refresh summary'); refresh.clicked.connect(self.refresh_validation_page); bar.addWidget(refresh)
            validate=QPushButton('Validate current workspace'); validate.clicked.connect(self.validate); bar.addWidget(validate); bar.addStretch(1); layout.addLayout(bar)
            self.validation_table=QTableWidget(); self.validation_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); layout.addWidget(self.validation_table,1)
        else:
            help=QPlainTextEdit(); help.setReadOnly(True); help.setPlainText(
                'ONE LEAD WORKSPACE\n\n'
                'Use Campaign in the top bar to choose a campaign. In Lead Workspace, Records switches between working drafts and authorized campaign records; Column view selects visible fields. '
                'Incoming transfers, records awaiting assignment and archived leads are filters in the same table.\n\n'
                'Import, paste, use formulas or send Scraper results to a working draft. Validate, review and commit valid rows to publish them. '
                'Open the Review ribbon, or Home > Review and send, for stages, assignment and Push to Quality / Delivery. The preview explains readiness for every selected row. Review > Incoming leads opens the receiving queue in this same table. Role, record and field rules still apply.\n\n'
                'SCRAPER\nOpen Scraper in this window, choose input and output, then start extraction. Send to Lead Workspace stages results in a private draft in the selected campaign.\n\n'
                'MODULE ACCESS\nSuper Users: Administration > Module Access. Select a department or an individual user and choose Inherit, Allow or Deny for each module. '
                'An individual override takes priority over the department. Administration remains Super User only. Account > Refresh my access checks changes immediately.\n\n'
                'FORMULAS & SHORTCUTS\nType = in a draft cell, choose references with arrow keys, and press Enter. F2 edits a cell. '
                'Use the Formulas ribbon to browse supported functions. Ctrl+F1 collapses the ribbon while keeping Column view available. Ctrl+Z undoes an edit. Ctrl+1 opens Scraper, Ctrl+2 Lead Workspace, Ctrl+3 Campaign Manager, Ctrl+, Settings, F1 Help.\n\n'
                'LOOKUP & EXPORT\nPopulate always asks which columns to fill. SQL Server and PostgreSQL connections offer header mapping. '
                'Export and clipboard copy include only permitted fields. Drafts, formulas, settings and saved views follow your account.\n\n'
                'SETUP\nStart Team Server.ps1 runs the shared service on this PC. Start Lead Workspace.vbs opens this application. '
                'Older Team and Local Research shortcuts now open this same interface. Existing local research files remain on disk and can be imported. '
                'Remote users connect to the service URL; they do not open the server database file.')
            layout.addWidget(help,1)
        return page

    def persist_app_settings(self):
        values=self.controller.settings_service.values['app_settings']
        def done(_):
            self.controller.settings_service.dirty.pop('app_settings',None); self.apply_theme(); self.leads.refresh()
            self.autosave.setInterval(max(15,self.controller.settings.autosave_interval_seconds)*1000)
            self.status.setText('Personal settings saved for your account.')
        self.run(lambda:self.client.call('preferences',key='app_settings',value=values,save=True),done,'Saving settings…')

    def qwen_action(self,action):
        def work():
            self.client.call('module_check',module='settings'); self.client.call('module_check',module='ai')
            return getattr(self.controller.qwen_runtime,action)()
        self.run(work,self.settings_page.update_qwen_status,'Checking local Qwen…')

    def import_scraper_results(self,path):
        if self.busy:
            self.status.setText('Finish the current operation, then use Send to Lead Workspace again.');return
        if not self.campaign:self.select_campaign();return
        cid=self.campaign['campaign_id']; campaign_name=self.campaign['campaign_name']
        def transfer():
            from app.core.scraper_bridge import read_scraper_records,identity
            self.client.call('module_check',module='scraper'); self.client.call('module_check',module='leads')
            if Path(path).stat().st_size>50_000_000:raise ValueError('Split Scraper results into files smaller than 50 MB.')
            rows=read_scraper_records(path); seen=set(); pending=[]
            for row in rows:
                key=identity(row)
                if key in seen:continue
                seen.add(key); row['Campaign Name']=campaign_name; pending.append(row)
            if len(pending)>5000:raise ValueError('A working draft supports 5,000 rows. Split this result file into smaller batches.')
            if not pending:raise ValueError('The workbook has no lead records to transfer.')
            fields=self.client.call('field_access',campaign_id=cid)
            payload={'records':[{k:v for k,v in r.items() if fields.get(k,'Edit')=='Edit' and k not in ('QA Status','Primary Reason')} for r in pending], 'custom_columns':[], 'formulas':[]}
            result=self.client.call('sheet_recovery',campaign_id=cid,payload=payload,name=('Scraper · '+Path(path).stem)[:100])
            return result,len(pending),len(rows)-len(pending)
        def done(result):
            sheet,added,skipped=result
            self.current_module='leads'; self.page_title.setText('Lead Workspace'); self.stack.setCurrentWidget(self.workspace)
            self.nav.blockSignals(True); self.nav.setCurrentRow(self.items.index('Lead Workspace')); self.nav.blockSignals(False)
            self.set_workspace_mode('draft',load=False); self.reload_sheets(sheet['id'])
            self.status.setText(f'{added:,} Scraper leads staged in a working draft · {skipped:,} repeated rows skipped. Validate and commit when ready.')
        self.with_saved(lambda:self.run(transfer,done,'Sending Scraper results to your workspace…'))

    def page_activity(self,delta):
        if self.busy:return
        self.audit_offset=max(0,self.audit_offset+delta); self.refresh_tools()

    def refresh_tools(self,*,reset=False):
        if self.busy:return
        if reset:self.audit_offset=0
        def done(rows):
            self.fill_table(self.audit_table,rows)
            self.audit_previous.setEnabled(self.audit_offset>0); self.audit_next.setEnabled(len(rows)==200)
            self.audit_page_label.setText(f'{self.audit_offset+1}–{self.audit_offset+len(rows)}' if rows else 'No activity on this page')
            self.diagnostics.setText('Connected to the authenticated service. Local tools run on this PC; browser and Qwen readiness are checked when started.')
        self.run(lambda:self.client.call('audit',offset=self.audit_offset),done,'Loading authorized activity…')

    def refresh_validation_page(self):
        def done(_):
            rows=[{'Row':i+1,'Status':self.controller.row_states.get(i,'Needs validation'),'Explanation':' · '.join(self.controller.validation_reasons.get(i,[]))} for i in range(len(self.controller.data_manager.records))]
            self.fill_table(self.validation_table,rows)
            self.validation_note.setText(f'{len(rows):,} rows in the current Lead Workspace view. Open a draft or record filter there to change the scope.')
        self.run(lambda:(self.client.call('module_check',module='validation'),self.client.call('module_check',module='leads')),done)

    def update_ai_selection(self):
        index=self.leads.table.currentIndex(); row=self.leads.proxy.mapToSource(index).row() if index.isValid() else -1
        self.ai_page.set_selected_row(row if row<len(self.controller.data_manager.records) else -1)

    def authorized_ai_records(self):
        # Fresh service reads enforce current field and record visibility before
        # data leaves the grid for a local model. Never read the legacy database.
        self.client.call('module_check',module='ai')
        if self.controller.mode=='draft' and self.controller.sheet:
            return self.client.call('sheet_load',sheet_id=self.controller.sheet['id'])['payload'].get('records',[])
        return [self.client.call('lead',lead_id=r['id'])['record'] for r in self.controller.lead_rows]

    def ai_build_rules(self,text):
        if not text:return
        def work():
            from app.ai.rule_builder import AIRuleBuilder
            self.client.call('module_check',module='ai'); return AIRuleBuilder(self.controller.ai_service).build(text)
        self.run(work,self.ai_page.show_rules,'Building suggested rules…')

    def ai_normalize(self,field):
        def work():
            from app.ai.normalization_agent import AINormalizationAgent
            rows=self.authorized_ai_records(); return AINormalizationAgent(self.controller.ai_service).normalize_unique(field,[r.get(field,'') for r in rows])
        self.with_saved(lambda:self.run(work,self.ai_page.show_normalization,'Preparing normalization suggestions…'))

    def ai_qa(self,row,explain=False):
        if row<0:return
        def work():
            from app.ai.qa_assistant import AIQAAssistant
            records=self.authorized_ai_records()
            if row>=len(records):raise ValueError('Select an available lead in Lead Workspace first.')
            assistant=AIQAAssistant(self.controller.ai_service)
            method=assistant.explain_validation if explain else assistant.review
            return method(records[row],status=self.controller.row_states.get(row),reasons=self.controller.validation_reasons.get(row,[]))
        self.with_saved(lambda:self.run(work,lambda r:self.ai_page.show_json('qa',r),'Preparing AI review…'))

    def ai_intelligence(self):
        def work():
            from app.ai.campaign_intelligence import AICampaignIntelligence
            self.client.call('module_check',module='ai')
            metrics=self.client.call('report',campaign_id=self.campaign['campaign_id'] if self.campaign else None)
            return AICampaignIntelligence(self.controller.ai_service).insights(metrics)
        self.run(work,lambda r:self.ai_page.show_json('intelligence',r),'Analyzing permitted campaign totals…')
