"""Account, campaign and policy forms for the authenticated desktop."""
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QPushButton,QTableWidget,QTableWidgetItem,QTabWidget,QComboBox,QLabel,
    QMessageBox,QInputDialog,QFileDialog,QListWidget,QListWidgetItem,QDialog,QDialogButtonBox)
from app.ui_qt.dialogs.team_dialogs import FormDialog,RowsDialog
from app.team.schema import ROLES,STATES
from app.constants import STANDARD_HEADERS
from app.ui_qt.module_guard import authorized

class TeamAdmin:
    def build_admin_page(self):
        page=QWidget(); layout=QVBoxLayout(page); title=QLabel('Administration'); title.setObjectName('pageTitle'); layout.addWidget(title)
        self.admin_tabs=QTabWidget(); layout.addWidget(self.admin_tabs,1); self.admin_tables={}
        for name,actions in [('Users',[('Create user',self.new_user),('Edit selected user',self.edit_user),('Assign campaign',self.assign_campaign_users),('Remove campaign access',lambda:self.assign_campaign_users(remove=True))]),
                             ('Departments',[('Create department',self.new_department),('Edit selected department',self.edit_department)]),
                             ('Policies',[('Add / edit policy',self.edit_policy)])]:
            tab=QWidget(); body=QVBoxLayout(tab); toolbar=QHBoxLayout(); body.addLayout(toolbar)
            for text,fn in actions: button=QPushButton(text); button.clicked.connect(fn); toolbar.addWidget(button)
            refresh=QPushButton('Refresh'); refresh.clicked.connect(self.refresh_admin); toolbar.addWidget(refresh); toolbar.addStretch(1)
            table=QTableWidget(); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); table.setAlternatingRowColors(True)
            body.addWidget(table,1); self.admin_tables[name]=table; self.admin_tabs.addTab(tab,name)
        self.admin_tabs.addTab(self.build_module_access_page(),'Module Access')
        return page

    def build_campaign_page(self):
        page=QWidget(); body=QVBoxLayout(page); title=QLabel('Campaign Manager'); title.setObjectName('pageTitle'); body.addWidget(title)
        toolbar=QHBoxLayout(); body.addLayout(toolbar)
        if self.client.user['role']=='Super User':
            actions=[('Create campaign',self.new_campaign),('Edit configuration',self.show_campaign_configuration),('Import package',self.import_campaign_package),('Review rules',self.review_campaign_rules),('Historical worksheets',self.legacy_snapshots)]
        else:actions=[]
        for text,fn in actions:
            button=QPushButton(text); button.clicked.connect(fn); toolbar.addWidget(button)
        refresh=QPushButton('Refresh'); refresh.clicked.connect(self.refresh_campaigns); toolbar.addWidget(refresh); toolbar.addStretch(1)
        note=QLabel('Double-click a campaign to select it for this workspace. Configuration and reference lists are managed by your Super User.'); note.setWordWrap(True); body.addWidget(note)
        table=QTableWidget(); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows); table.setAlternatingRowColors(True)
        table.itemDoubleClicked.connect(lambda item:self.select_campaign_id(item.data(Qt.ItemDataRole.UserRole)['campaign_id']))
        body.addWidget(table,1); self.admin_tables['Campaigns']=table
        return page

    def display_campaigns(self,campaigns):
        self.controller.campaigns=campaigns
        if self.campaign:self.campaign=next((c for c in campaigns if c['campaign_id']==self.campaign['campaign_id']),self.campaign)
        self.fill_table(self.admin_tables['Campaigns'],[{'campaign_id':r['campaign_id'],'campaign_name':r['campaign_name'],
            'version':r['version'],'client':r['config'].get('client',''),'allocation':r['config'].get('allocation',''),
            'start_date':r['config'].get('start_date',''),'end_date':r['config'].get('end_date',''),'status':r['config'].get('status','Not set')} for r in campaigns])
        self.leads.update_workspaces()

    def refresh_campaigns(self):
        self.run(lambda:self.client.call('campaigns'),self.display_campaigns,'Loading campaigns…')

    def build_module_access_page(self):
        page=QWidget(); body=QVBoxLayout(page)
        note=QLabel('Choose a department default or an individual user override. User overrides take priority over department settings. '
                    'Inherit removes the override. Module access never grants extra record, field or workflow rights. Super Users retain full access.'); note.setWordWrap(True); body.addWidget(note)
        bar=QHBoxLayout(); self.access_kind=QComboBox(); self.access_kind.addItem('Department','department'); self.access_kind.addItem('Individual user','user')
        self.access_subject=QComboBox(); self.access_subject.setMinimumWidth(260); bar.addWidget(self.access_kind); bar.addWidget(self.access_subject,1)
        reload=QPushButton('Load access'); reload.clicked.connect(self.load_module_policy); bar.addWidget(reload)
        save=QPushButton('Save module access'); save.setObjectName('primaryButton'); save.clicked.connect(self.save_module_policy); bar.addWidget(save); body.addLayout(bar)
        self.access_table=QTableWidget(0,3); self.access_table.setHorizontalHeaderLabels(['Module','Access','Effective access']); self.access_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.access_table.horizontalHeader().setStretchLastSection(True); body.addWidget(self.access_table,1); self.access_controls={}; self.access_loaded_subject=None
        self.access_kind.currentIndexChanged.connect(self.refresh_access_subjects); self.access_subject.currentIndexChanged.connect(self.load_module_policy)
        return page

    def refresh_access_subjects(self):
        directory=getattr(self,'directory',{}); kind=self.access_kind.currentData(); current=self.access_subject.currentData()
        self.access_subject.blockSignals(True); self.access_subject.clear()
        for row in directory.get('users' if kind=='user' else 'departments',[]):
            self.access_subject.addItem(row['full_name']+' · '+row['role'] if kind=='user' else row['name'],row['id'])
        self.access_subject.setCurrentIndex(max(0,self.access_subject.findData(current))); self.access_subject.blockSignals(False)
        self.load_module_policy()

    def load_module_policy(self):
        if self.busy or not self.access_subject.currentData():return
        kind,subject=self.access_kind.currentData(),self.access_subject.currentData()
        self.access_loaded_subject=None
        def done(result):
            if (kind,subject)!=(self.access_kind.currentData(),self.access_subject.currentData()):self.load_module_policy();return
            self.access_loaded_subject=(kind,subject); self.access_controls={}; self.access_table.setRowCount(len(result['modules']))
            for i,(module,label) in enumerate(result['modules'].items()):
                self.access_table.setItem(i,0,QTableWidgetItem(label)); control=QComboBox()
                for name,value in [('Inherit',None),('Allow',True),('Deny',False)]:control.addItem(name,value)
                value=result['overrides'].get(module); control.setCurrentIndex(0 if value is None else 1 if value else 2)
                control.setEnabled(module!='administration'); self.access_table.setCellWidget(i,1,control); self.access_controls[module]=control
                effective=result['effective'].get(module)
                if effective:text=('Allowed' if effective['allowed'] else 'Denied')+' · '+effective['source']
                elif module=='administration':text='Super User only'
                elif value is None:text=('Denied' if module=='tools' or (module=='scraper' and subject in ('quality','delivery')) else 'Allowed')+' · Default'
                else:text='Department: '+('Allowed' if value else 'Denied')
                self.access_table.setItem(i,2,QTableWidgetItem(text))
            self.access_table.resizeColumnsToContents()
        self.run(lambda:self.client.call('module_policy',subject_type=kind,subject_id=subject),done,'Loading module access…')

    def save_module_policy(self):
        if self.busy:return
        key=(self.access_kind.currentData(),self.access_subject.currentData())
        if key!=self.access_loaded_subject:return
        values={k:c.currentData() for k,c in self.access_controls.items() if k!='administration'}
        self.run(lambda:self.client.call('module_policy_save',subject_type=key[0],subject_id=key[1],overrides=values),lambda _:self.load_module_policy(),'Saving module permissions…')

    def fill_table(self,table,rows):
        headers=list(dict.fromkeys(k for r in rows for k in r)); table.setColumnCount(len(headers)); table.setHorizontalHeaderLabels(headers); table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            for j,key in enumerate(headers):
                item=QTableWidgetItem(str(row.get(key,''))); item.setData(Qt.ItemDataRole.UserRole,row); item.setToolTip(str(row.get(key,''))); table.setItem(i,j,item)
        table.resizeColumnsToContents()

    def selected_admin(self,name):
        table=self.admin_tables[name]; item=table.item(table.currentRow(),0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def refresh_admin(self):
        if self.busy:return
        def done(data):
            directory,campaigns,policy=data; self.directory=directory; self.controller.campaigns=campaigns; self.policy=policy
            if self.campaign:self.campaign=next((c for c in campaigns if c['campaign_id']==self.campaign['campaign_id']),self.campaign)
            self.fill_table(self.admin_tables['Users'],directory['users']); self.fill_table(self.admin_tables['Departments'],directory['departments'])
            self.display_campaigns(campaigns)
            self.fill_table(self.admin_tables['Policies'],[{'kind':kind,**row} for kind,rows in policy.items() for row in rows])
            self.leads.update_workspaces()
            if self.stack.currentWidget()==self.admin_page:self.refresh_access_subjects()
        self.run(lambda:(self.client.call('directory'),self.client.call('campaigns'),self.client.call('policy')),done,'Loading administration…')

    def new_user(self):self.user_form({})
    def edit_user(self):
        if row:=self.selected_admin('Users'):self.user_form(row)
    def user_form(self,row):
        if self.busy:return
        directory=getattr(self,'directory',{'users':[],'departments':[]}); choices=lambda role:[('Unassigned',None)]+[(u['full_name'],u['id']) for u in directory['users'] if u['role']==role and u['active']]
        fields={'full_name':('Full name',row.get('full_name',''),None),'username':('Username',row.get('username',''),None),'email':('Email',row.get('email',''),None),
                'password':('Password (blank keeps current)', '',None),'role':('Role',row.get('role','Employee'),[(r,r) for r in ROLES]),
                'department_id':('Department',row.get('department_id'),[('Unassigned',None)]+[(d['name'],d['id']) for d in directory['departments'] if d['active']]),
                'manager_id':('Reporting manager',row.get('manager_id'),choices('Department Manager')),
                'team_lead_id':('Assigned Team Lead',row.get('team_lead_id'),choices('Team Lead')),'active':('Active account',bool(row.get('active',True)),None)}
        dialog=FormDialog(self,'Edit user' if row else 'Create user',fields)
        if dialog.exec():
            values=dialog.values(); values['password']=values['password'] or None
            self.run(lambda:self.client.call('user_save',id=row.get('id'),**values),lambda _:self.refresh_admin(),'Saving user and revoking previous sessions…')

    def new_department(self):self.department_form({})
    def edit_department(self):
        if row:=self.selected_admin('Departments'):self.department_form(row)
    def department_form(self,row):
        dialog=FormDialog(self,'Department',{'name':('Name',row.get('name',''),None),'active':('Active',bool(row.get('active',True)),None)})
        if dialog.exec():self.run(lambda:self.client.call('department_save',id=row.get('id'),**dialog.values()),lambda _:self.refresh_admin())

    def choose_users(self,title,users):
        dialog=QDialog(self); dialog.setWindowTitle(title); layout=QVBoxLayout(dialog); listing=QListWidget(); layout.addWidget(listing)
        for user in users:
            item=QListWidgetItem(user['full_name']+' · '+user['role']); item.setData(Qt.ItemDataRole.UserRole,user['id']); item.setCheckState(Qt.CheckState.Unchecked); listing.addItem(item)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        return [listing.item(i).data(Qt.ItemDataRole.UserRole) for i in range(listing.count()) if listing.item(i).checkState()==Qt.CheckState.Checked] if dialog.exec() else []

    def assign_campaign_users(self,checked=False,remove=False):
        if not self.campaign: self.select_campaign();return
        users=self.choose_users('Remove campaign access' if remove else 'Assign users to '+self.campaign['campaign_name'],getattr(self,'directory',{}).get('users',[]))
        if users:self.run(lambda:self.client.call('campaign_assign',campaign_id=self.campaign['campaign_id'],user_ids=users,remove=remove),lambda _:self.refresh_admin())

    def new_campaign(self):self.campaign_form(None)
    def show_campaign_configuration(self):
        row=self.selected_admin('Campaigns') if self.stack.currentWidget()==self.campaign_page else None
        campaign=next((c for c in self.controller.campaigns if c['campaign_id']==row['campaign_id']),None) if row else self.campaign
        if campaign:self.campaign_form(campaign)

    def campaign_form(self,campaign):
        if self.client.user['role']!='Super User':
            QMessageBox.information(self,'Campaign configuration','Campaign configuration and reference lists are managed by your Super User.');return
        config=(campaign or {}).get('config',{})
        departments=getattr(self,'directory',{}).get('departments',[{'name':n,'id':n.lower(),'active':True} for n in ('Operations','Quality','DBA','Delivery')])
        fields={'campaign_id':('CID',(campaign or {}).get('campaign_id',''),None),'campaign_name':('Campaign name',(campaign or {}).get('campaign_name',''),None),
                'client':('Client',config.get('client',''),None),'allocation':('Total allocation',str(config.get('allocation','')),None),
                'delivered':('Cumulative delivered count (blank uses workflow)',str(config.get('delivered','')),None),
                'departments':('Active departments (empty permits all)',config.get('departments',[]),[(d['name'],d['id']) for d in departments if d['active']]),
                'domain_cap_default':('Default leads per company (blank is unlimited)',str(config.get('domain_cap_default','')),None),
                'start_date':('Start date (YYYY-MM-DD)',config.get('start_date',''),None),'end_date':('End date (YYYY-MM-DD)',config.get('end_date',''),None),
                'status':('Status',config.get('status','Running'),[(s,s) for s in ('Running','Paused','Closed','Archived')]),
                'require_tal_match':('Require account list match',config.get('require_tal_match',True),None),'enable_suppression':('Check suppression',config.get('enable_suppression',True),None),
                'review_required':('Require explicit Team Lead review queue',config.get('review_required',True),None),
                'required_fields':('Additional mandatory headers (comma separated)',', '.join(config.get('required_fields',[])),None),
                'duplicate_keys':('Duplicate checks',','.join(config.get('duplicate_keys',['email','linkedin','person_domain'])),[('Email, LinkedIn and name + domain','email,linkedin,person_domain'),('Email and LinkedIn','email,linkedin'),('Email','email'),('LinkedIn','linkedin')])}
        dialog=FormDialog(self,'Campaign configuration',fields)
        if campaign:dialog.controls['campaign_id'].setReadOnly(True)
        if not dialog.exec():return
        values=dialog.values(); cid=values.pop('campaign_id'); name=values.pop('campaign_name')
        try:
            for field in ('allocation','delivered','domain_cap_default'): values[field]=int(values[field].replace(',','')) if values[field].strip() and values[field]!='None' else None
        except ValueError:QMessageBox.warning(self,'Allocation','Enter a whole number.');return
        values['required_fields']=[v.strip() for v in values['required_fields'].split(',') if v.strip()]
        values['duplicate_keys']=values['duplicate_keys'].split(',')
        config={**config,**values}
        self.run(lambda:self.client.call('campaign_save',campaign_id=cid,campaign_name=name,config=config,version=(campaign or {}).get('version',0)),lambda _:self.refresh_admin(),'Saving campaign…')

    def edit_policy(self):
        if self.busy:return
        old=self.selected_admin('Policies')
        kind,ok=QInputDialog.getItem(self,'Policy type','Type:',['permissions','routes','reasons','transitions'],0,False)
        if not ok:return
        old=old if old and old['kind']==kind else {}; directory=getattr(self,'directory',{})
        departments=[('Any department',None)]+[(d['name'],d['id']) for d in directory.get('departments',[])]
        campaigns=[('All campaigns',None)]+[(c['campaign_name'],c['campaign_id']) for c in self.controller.campaigns]
        roles=[('All roles',None)]+[(r,r) for r in ROLES]; states=[(s,s) for s in STATES]
        specs={
          'permissions':{'department_id':('Department',None,departments),'role':('Role',None,roles),'campaign_id':('Campaign',None,campaigns),
                         'field':('Field / category','*',[(x,x) for x in ['*','@Prospect','@Company','@Quality','@Delivery','@Approval',*STANDARD_HEADERS]]),
                         'access':('Permission','Read Only',[(x,x) for x in ['Hidden','Read Only','Edit','Approve','Export']])},
          'routes':{'campaign_id':('Campaign',None,campaigns),'from_department':('From department',None,departments[1:]),'to_department':('Destination',None,departments[1:]),
                    'required_state':('Required stage','Approved',states),'arrival_state':('Arrival stage','Transferred to Quality',states),'active':('Active',True,None)},
          'reasons':{'name':('Rejection reason','',None),'active':('Active',True,None)},
          'transitions':{'from_state':('Current stage','Draft',states),'to_state':('Next stage','Pending Validation',states),'role':('Permitted role','Employee',roles[1:]),
                         'department_id':('Department',None,departments),'active':('Active',True,None)}}
        fields={k:(label,bool(old[k]) if k=='active' and k in old else old.get(k,value),choices) for k,(label,value,choices) in specs[kind].items()}
        dialog=FormDialog(self,'Edit policy' if old else 'Create policy',fields)
        if dialog.exec():self.run(lambda:self.client.call('policy_save',kind=kind,values=dialog.values(),id=old.get('id')),lambda _:self.refresh_admin())

    def build_report_page(self):
        page=QWidget(); layout=QVBoxLayout(page); title=QLabel('Campaign & team operations'); title.setObjectName('pageTitle'); layout.addWidget(title)
        bar=QHBoxLayout(); refresh=QPushButton('Refresh'); refresh.clicked.connect(self.refresh_report); bar.addWidget(refresh)
        filters=QPushButton('Report filters'); filters.clicked.connect(self.report_filters); bar.addWidget(filters)
        export=QPushButton('Export report'); export.clicked.connect(self.export_report); bar.addWidget(export); bar.addStretch(1); layout.addLayout(bar)
        self.report_note=QLabel(); self.report_note.setWordWrap(True); layout.addWidget(self.report_note)
        self.report_tabs=QTabWidget(); self.report_tables={}
        for name in ('Workflow','Validation','Workload','Departments','Quality by date'):
            table=QTableWidget(); table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers); self.report_tables[name]=table; self.report_tabs.addTab(table,name)
        layout.addWidget(self.report_tabs,1); self.report_options={}; self.current_report=None
        return page

    def refresh_report(self):
        if self.busy:return
        def done(report):
            self.current_report=report; elapsed=report['mean_delivered_elapsed_hours']
            cid=options['campaign_id']; scope=next((c['campaign_name']+' · '+cid for c in self.controller.campaigns if c['campaign_id']==cid),'All campaigns')
            self.report_note.setText(scope+(' · Archived leads' if options.get('archived') else ' · Active leads')+f" · {report['total']:,} leads · {report['active_employees']} active employees · {report['submitted_today_utc']} submitted today (UTC) · {report['transfer_events']:,} transfer events · Average creation-to-delivery: {round(elapsed,1) if elapsed is not None else 'No delivered records'} hours. "+report['definitions'])
            self.fill_table(self.report_tables['Workflow'],[{'Stage':k,'Leads':v} for k,v in report['states'].items()])
            self.fill_table(self.report_tables['Validation'],[{'Validation':k,'Leads':v} for k,v in report['validation'].items()])
            self.fill_table(self.report_tables['Workload'],report['workload']); self.fill_table(self.report_tables['Departments'],report['departments'])
            self.fill_table(self.report_tables['Quality by date'],report['quality_by_created_date'])
        options=self.report_request_options()
        self.run(lambda:self.client.call('report',**options),done,'Loading permitted report totals…')

    def report_request_options(self):
        cid=self.campaign['campaign_id'] if self.campaign else None
        if self.client.user['role']=='Super User':cid=self.report_options.get('campaign_id')
        return {**self.report_options,'campaign_id':cid}

    def report_filters(self):
        def choose(directory):
            users=directory['users']; values=self.report_options
            fields={'employee_id':('Employee',values.get('employee_id'),[('All permitted',None)]+[(u['full_name'],u['id']) for u in users]),
              'department_id':('Department',values.get('department_id'),[('All permitted',None)]+[(d['name'],d['id']) for d in directory['departments']]),
              'team_lead_id':('Team Lead',values.get('team_lead_id'),[('All permitted',None)]+[(u['full_name'],u['id']) for u in users if u['role']=='Team Lead']),
              'state':('Stage',values.get('state'),[('All stages',None)]+[(s,s) for s in STATES]),'date_from':('Created from (YYYY-MM-DD)',values.get('date_from',''),None),
              'date_to':('Created through (YYYY-MM-DD)',values.get('date_to',''),None)}
            if self.client.user['role']=='Super User':
                fields={'campaign_id':('Campaign',values.get('campaign_id'),[('All campaigns',None)]+[(c['campaign_name']+' · '+c['campaign_id'],c['campaign_id']) for c in self.controller.campaigns]),
                        'archived':('Archived leads only',values.get('archived',False),None),**fields}
            dialog=FormDialog(self,'Report filters',fields)
            if dialog.exec():self.report_options=dialog.values(); self.refresh_report()
        self.run(lambda:self.client.call('directory'),choose)

    def export_report(self):
        if not self.current_report:return
        path,_=QFileDialog.getSaveFileName(self,'Export authorized report','','Excel (*.xlsx)')
        if path:
            from app.ui_qt.team_actions import write_report
            options=self.report_request_options()
            self.run(lambda:write_report(path,self.client.call('report_export',**options)),lambda _:self.status.setText('All authorized report tabs exported.'))

    def configure_reference(self,kind):
        if self.client.user['role']!='Super User' or not self.campaign:
            QMessageBox.information(self,'Campaign references','Only a Super User can update shared campaign reference lists.');return
        path,_=QFileDialog.getOpenFileName(self,'Load '+kind.upper(),'','Excel / CSV (*.xlsx *.xls *.csv *.tsv)')
        if not path:return
        from app.excel.importer import read_import_tables
        from app.core.reference_lists import available_fields
        from app.ui_qt.dialogs.lead_import_dialog import LeadImportDialog
        from app.ui_qt.team_actions import UserMappings
        def mapped(tables):
            dialog=LeadImportDialog(self,tables,available_fields(kind),reference_kind=kind,mapping_store=UserMappings(self.controller.settings_service))
            if dialog.exec():
                rows=[{target:str(row[source]) for source,target in dialog.mapping().items()} for _,row in dialog.selected_table().iterrows()]
                campaign=self.campaign; config={**campaign['config'],kind:rows}
                self.run(lambda:self.client.call('campaign_save',campaign_id=campaign['campaign_id'],campaign_name=campaign['campaign_name'],config=config,version=campaign['version']),lambda _:self.refresh_admin())
        self.run(lambda:read_import_tables(path),mapped,'Reading reference list…')

    def import_campaign_package(self):
        if self.busy:return
        from pathlib import Path
        import base64
        path,_=QFileDialog.getOpenFileName(self,'Import campaign package','','Campaign ZIP (*.zip)')
        if not path:return
        if Path(path).stat().st_size>10_000_000:QMessageBox.warning(self,'Campaign package','ZIP uploads are limited to 10 MB.');return
        self.run(lambda:self.client.call('campaign_package',filename=Path(path).name,content=base64.b64encode(Path(path).read_bytes()).decode()),lambda _:self.refresh_admin(),'Importing campaign package…')

    def legacy_snapshots(self):
        def show(rows):
            dialog=RowsDialog(self,'Historical worksheets · double-click to recover a private copy',rows)
            def recover(item):
                row=rows[item.row()]
                if QMessageBox.question(dialog,'Recover private worksheet','Create a private draft copy including saved formulas? The historical committed Lead IDs remain unchanged; committing copied leads will be blocked as duplicates.')!=QMessageBox.StandardButton.Yes:return
                dialog.accept()
                self.run(lambda:self.client.call('legacy_snapshots',source_key=row['source_key']),lambda r:self.status.setText('Recovered private sheet in campaign '+r['campaign_id']+'. Choose Working drafts in Lead Workspace to review it.'))
            dialog.table.itemDoubleClicked.connect(recover); dialog.exec()
        self.run(lambda:self.client.call('legacy_snapshots'),show)

    def review_campaign_rules(self):
        row=self.selected_admin('Campaigns') or self.campaign
        if not row:return
        cid=row['campaign_id']
        def show(rows):
            dialog=RowsDialog(self,'Campaign rules · double-click to review',rows)
            def edit(item):
                rule=rows[item.row()]
                status,ok=QInputDialog.getItem(dialog,'Review rule','Status:',['Confirmed','Needs Review','Rejected'],0,False)
                if ok:
                    dialog.accept(); self.run(lambda:self.client.call('campaign_rules',campaign_id=cid,index=rule['index'],status=status),show)
            dialog.table.itemDoubleClicked.connect(edit); dialog.exec()
        self.run(lambda:self.client.call('campaign_rules',campaign_id=cid),show)

    @authorized('leads')
    def configure_reference_database(self):
        from app.ui_qt.dialogs.database_connection_dialog import DatabaseConnectionDialog
        dialog=DatabaseConnectionDialog(self,self.controller.database_profiles)
        dialog.local_note.setText('Local uses permitted campaign leads. SQL Server / PostgreSQL uses your own database credentials; passwords remain in this session only.')
        if dialog.exec():self.status.setText('Lookup connection and header mapping saved for your account.')

    def add_reference_data(self):
        self.commit_draft()

    @authorized('leads')
    def populate_reference(self):
        if self.busy or not self.campaign:return
        from app.core.lead_reference import POPULATABLE_FIELDS,ReferenceInfo
        from app.core.database_connections import RemoteLeadSource
        from app.ui_qt.dialogs.populate_dialog import PopulateColumnsDialog
        from PySide6.QtWidgets import QLineEdit
        fields=[f for f in POPULATABLE_FIELDS if self.controller.field_permissions.get(f,'Edit')=='Edit']
        config=self.controller.database_profiles.load(); source=None
        if config.engine!='local':
            password=self.controller.database_profiles.password(config)
            if password is None and config.auth=='password':
                password,ok=QInputDialog.getText(self,'Database password','Password (session only):',QLineEdit.EchoMode.Password)
                if not ok:return
                self.controller.database_profiles.remember_session_password(config,password)
            source=RemoteLeadSource(config,password or '')
            fields=[f for f in fields if f in config.available_fields()]
        records=[dict(r) for r in self.controller.data_manager.records]
        scopes={'all':list(range(len(records))),'visible':self.leads.visible_rows(),'selected':self.leads.selected_rows()}
        info=ReferenceInfo('',None,label=config.source_label() if source else 'Permitted campaign leads',table=self.campaign['campaign_id'],available_fields=tuple(fields))
        dialog=PopulateColumnsDialog(self,info,scopes)
        if not dialog.exec():return
        columns=dialog.selected_columns(); selected=dialog.selected_rows(); overwrite=dialog.overwrite.isChecked()
        def lookup():
            if source:return source.plan(records,columns,selected,workspace_key=self.controller.workspace_key,overwrite=overwrite).edits
            result=self.client.call('populate',campaign_id=self.campaign['campaign_id'],records=[records[i] for i in selected],columns=columns,overwrite=overwrite)
            return {(selected[e['row']],e['field']):e['value'] for e in result['edits']}
        def done(edits):
            edits={cell:value for cell,value in edits.items() if self.controller.can_edit_cell(*cell)}
            self.controller.edit_cells(edits,'Populate selected fields',allow_formulas=False); self.leads.refresh(); self.status.setText(f'Populated {len(edits):,} cells. Review and save changes.')
        self.run(lookup,done,'Looking up selected fields…',cancellable=True)

    @authorized('leads')
    def find_emails(self):
        if self.busy:return
        from app.core.email_finder import EmailFinder
        settings=self.controller.settings
        records=[dict(r) for r in self.controller.data_manager.records]
        def find():
            from app.core.email_pattern_cache import EmailPatternCache
            from app.core.email_discovery_cache import EmailDiscoveryCache
            from run_support import EvidenceCache
            self.client.call('module_check',module='leads')
            path=self.controller.client_data_dir/'email-cache.sqlite3'
            finder=EmailFinder(cache=EmailPatternCache(database=path),discovery_cache=EmailDiscoveryCache(database=path),
                website_cache=EvidenceCache(self.controller.client_data_dir/'website-emails.sqlite3','official_pages_v1',ttl=86400))
            return finder.find_missing(records,blocked_statuses=dict(self.controller.row_states),
                minimum_confidence=settings.minimum_email_confidence,revalidate_existing=settings.revalidate_existing_emails,
                enable_web_search=settings.email_search_enabled,enable_website_lookup=settings.email_website_lookup,
                search_provider_name=settings.search_provider_name,max_workers=settings.email_search_max_workers,
                request_timeout_seconds=settings.email_search_timeout,retries=settings.email_search_retries,
                discovery_cache_days=settings.email_discovery_cache_days)
        def done(results):
            edits={}
            for result in results:
                for field,value in [('Business Email ID',result.candidate),('Email Status',result.status)]:
                    if result.applied and self.controller.can_edit_cell(result.row_index,field):edits[result.row_index,field]=value
            self.controller.edit_cells(edits,'Find email candidates',allow_formulas=False); self.leads.refresh()
            RowsDialog(self,'Email candidates · review before saving',[{'Row':r.row_index+1,'Candidate':r.candidate,'Status':r.status,'Confidence':r.confidence,'Reason':r.reason} for r in results]).exec()
        self.run(find,done,'Finding email candidates with your discovery settings…',cancellable=True)
