"""Authenticated desktop shell reusing the existing Lead Workspace grid."""
import json
from types import SimpleNamespace
from PySide6.QtCore import Qt,QTimer,QThreadPool,QItemSelection,QItemSelectionModel
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QLabel,QListWidget,QStackedWidget,
    QTabBar,QToolButton,QMenu,QMessageBox,QInputDialog,QTableWidget,QTableWidgetItem,QHeaderView,QComboBox,QLineEdit,QSplitter,QProgressBar)
from app.ui_qt.team_controller import TeamController
from app.ui_qt.pages.leads_page import LeadsPage
from app.ui_qt.dialogs.team_dialogs import TeamTask,CampaignPicker,FormDialog,RowsDialog
from app.ui_qt.widgets.campaign_charts import CampaignCharts
from app.core.campaign_dashboard import CampaignProgress,parse_date
from app.ui_qt.qt_theme import build_stylesheet
from app.ui_qt.team_actions import TeamActions
from app.ui_qt.team_admin import TeamAdmin

from app.ui_qt.unified_shell import UnifiedShell
from app.ui_qt.unified_modules import UnifiedModules
from app.ui_qt.handoff_controls import HandoffControls

class TeamWindow(HandoffControls,UnifiedShell,UnifiedModules,TeamActions,TeamAdmin,QMainWindow):
    def __init__(self,client):
        super().__init__(); self.client=client; self.controller=TeamController(client)
        self.controller.error_callback=lambda msg:QMessageBox.information(self,'Lead Workspace',msg)
        self.busy=False; self._closing=False; self.campaign=None; self.sheet_rows=[]; self.offset=0; self.total=0; self.view='mine'; self.save_conflict=False
        self.modules={}; self.current_module='leads'; self._sidebar_collapsed=False; self._module_tasks=set()
        self.controller.request_module_action=self.request_module_action
        self.setWindowTitle('Lead Workspace · '+client.user['full_name']); self.resize(1540,940); self.setMinimumSize(1120,720)
        self.setStyleSheet(build_stylesheet('Professional Blue',False)); self.build_shell()
        self.autosave=QTimer(self); self.autosave.timeout.connect(self.auto_save); self.autosave.start(30000)
        self.poll=QTimer(self); self.poll.timeout.connect(self.poll_notifications); self.poll.start(45000)
        self.run(lambda:(self.client.call('campaigns'),self.client.call('preferences'),self.client.call('modules')),self.initialize,'Loading your workspace…')


    def build_workspace(self):
        self.workspace=QWidget(); layout=QVBoxLayout(self.workspace); layout.setContentsMargins(10,8,10,8); layout.setSpacing(5)
        self.scope=QComboBox(); self.scope.setMinimumWidth(190)
        for label,value in [('Working drafts','draft'),('Assigned / owned by me','mine'),('All permitted leads','all')]:self.scope.addItem(label,value)
        if self.client.user['role'] in ('Department Manager','Team Lead'):self.scope.addItem('My department','department')
        if self.client.user['role'] in ('Super User','Department Manager','Team Lead'):
            for label,value in [('Incoming transfers','incoming'),('Awaiting assignment','pending_assignment'),('Transferred leads','transferred')]:self.scope.addItem(label,value)
        if self.client.user['role']=='Super User':
            self.scope.setItemText(self.scope.findData('all'),'All leads')
            self.scope.addItem('Archived leads','archived')
            self.scope.addItem("Everyone's worksheets",'all_sheets')
        self.scope.setToolTip('Records in the selected campaign. Super Users can view all leads and everyone\'s active or archived worksheets. Use Campaign to switch campaigns.')
        self.scope.currentIndexChanged.connect(self.workspace_filter_changed)
        self.build_handoff_controls(); layout.addWidget(self.handoff_bar)
        self.sheet_bar=QWidget(); sheetbar=QHBoxLayout(self.sheet_bar); sheetbar.setContentsMargins(0,0,0,0); self.tabs=QTabBar(); self.tabs.setExpanding(False); self.tabs.setMovable(False); self.tabs.currentChanged.connect(self.switch_sheet)
        sheetbar.addWidget(self.tabs,1); plus=QPushButton('+'); plus.setFixedWidth(32); plus.setToolTip('Create a worksheet in your working drafts'); plus.clicked.connect(self.new_sheet); sheetbar.addWidget(plus)
        sheet_menu=QToolButton(); sheet_menu.setText('Sheets'); sheet_menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(sheet_menu)
        self.sheet_actions={}
        for label,fn in [('Rename sheet',self.rename_sheet),('Duplicate sheet',self.duplicate_sheet),('Delete sheet',self.delete_sheet)]: self.sheet_actions[label]=menu.addAction(label,fn)
        sheet_menu.setMenu(menu); sheetbar.addWidget(sheet_menu)
        self.leads=LeadsPage(self.controller,compact=True); layout.addWidget(self.leads,1)
        self.leads.heading_row.insertWidget(0,self.sheet_bar,1); self.leads.heading_row.setStretch(1,0)
        self.operations_bar=QWidget(); operations=QHBoxLayout(self.operations_bar); self.commit_button=QPushButton('Review & commit valid rows'); self.commit_button.setObjectName('primaryButton'); self.commit_button.clicked.connect(self.commit_draft)
        operations.addWidget(self.commit_button)
        self.workflow_buttons=[]; self.workspace_buttons={}
        for label,fn in [('Save',self.save),('Find / replace',self.find_replace),('Return for rework',self.return_rework),('View History',self.show_history)]:
            button=QPushButton(label); button.clicked.connect(fn); operations.addWidget(button)
            self.workspace_buttons[label]=button
            if label not in ('Save','Find / replace'):self.workflow_buttons.append((label,button)); button.hide()
        extras=QToolButton(); extras.setText('More'); extras.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup); menu=QMenu(extras)
        for label,fn in [('Comments',self.comments),('Transfer history',self.transfer_history),('Archive selected',self.archive_selected),('Restore selected',self.restore_selected),('Assign historical owner',self.assign_historical),('Save recovery draft',self.recover_draft),('Export validation errors',self.export_errors),('Save filter view',self.save_filter_view),('Load filter view',self.load_filter_view)]: menu.addAction(label,fn)
        self.workspace_more=extras
        extras.setMenu(menu); operations.addStretch(1); operations.addWidget(extras); layout.addWidget(self.operations_bar)
        self.page_bar=QWidget(); pagebar=QHBoxLayout(self.page_bar); self.previous=QPushButton('Previous'); self.next=QPushButton('Next'); self.previous.clicked.connect(lambda:self.page(-1)); self.next.clicked.connect(lambda:self.page(1))
        self.paging=QLabel(); self.query=QLineEdit(); self.query.setPlaceholderText('Search shared records in this campaign…'); self.query.returnPressed.connect(self.refresh_records)
        pagebar.addWidget(self.query,1); pagebar.addWidget(self.previous); pagebar.addWidget(self.paging); pagebar.addWidget(self.next); layout.addWidget(self.page_bar)
        from app.ui_qt.excel_workspace import ExcelWorkspace
        self.excel_workspace=ExcelWorkspace(self)

    def _wire_grid(self):
        p=self.leads
        p.table.selectionModel().selectionChanged.connect(self.update_handoff_controls)
        p.model.modelReset.connect(self.update_handoff_controls)
        # Campaign selection is already persistent in the shared shell header.
        p.workspace_label.setText('Records'); p.workspace_selector.hide()
        p._filter_widgets=(p.workspace_label,self.scope,p.search,p.status,p.clear_filters_btn)
        for action in p.more_menu.actions():
            if action.text().startswith('Add current leads to reference'):action.setVisible(False)
        p.empty_hint.setText('No leads yet. Open a personal worksheet to import, paste or enter leads, then validate and commit.')
        p.import_requested.connect(self.import_leads); p.export_requested.connect(self.export_leads); p.save_requested.connect(self.save)
        p.paste_requested.connect(p.table.paste_clipboard); p.new_requested.connect(self.new_sheet)
        p.validate_requested.connect(self.validate); p.validate_selected_requested.connect(lambda:self.validate(selected=True)); p.validate_edited_requested.connect(self.validate)
        p.recheck_requested.connect(lambda row:self.validate(indices=[row])); p.validation_summary_requested.connect(self.show_validation_summary)
        p.workspace_requested.connect(lambda cid:self.select_campaign_id(cid)); p.columns_added.connect(self.mark_dirty); p.model.changed.connect(self.mark_dirty)
        p.load_tal_requested.connect(lambda:self.configure_reference('tal')); p.load_suppression_requested.connect(lambda:self.configure_reference('suppression')); p.manage_references_requested.connect(self.show_campaign_configuration)
        p.populate_requested.connect(self.populate_reference); p.database_connection_requested.connect(self.configure_reference_database); p.add_to_database_requested.connect(self.add_reference_data)
        p.find_emails_requested.connect(self.find_emails)
        for table in (p.table,p.frozen_table):
            table.horizontalHeader().setSectionsMovable(True)
            table.authorized_copy=self.copy_authorized
        p.search.setToolTip('Find in the loaded sheet or page. Data → Search campaign searches all permitted campaign records.')


    def _dashboard(self):
        page=QWidget(); layout=QVBoxLayout(page); title=QLabel('Campaign dashboard'); title.setObjectName('pageTitle'); layout.addWidget(title)
        bar=QHBoxLayout(); select=QPushButton('Select Campaign'); select.clicked.connect(self.select_campaign); bar.addWidget(select)
        self.dashboard_scope=QComboBox()
        if self.client.user['role']=='Super User':self.dashboard_scope.addItem('All campaigns','all')
        self.dashboard_scope.addItem('Selected campaign','selected'); self.dashboard_scope.currentIndexChanged.connect(self.refresh_dashboard)
        self.dashboard_scope.setVisible(self.client.user['role']=='Super User'); bar.addWidget(self.dashboard_scope)
        refresh=QPushButton('Refresh'); refresh.clicked.connect(self.refresh_dashboard); bar.addWidget(refresh); bar.addStretch(1); layout.addLayout(bar)
        headers=['Campaign name','CID','Team Lead','Total allocation','Start date','End date','Total leads','Qualified leads','Disqualified leads','Delivered leads','Remaining to deliver','Average leads per day','Status']
        self.campaign_table=QTableWidget(0,len(headers)); self.campaign_table.setHorizontalHeaderLabels(headers); self.campaign_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.campaign_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); self.campaign_table.setAlternatingRowColors(True)
        self.campaign_table.itemDoubleClicked.connect(lambda item:self.select_campaign_id(self.campaign_table.item(item.row(),1).text()))
        split=QSplitter(Qt.Orientation.Vertical); split.addWidget(self.campaign_table); self.charts=CampaignCharts(self.controller); split.addWidget(self.charts); split.setSizes([350,270]); layout.addWidget(split,1)
        note=QLabel('Calendar-day target includes both dates and rounds up. Shared lead totals count each Lead ID once; only authorized records contribute.'); note.setWordWrap(True); note.setObjectName('muted'); layout.addWidget(note)
        return page

    def run(self,fn,done=None,message='Working…',cancellable=False):
        if self.busy or self._closing:return
        operation={'canceled':False}; self.active_operation=operation
        self.job_progress.show(); self.cancel_read.setVisible(cancellable); self.cancel_read.setEnabled(True)
        self.busy=True; self.status.setText(message); self.leads.set_data_busy(True); self.nav.setEnabled(False); self.tabs.setEnabled(False); self.scope.setEnabled(False)
        self.update_workspace_controls()
        task=TeamTask(fn); self.task=task
        def finish(value):
            self.job_progress.hide(); self.cancel_read.hide()
            self.busy=False; self.leads.set_data_busy(False); self.nav.setEnabled(True); self.tabs.setEnabled(True); self.scope.setEnabled(True); self.status.setText('Ready')
            self.update_workspace_controls()
            if operation['canceled']:self.status.setText('Canceled · results discarded; no draft changes applied.'); return
            if done:
                try: done(value)
                except Exception as exc: self.failed(str(exc))
        def failure(msg):
            self.job_progress.hide(); self.cancel_read.hide()
            self.busy=False; self.leads.set_data_busy(False); self.nav.setEnabled(True); self.tabs.setEnabled(True); self.scope.setEnabled(True); self.failed(msg)
            self.update_workspace_controls()
        task.signals.result.connect(finish); task.signals.error.connect(failure); QThreadPool.globalInstance().start(task)

    def cancel_preview(self):
        self.active_operation['canceled']=True; self.cancel_read.setEnabled(False)
        self.status.setText('Cancel requested. Waiting for the current read to finish; its results will be discarded.')

    def failed(self,message):
        if self._closing:return
        if self.controller.dirty:
            self.save_conflict=True
            message+='\nYour unsaved edits remain open. Use File > Save recovery draft to preserve them in a separate private sheet, or retry Save after the connection is restored.'
        self.status.setText(message); QMessageBox.warning(self,'Lead Workspace',message)
        if not self.client.token:
            self.leads.set_data_busy(True); self.status.setText('Session expired. Close this window and sign in again. Unsaved values remain in memory only.')


    def select_campaign(self):
        if self.busy:return
        dialog=CampaignPicker(self,self.controller.campaigns)
        if dialog.exec(): self.select_campaign_id(dialog.selected()['campaign_id'])




    def with_saved(self,fn):
        self.remember_view()
        if self.controller.dirty and self.allowed('leads'):self.save(after=fn)
        else:fn()

    def remember_view(self):
        if not self.campaign:return
        p=self.leads; headers=self.controller.data_manager.headers; header=p.table.horizontalHeader()
        settings={'search':p.search.text(),'status':p.status.currentText(),'view':p.view_selector.currentText(),
          'sort':headers[p.proxy.sortColumn()] if 0<=p.proxy.sortColumn()<len(headers) else None,'descending':p.proxy.sortOrder()==Qt.SortOrder.DescendingOrder,
          'filters':{headers[c]:list(v) for c,v in p.proxy.column_filters.items() if c<len(headers)},
          'conditions':{headers[c]:v for c,v in p.proxy.column_conditions.items() if c<len(headers)},
          'order':[headers[header.logicalIndex(i)] for i in range(len(headers))]}
        self.controller.settings_service.set('workspace_view_'+self.controller.workspace_key,settings)

    def restore_view(self):
        p=self.leads; headers=self.controller.data_manager.headers
        prefs=self.controller.settings_service; saved=prefs.get('workspace_view_'+self.controller.workspace_key,{})
        p.custom_views=prefs.get('lead_column_views',{})
        for name in p.custom_views:
            if p.view_selector.findText(name)<0:p.view_selector.addItem(name)
        name=saved.get('view',prefs.get('lead_last_view','All columns')); p.view_selector.setCurrentText(name)
        p.search.setText(saved.get('search','')); p.status.setCurrentText(saved.get('status','All'))
        for field,values in saved.get('filters',{}).items():
            if field in headers:p.proxy.set_column_filter(headers.index(field),set(values))
        for field,rule in saved.get('conditions',{}).items():
            if field in headers:p.proxy.set_condition(headers.index(field),rule)
        if saved.get('sort') in headers:p.proxy.sort(headers.index(saved['sort']),Qt.SortOrder.DescendingOrder if saved.get('descending') else Qt.SortOrder.AscendingOrder)
        for pane in (p.table,p.frozen_table):
            head=pane.horizontalHeader()
            for visual,field in enumerate(f for f in saved.get('order',[]) if f in headers):head.moveSection(head.visualIndex(headers.index(field)),visual)
        p.apply_column_view()

    def mark_dirty(self):
        if self.controller.dirty:self.status.setText('Unsaved changes'); self.leads.reference_label.setText(self.controller.reference_summary())

    def save(self,checked=False,after=None):
        if self.busy:return
        controller=self.controller
        if controller.read_only_sheet:
            if after:after()
            return
        selected=[self.leads.proxy.mapToSource(i) for i in self.leads.table.selectionModel().selectedIndexes()]
        cells=[(i.row(),i.column()) for i in selected]
        def restore_selection():
            selection=QItemSelection()
            for row,column in cells:
                index=self.leads.proxy.mapFromSource(self.leads.model.index(row,column))
                if index.isValid():selection.select(index,index)
            self.leads.table.selectionModel().select(selection,QItemSelectionModel.SelectionFlag.ClearAndSelect)
        if controller.mode=='draft' and controller.sheet:
            sid=controller.sheet['id']; version=controller.sheet['version']; payload=controller.draft_payload()
            def done(result):
                controller.sheet['version']=result['version']; payload['row_ids']=result['row_ids']; controller.sheet['payload']=payload
                controller.dirty=False; self.leads.refresh(); restore_selection()
                self.save_conflict=False
                if after:after()
            self.run(lambda:self.client.call('sheet_save',sheet_id=sid,version=version,payload=payload),done,'Saving private draft…')
        elif controller.mode=='records' and controller.pending_edits():
            edits=controller.pending_edits()
            def done(rows):
                mapping={r['id']:r for r in rows}; controller.load_leads({'rows':[mapping.get(r['id'],r) for r in controller.lead_rows]}); self.leads.refresh()
                restore_selection(); self.save_conflict=False
                if after:after()
            self.run(lambda:self.client.call('bulk_edit',edits=edits),done,'Saving authorized changes…')
        elif after:after()

    def auto_save(self):
        if self.busy or self.save_conflict:return
        self.remember_view()
        if self.controller.mode=='draft' and self.controller.dirty and self.allowed('leads'):self.save()
        elif self.controller.settings_service.dirty:
            dirty=dict(self.controller.settings_service.dirty)
            self.run(lambda:[self.client.call('preferences',key=k,value=v,save=True) for k,v in dirty.items()],lambda _:[self.controller.settings_service.dirty.pop(k,None) for k in dirty],'Saving your preferences…')

    def rebuild_tabs(self):
        self.tabs.blockSignals(True)
        while self.tabs.count():self.tabs.removeTab(0)
        for sheet in self.sheet_rows:
            label=sheet['name']
            if self.scope.currentData()=='all_sheets':label+=' · '+sheet['owner_name']+(' · Archived' if sheet['archived'] else '')
            index=self.tabs.addTab(label)
            self.tabs.setTabToolTip(index,f"{sheet['name']}\nOwner: {sheet.get('owner_name','')} (@{sheet.get('owner_username','')})\n"+('Read-only' if sheet.get('read_only') else 'Your working draft')+(' · Archived' if sheet.get('archived') else ''))
        self.tabs.blockSignals(False)

    def switch_sheet(self,index):
        if self.busy or index<0 or index>=len(self.sheet_rows):return
        self.with_saved(lambda:self.load_sheet(self.sheet_rows[index]['id']))

    def load_sheet(self,sid):
        def done(sheet):
            self.save_conflict=False; self.validation_result=None
            self.controller.load_sheet(sheet)
            self.set_workspace_mode('all_sheets' if self.scope.currentData()=='all_sheets' or sheet.get('read_only') else 'draft',load=False)
            key='last_inspected_sheet_' if self.scope.currentData()=='all_sheets' else 'last_sheet_'
            self.controller.settings_service.set(key+sheet['campaign_id'],sid)
            self.tabs.blockSignals(True); self.tabs.setCurrentIndex(next((i for i,s in enumerate(self.sheet_rows) if s['id']==sid),0)); self.tabs.blockSignals(False)
            self.leads.clear_filters(); self.leads.refresh(); self.restore_view(); self.update_workspace_controls(); self.status.setText(self.controller.reference_summary())
        self.run(lambda:self.client.call('sheet_load',sheet_id=sid),done,'Opening worksheet…')

    def new_sheet(self,checked=False,default=False):
        if self.busy or not self.campaign:return
        name,ok=('Sheet1',True) if default else QInputDialog.getText(self,'New worksheet','Sheet name:')
        if ok and name.strip():
            self.with_saved(lambda:self.run(lambda:self.client.call('sheet_create',campaign_id=self.campaign['campaign_id'],name=name.strip()),lambda result:self.open_own_sheet(result['id']),'Creating worksheet…'))

    def reload_sheets(self,sid=None,*,create_default=False):
        include_all=self.scope.currentData()=='all_sheets'
        def done(rows):
            self.sheet_rows=rows; self.rebuild_tabs()
            key='last_inspected_sheet_' if include_all else 'last_sheet_'
            wanted=sid or self.controller.settings_service.get(key+self.campaign['campaign_id'])
            target=next((i for i,r in enumerate(rows) if r['id']==wanted),0)
            if rows:
                self.tabs.blockSignals(True); self.tabs.setCurrentIndex(target); self.tabs.blockSignals(False); self.load_sheet(rows[target]['id'])
            else:
                self.controller._load([],[],[]); self.controller.mode='draft'; self.controller.sheet=None; self.controller.lead_rows=[]; self.controller.dirty=False; self.leads.refresh(); self.update_workspace_controls()
                if create_default and not include_all:self.new_sheet(default=True)
        self.run(lambda:self.client.call('sheets',campaign_id=self.campaign['campaign_id'],include_all=include_all),done)

    def open_own_sheet(self,sid):
        self.set_workspace_mode('draft',load=False); self.reload_sheets(sid)

    def rename_sheet(self):
        if self.busy or not self.controller.sheet or self.controller.read_only_sheet:return
        name,ok=QInputDialog.getText(self,'Rename worksheet','New name:',text=self.controller.sheet['name'])
        if ok:self.with_saved(lambda:self.run(lambda:self.client.call('sheet_rename',sheet_id=self.controller.sheet['id'],version=self.controller.sheet['version'],name=name),lambda _:self.reload_sheets(self.controller.sheet['id'])))

    def duplicate_sheet(self):
        if self.busy or not self.controller.sheet:return
        name,ok=QInputDialog.getText(self,'Duplicate worksheet','Copy name:',text=self.controller.sheet['name']+' copy')
        if ok:self.with_saved(lambda:self.run(lambda:self.client.call('sheet_create',campaign_id=self.campaign['campaign_id'],name=name,duplicate_id=self.controller.sheet['id']),lambda r:self.open_own_sheet(r['id'])))

    def delete_sheet(self):
        sheet=self.controller.sheet
        if self.busy or not sheet or self.controller.read_only_sheet:return
        if QMessageBox.question(self,'Delete worksheet','Archive this private sheet? Committed leads and their history will remain. Unsaved draft edits will be discarded.')!=QMessageBox.StandardButton.Yes:return
        self.run(lambda:self.client.call('sheet_delete',sheet_id=sheet['id'],version=sheet['version']),lambda _:self.reload_sheets())

    def refresh_records(self):
        if self.busy or not self.campaign:return
        def done(result):
            self.save_conflict=False
            self.total=result['total']; self.validation_result=None; self.controller.load_leads(result); self.leads.refresh(); self.restore_view()
            self.paging.setText(f"{min(self.offset+1,self.total)}–{min(self.offset+len(result['rows']),self.total)} of {self.total:,}")
            self.previous.setEnabled(self.offset>0); self.next.setEnabled(self.offset+200<self.total)
            self.update_handoff_controls()
        self.with_saved(lambda:self.run(lambda:self.client.call('leads',campaign_id=self.campaign['campaign_id'],view=self.view,archived=self.view=='archived',offset=self.offset,limit=200,search=self.query.text().strip()),done,'Loading authorized leads…'))

    def page(self,direction): self.with_saved(lambda:self._page(direction))
    def _page(self,direction): self.offset=max(0,self.offset+direction*200); self.refresh_records()

    def refresh_dashboard(self,*_):
        if self.busy:return
        def done(rows):
            if self.campaign and self.dashboard_scope.currentData()!='all': rows=[r for r in rows if r['campaign_id']==self.campaign['campaign_id']]
            keys=['campaign_name','campaign_id','team_lead','allocation','start','end','total','qualified','disqualified','delivered','remaining','average','status']
            self.campaign_table.setRowCount(len(rows))
            for i,row in enumerate(rows):
                for j,key in enumerate(keys): self.campaign_table.setItem(i,j,QTableWidgetItem(str(row[key]) if row[key] is not None else 'Not set'))
            self.campaign_table.resizeColumnsToContents()
            self.charts.refresh([CampaignProgress(r['campaign_id'],r['campaign_name'],r['allocation'],parse_date(r['start']),parse_date(r['end']),r['total'],r['qualified'],r['disqualified'],r['delivered'],r['status']) for r in rows])
        self.run(lambda:self.client.call('dashboard'),done,'Loading campaign metrics…')


    def sign_out(self):
        if self.busy:return
        if not self.can_leave_unsaved():return
        self.with_saved(lambda:self.run(self.client.logout,lambda _:self._finish_close(),'Signing out…'))

    def can_leave_unsaved(self):
        if self.controller.dirty and not self.allowed('leads'):
            return QMessageBox.question(self,'Unsaved edits','Lead Workspace access was removed, so these edits cannot be saved. Close and discard the unsaved edits? Cancel keeps them in memory until access is restored.')==QMessageBox.StandardButton.Yes
        return True

    def _finish_close(self):
        self._closing=True; self.autosave.stop(); self.poll.stop()
        def finish():
            self.controller.shutdown_local_tools(); self.close()
        if hasattr(self,'scraper_page'):self.scraper_page.shutdown(finish)
        else:finish()

    def closeEvent(self,event):
        if self._closing:
            self.autosave.stop(); self.poll.stop()
            if hasattr(self,'scraper_page') and not (self.scraper_page.worker and self.scraper_page.worker.is_alive()):self.scraper_page.timer.stop()
            self.controller.shutdown_local_tools(); event.accept(); return
        if self.busy:event.ignore(); return
        if not self.can_leave_unsaved():event.ignore(); return
        if self.controller.dirty:
            event.ignore(); self.with_saved(lambda:self.run(self.client.logout,lambda _:self._finish_close())); return
        event.ignore(); self.run(self.client.logout,lambda _:self._finish_close())
