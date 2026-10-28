"""One navigation shell for research, lead operations and administration."""
from types import SimpleNamespace
from PySide6.QtCore import Qt, QSize, QThreadPool
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QStackedWidget, QComboBox, QToolButton, QMenu, QProgressBar,
    QMessageBox)
from app.team.modules import MODULES
from app.ui_qt.dialogs.team_dialogs import TeamTask
from app.ui_qt.widgets.icons import icon


class UnifiedShell:
    def build_shell(self):
        root=QWidget(); root.setObjectName('appRoot'); self.setCentralWidget(root)
        outer=QHBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        self.sidebar=QFrame(); self.sidebar.setObjectName('sideBar'); self.sidebar.setFixedWidth(210)
        side=QVBoxLayout(self.sidebar); side.setContentsMargins(10,20,10,12); side.setSpacing(10)
        brand=QHBoxLayout(); mark=QLabel('LW'); mark.setObjectName('brandMark'); mark.setFixedSize(36,36); mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.brand_label=QLabel('Lead Workspace'); self.brand_label.setObjectName('appTitle')
        brand.addWidget(mark); brand.addWidget(self.brand_label); side.addLayout(brand)
        self.nav=QListWidget(); self.nav.setObjectName('moduleNavigation'); self.nav.setIconSize(QSize(19,19)); self.nav.setSpacing(3)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); side.addWidget(self.nav,1)
        self.account_note=QLabel(self.client.user['full_name']+'\n'+self.client.user['role']); self.account_note.setTextFormat(Qt.TextFormat.PlainText)
        self.account_note.setWordWrap(True); self.account_note.setObjectName('sidebarNote'); side.addWidget(self.account_note); outer.addWidget(self.sidebar)
        content=QVBoxLayout(); content.setContentsMargins(0,0,0,0); content.setSpacing(0); outer.addLayout(content,1)
        top=QFrame(); top.setObjectName('topBar'); bar=QHBoxLayout(top); bar.setContentsMargins(12,8,12,8)
        toggle=QPushButton(); toggle.setIcon(icon('menu')); toggle.setToolTip('Collapse or expand navigation'); toggle.setAccessibleName('Toggle navigation'); toggle.setFixedSize(32,32); toggle.clicked.connect(self.toggle_sidebar); bar.addWidget(toggle)
        self.page_title=QLabel('Lead Workspace'); self.page_title.setObjectName('sectionTitle'); bar.addWidget(self.page_title)
        bar.addStretch(1); self.campaign_badge=QLabel('No campaign selected'); self.campaign_badge.setObjectName('badge'); self.campaign_badge.setTextFormat(Qt.TextFormat.PlainText); self.campaign_badge.setMaximumWidth(260); bar.addWidget(self.campaign_badge)
        choose=QPushButton('Campaign'); choose.setToolTip('Select campaign'); choose.clicked.connect(self.select_campaign); bar.addWidget(choose)
        self.notification_button=QPushButton('Notifications'); self.notification_button.clicked.connect(self.show_notifications); bar.addWidget(self.notification_button)
        account=QToolButton(); account.setText('Account'); account.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(account); menu.addAction('Refresh my access',self.refresh_access); menu.addAction('Change password…',self.change_password); menu.addAction('Sign out',self.sign_out); account.setMenu(menu); bar.addWidget(account)
        content.addWidget(top); self.stack=QStackedWidget(); content.addWidget(self.stack,1)
        self.build_workspace()
        self.dashboard=self._dashboard(); self.admin_page=self.build_admin_page(); self.campaign_page=self.build_campaign_page(); self.report_page=self.build_report_page()
        self.module_pages={'leads':self.workspace,'dashboard':self.dashboard,'campaigns':self.campaign_page,'administration':self.admin_page,'reports':self.report_page}
        self.welcome=QLabel('Loading your modules…'); self.welcome.setAlignment(Qt.AlignmentFlag.AlignCenter); self.stack.addWidget(self.welcome)
        for page in self.module_pages.values():self.stack.addWidget(page)
        self.stack.setCurrentWidget(self.welcome)
        self.items=[]; self.nav.currentRowChanged.connect(lambda i:self.navigate(self.nav.item(i).data(Qt.ItemDataRole.UserRole)) if i>=0 else None)
        self.status=QLabel('Connecting…'); self.statusBar().addWidget(self.status,1)
        self.job_progress=QProgressBar(); self.job_progress.setRange(0,0); self.job_progress.setMaximumWidth(110); self.job_progress.hide(); self.statusBar().addPermanentWidget(self.job_progress)
        self.cancel_read=QPushButton('Cancel'); self.cancel_read.hide(); self.cancel_read.setToolTip('Discard the current preview when it returns.'); self.cancel_read.clicked.connect(self.cancel_preview); self.statusBar().addPermanentWidget(self.cancel_read)
        self._wire_grid()
        for sequence,module in [('Ctrl+1','scraper'),('Ctrl+2','leads'),('Ctrl+3','campaigns'),('Ctrl+,','settings'),('F1','info')]:
            shortcut=QShortcut(QKeySequence(sequence),self); shortcut.activated.connect(lambda m=module:self.navigate(m))

    def toggle_sidebar(self):
        self.nav.blockSignals(True)
        self._sidebar_collapsed=not self._sidebar_collapsed
        self.sidebar.setFixedWidth(62 if self._sidebar_collapsed else 210)
        self.brand_label.setVisible(not self._sidebar_collapsed); self.account_note.setVisible(not self._sidebar_collapsed)
        for i,label in enumerate(self.items):self.nav.item(i).setText('' if self._sidebar_collapsed else label)
        self.nav.blockSignals(False)
        # Use item data for collapsed navigation instead of empty display text.

    def allowed(self,module):
        return module=='info' or bool(self.modules.get(module,{}).get('allowed'))

    def apply_modules(self,modules):
        previous=self.current_module; old=self.modules; self.modules=modules
        self.controller.module_access=modules
        self.nav.blockSignals(True); self.nav.clear(); self.items=[]
        for key,label in [*MODULES.items(),('info','Help & Support')]:
            if not self.allowed(key):continue
            item=QListWidgetItem(icon({'reports':'dashboard','administration':'settings'}.get(key,key)),'' if self._sidebar_collapsed else label)
            item.setData(Qt.ItemDataRole.UserRole,key); item.setToolTip(label); item.setSizeHint(QSize(180,37)); self.nav.addItem(item); self.items.append(label)
        selected=previous if self.allowed(previous) else ('leads' if self.allowed('leads') else self.nav.item(0).data(Qt.ItemDataRole.UserRole))
        self.current_module=selected
        self.nav.setCurrentRow(next(i for i in range(self.nav.count()) if self.nav.item(i).data(Qt.ItemDataRole.UserRole)==selected)); self.nav.blockSignals(False)
        if old and old.get('scraper',{}).get('allowed') and not self.allowed('scraper') and hasattr(self,'scraper_page'):
            self.scraper_page.stop(); self.scraper_page.setEnabled(False)
        for key,page in self.module_pages.items():page.setEnabled(self.allowed(key))
        if old and not self.allowed(previous):
            self.stack.setCurrentWidget(self.welcome); self.welcome.setText('Your module access has changed. Select an available module.')
            self.status.setText('Access updated. Restricted modules are closed; unsaved edits remain in memory.')
        if not self.allowed('leads'):
            self.leads.setEnabled(False)
        elif old and not old.get('leads',{}).get('allowed') and self.campaign:
            # Reload current campaign policies before editing after a grant.
            self.select_campaign_id(self.campaign['campaign_id'])
        if hasattr(self,'excel_workspace'):self.update_workspace_controls()

    def initialize(self,result):
        campaigns,prefs,modules=result; self.controller.campaigns=campaigns; self.controller.settings_service.values=prefs
        saved_scope=prefs.get('workspace_scope')
        if saved_scope and self.scope.findData(saved_scope)>=0:
            self.scope.blockSignals(True); self.scope.setCurrentIndex(self.scope.findData(saved_scope)); self.scope.blockSignals(False)
        self.controller.load_settings(); self.apply_theme(); self.apply_modules(modules)
        self.autosave.setInterval(max(15,self.controller.settings.autosave_interval_seconds)*1000)
        self.leads._view_widths=prefs.get('lead_column_widths',{}); self.leads.update_workspaces()
        self.leads._view_orders=prefs.get('lead_column_orders',{})
        if prefs.get('ribbon_collapsed') and hasattr(self,'excel_workspace'):
            self.excel_workspace.set_collapsed(True,persist=False)
        cid=prefs.get('last_campaign'); campaign=next((c for c in campaigns if c['campaign_id']==cid),campaigns[0] if campaigns else None)
        if campaign:self.select_campaign_id(campaign['campaign_id'])
        else:
            self.show_module(self.current_module)
            self.status.setText('No assigned campaigns. Create or assign a campaign in Campaign Manager.')

    def select_campaign_id(self,cid):
        if self.busy or not cid:return
        campaign=next((c for c in self.controller.campaigns if c['campaign_id']==cid),None)
        if not campaign:return
        def switch():
            self.campaign=campaign; self.controller.active_campaign=SimpleNamespace(**campaign)
            self.controller.settings_service.set('last_campaign',cid)
            self.campaign_badge.setText(campaign['campaign_name']+' · '+cid); self.campaign_badge.setToolTip(campaign['campaign_name']+' · '+cid); self.leads.update_workspaces()
            if self.allowed('leads'):
                self.run(lambda:(self.client.call('sheets',campaign_id=cid),self.client.call('field_access',campaign_id=cid)),self.campaign_loaded,'Opening campaign…')
            else:self.show_module(self.current_module)
        self.with_saved(switch)

    def campaign_loaded(self,result):
        sheets,permissions=result; self.controller.field_permissions=permissions; self.sheet_rows=sheets
        self.controller._load([],[],[]); self.controller.sheet=None; self.controller.lead_rows=[]; self.validation_result=None
        self.rebuild_tabs(); self.leads.refresh(); self.show_module(self.current_module)

    def navigate(self,name):
        if self.busy or self._closing:return
        item=self.nav.currentItem()
        module=next((key for key,label in MODULES.items() if name in (key,label)),None)
        if name in ('info','Help & Support'):module='info'
        if not name and item:module=item.data(Qt.ItemDataRole.UserRole)
        if not module:return
        if not self.allowed(module):
            QMessageBox.information(self,'Module access','Your account does not have access to this module. Contact your Super User.'); return
        def open_page():
            if module=='info':self.show_module(module)
            else:self.run(lambda:self.client.call('module_check',module=module),lambda _:self.show_module(module),'Checking module access…')
        self.with_saved(open_page)

    def show_module(self,module):
        if not self.allowed(module):return
        self.current_module=module; label=MODULES.get(module,'Help & Support'); self.page_title.setText(label)
        self.nav.blockSignals(True)
        for i in range(self.nav.count()):
            if self.nav.item(i).data(Qt.ItemDataRole.UserRole)==module:self.nav.setCurrentRow(i); break
        self.nav.blockSignals(False)
        if module not in self.module_pages:
            page=self.create_module_page(module); self.module_pages[module]=page; self.stack.addWidget(page)
        self.stack.setCurrentWidget(self.module_pages[module])
        if module=='leads':self.open_workspace_filter()
        elif module=='dashboard':self.refresh_dashboard()
        elif module=='campaigns':self.refresh_campaigns()
        elif module=='administration':self.refresh_admin()
        elif module=='reports':self.refresh_report()
        elif module=='tools':self.refresh_tools()
        elif module=='validation':self.refresh_validation_page()
        elif module=='ai':self.update_ai_selection()

    def set_workspace_mode(self,value,load=True):
        self.scope.blockSignals(True); self.scope.setCurrentIndex(max(0,self.scope.findData(value))); self.scope.blockSignals(False)
        self.update_workspace_controls()
        if load:self.open_workspace_filter()

    def update_workspace_controls(self):
        draft=self.scope.currentData() in ('draft','all_sheets'); self.sheet_bar.setVisible(draft); self.commit_button.setVisible(draft and self.allowed('validation'))
        editable=draft and self.controller.sheet is not None and not self.controller.read_only_sheet and not self.busy
        self.commit_button.setEnabled(editable)
        self.workspace_buttons['Save'].setEnabled(not self.busy and not self.controller.read_only_sheet)
        for name,action in self.sheet_actions.items():
            action.setEnabled(bool(self.controller.sheet) and not self.busy and (name=='Duplicate sheet' or editable))
        for control in self.leads.validation_actions.findChildren((QPushButton)):
            if control.text() in ('Validate','Summary'):control.setVisible(self.allowed('validation'))
        for control in self.leads.validation_actions.findChildren(QToolButton):
            if control.text()=='Rows':control.setVisible(self.allowed('validation'))
        for label,button in self.workflow_buttons:button.setVisible(not draft and not(label in ('Assign','Push to Department') and self.client.user['role']=='Employee'))
        for widget in (self.previous,self.next,self.query,self.paging):widget.setVisible(not draft)
        self.leads.empty_hint.setText('No worksheets in this campaign. Use Campaign to choose another.' if self.scope.currentData()=='all_sheets' else 'Import, paste or enter leads in a working draft, then validate and commit.' if draft else 'No leads match this filter. Choose another view or search.')
        self.update_handoff_controls()
        if hasattr(self,'excel_workspace'):self.excel_workspace.update_mode()

    def workspace_filter_changed(self):
        if self.busy:return
        self.with_saved(self.open_workspace_filter)

    def open_workspace_filter(self):
        self.update_workspace_controls()
        self.controller.settings_service.set('workspace_scope',self.scope.currentData())
        if not self.campaign:return
        if self.scope.currentData() in ('draft','all_sheets'):
            self.reload_sheets(create_default=self.scope.currentData()=='draft')
        else:
            self.view=self.scope.currentData(); self.offset=0; self.query.clear(); self.refresh_records()

    def request_module_action(self,module,callback,on_denied=None):
        if self._closing:return
        task=TeamTask(lambda:self.client.call('module_check',module=module)); self._module_tasks.add(task)
        def done(_):
            self._module_tasks.discard(task)
            if not self._closing:
                try:callback()
                except Exception as exc:self.failed(str(exc))
            elif on_denied:on_denied()
        def failed(message):
            self._module_tasks.discard(task)
            if on_denied:on_denied()
            if self._closing:return
            if module=='scraper' and hasattr(self,'scraper_page'):
                self.scraper_page.stop(); self.scraper_page._set_running(False)
            QMessageBox.warning(self,'Module access',message)
        task.signals.result.connect(done); task.signals.error.connect(failed); QThreadPool.globalInstance().start(task)

    def refresh_access(self):
        self.run(lambda:self.client.call('modules'),self.apply_modules,'Refreshing module access…')

    def poll_notifications(self):
        if self.busy or self._closing or getattr(self,'_polling',False):return
        self._polling=True; task=TeamTask(lambda:(self.client.call('modules'),self.client.call('notifications'))); self.poll_task=task
        def finish(result):
            self._polling=False
            if self._closing:return
            modules,notifications=result
            if modules!=self.modules:self.apply_modules(modules)
            self.notification_button.setText(f"Notifications ({notifications['unread']})")
        def failed(message):
            self._polling=False
            # Pause local activity when access cannot be revalidated.
            if hasattr(self,'scraper_page') and self.scraper_page.processing:self.scraper_page.pause()
            self.status.setText('Connection/access check failed: '+message)
        task.signals.result.connect(finish); task.signals.error.connect(failed); QThreadPool.globalInstance().start(task)
