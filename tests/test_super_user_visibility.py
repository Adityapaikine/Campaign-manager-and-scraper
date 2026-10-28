"""Super User oversight must not broaden another role's access or mutate drafts."""
import uuid

import pytest
from PySide6.QtWidgets import QMessageBox,QInputDialog

from app.team.access import ServiceError
from app.team.schema import transaction
from app.ui_qt.team_window import TeamWindow
from tests.test_team_service import team,call,commit,record,PASSWORD
from tests.test_team_ui import DirectClient,wait_ready


def make_sheet(team,owner='a',archived=False):
    sheet=call(team,owner,'sheet_create',campaign_id='C1',name='Research')
    payload={'records':[{**record(701),'Amount':'4','Total':'8'}],
             'headers':['First Name','Business Email ID','Amount','Total'],
             'custom_columns':['Amount','Total'],
             'formulas':[{'row':0,'column':'Total','expression':'=Amount*2'}]}
    call(team,owner,'sheet_save',sheet_id=sheet['id'],version=1,payload=payload)
    if archived:call(team,owner,'sheet_delete',sheet_id=sheet['id'],version=2)
    return sheet['id']


@pytest.mark.parametrize('archived',[False,True])
def test_super_user_can_inspect_export_and_duplicate_other_worksheets(team,archived):
    sid=make_sheet(team,archived=archived)
    if archived:
        owner=team[2]['a']
        call(team,'admin','user_save',**{k:owner[k] for k in ('id','full_name','username','email','role','department_id','manager_id','team_lead_id')},active=False)
    # A field hidden for the owner remains visible to the Super User.
    call(team,'admin','policy_save',kind='permissions',values={'department_id':'operations','role':'Employee',
         'campaign_id':'C1','field':'Business Email ID','access':'Hidden'})
    rows=call(team,'admin','sheets',campaign_id='C1',include_all=True)
    assert len(rows)==1 and rows[0]['id']==sid and rows[0]['owner_name']=='a'
    assert rows[0]['read_only'] and rows[0]['archived']==archived
    assert call(team,'admin','sheets',campaign_id='C1')==[]
    loaded=call(team,'admin','sheet_load',sheet_id=sid)
    assert loaded['payload']['records'][0]['Business Email ID']=='person701@acme.example'
    assert loaded['payload']['formulas'][0]['expression']=='=Amount*2'
    assert call(team,'admin','export_draft',campaign_id='C1',sheet_id=sid,row_ids=loaded['payload']['row_ids'])[0]['Total']=='8'
    for owner in ('b','lead','manager'):
        with pytest.raises(ServiceError):call(team,owner,'sheets',campaign_id='C1',include_all=True)
        with pytest.raises(ServiceError):call(team,owner,'sheet_load',sheet_id=sid)
    if archived:
        with pytest.raises(ServiceError):call(team,'a','sheet_load',sheet_id=sid)
    # Every mutation route must enforce ownership even if called outside the UI.
    for op,args in [('sheet_save',{'payload':loaded['payload']}),('sheet_rename',{'name':'Changed'}),('sheet_delete',{})]:
        with pytest.raises(ServiceError,match='read-only'):
            call(team,'admin',op,sheet_id=sid,version=loaded['version'],**args)
    with pytest.raises(ServiceError,match='read-only'):
        call(team,'admin','commit',campaign_id='C1',sheet_id=sid,records=loaded['payload']['records'],request_key=str(uuid.uuid4()))
    copy=call(team,'admin','sheet_create',campaign_id='C1',name='My copy',duplicate_id=sid)
    copied=call(team,'admin','sheet_load',sheet_id=copy['id'])
    assert not copied['read_only'] and not copied['archived']
    assert copied['payload']==loaded['payload']
    assert call(team,'admin','sheet_load',sheet_id=sid)['payload']==loaded['payload']
    with transaction(team[0].path,False) as db:
        assert db.execute('SELECT count(*) FROM team_audit WHERE event=? AND resource=?',('sheet-inspect',sid)).fetchone()[0]>=1
        assert db.execute('SELECT owner_id FROM team_sheets WHERE id=?',(sid,)).fetchone()[0]==team[2]['a']['id']


def test_super_user_sees_leads_and_fields_across_campaigns_and_departments(team):
    first=commit(team,'a',710)['committed'][0]['id']
    second=commit(team,'quality',711)['committed'][0]['id']
    call(team,'admin','commit',campaign_id='C2',records=[record(712)],request_key=str(uuid.uuid4()))
    call(team,'admin','policy_save',kind='permissions',values={'department_id':None,'role':None,'campaign_id':None,'field':'Business Email ID','access':'Hidden'})
    result=call(team,'admin','leads')
    assert result['total']==3
    assert all('Business Email ID' in r['record'] for r in result['rows'])
    assert call(team,'admin','report')['total']==3
    assert {r['campaign_id'] for r in call(team,'admin','dashboard')}=={'C1','C2'}
    assert all(m['allowed'] for m in call(team,'admin','modules').values())
    assert call(team,'a','leads',campaign_id='C1')['total']==1
    with pytest.raises(ServiceError):call(team,'a','lead',lead_id=second)
    with pytest.raises(ServiceError):call(team,'a','leads',campaign_id='C2')
    assert 'Business Email ID' not in call(team,'a','lead',lead_id=first)['record']


def test_super_user_ui_inspection_scope_and_campaign_totals(qt,team,monkeypatch):
    errors=[]; monkeypatch.setattr(QMessageBox,'warning',lambda *args:errors.append(args[-1]))
    sid=make_sheet(team,archived=True)
    commit(team,'a',720)
    call(team,'admin','commit',campaign_id='C2',records=[record(721)],request_key=str(uuid.uuid4()))
    client=DirectClient(team[0],team[0].login('admin',PASSWORD))
    window=TeamWindow(client); window.show()
    try:
        wait_ready(qt,window); window.select_campaign_id('C1'); wait_ready(qt,window)
        own_id=window.controller.sheet['id']
        window.set_workspace_mode('all_sheets'); wait_ready(qt,window)
        window.load_sheet(sid); wait_ready(qt,window)
        assert window.scope.currentData()=='all_sheets'
        assert window.controller.read_only_sheet and window.sheet_bar.isVisible()
        assert 'Read-only inspection' in window.handoff_hint.text()
        assert any('a · Archived' in window.tabs.tabText(i) for i in range(window.tabs.count()))
        assert not window.commit_button.isEnabled() and not window.workspace_buttons['Save'].isEnabled()
        assert not window.leads.import_button.isEnabled() and not window.leads.add_columns_button.isEnabled()
        assert not window.sheet_actions['Rename sheet'].isEnabled()
        assert window.sheet_actions['Duplicate sheet'].isEnabled()
        assert not window.controller.can_edit_cell(0,'First Name')
        with pytest.raises(ValueError,match='read-only'):window.controller.change_columns(['Test'])
        assert not window.controller.recalculate_formulas() and not window.controller.dirty
        window.save(); window.auto_save(); wait_ready(qt,window)
        assert call(team,'admin','sheet_load',sheet_id=sid)['version']==3
        window.set_workspace_mode('draft'); wait_ready(qt,window)
        assert window.controller.sheet['id']==own_id and window.controller.can_edit_cell(0,'First Name')
        assert all(s['owner_id']==client.user['id'] for s in window.sheet_rows)
        window.set_workspace_mode('all_sheets'); wait_ready(qt,window)
        assert window.controller.sheet['id']==sid
        monkeypatch.setattr(QInputDialog,'getText',lambda *a,**kw:('My review copy',True))
        window.duplicate_sheet(); wait_ready(qt,window)
        assert window.scope.currentData()=='draft' and not window.controller.read_only_sheet
        assert window.controller.sheet['owner_id']==client.user['id']
        window.navigate('dashboard'); wait_ready(qt,window)
        assert window.campaign_table.rowCount()==2
        window.dashboard_scope.setCurrentIndex(window.dashboard_scope.findData('selected')); wait_ready(qt,window)
        assert window.campaign_table.rowCount()==1
        window.navigate('reports'); wait_ready(qt,window)
        assert window.current_report['total']==2 and window.report_request_options()['campaign_id'] is None
        window.report_options={'campaign_id':'C1'}; window.refresh_report(); wait_ready(qt,window)
        assert window.current_report['total']==1 and window.report_request_options()['campaign_id']=='C1'
        assert not errors
    finally:
        window._closing=True; window.close(); qt.processEvents()


def test_activity_paging_exposes_older_events(qt,team,monkeypatch):
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:pytest.fail(str(args[-1])))
    client=DirectClient(team[0],team[0].login('admin',PASSWORD))
    with transaction(team[0].path) as db:
        db.executemany('INSERT INTO team_audit(user_id,event,resource,outcome) VALUES(?,?,?,?)',
                       [(client.user['id'],'inspection-test',str(i),'success') for i in range(210)])
    window=TeamWindow(client)
    try:
        wait_ready(qt,window); window.navigate('tools'); wait_ready(qt,window)
        first=window.audit_table.item(0,0).text()
        assert window.audit_table.rowCount()==200 and window.audit_next.isEnabled()
        assert not window.audit_previous.isEnabled()
        window.audit_next.click(); wait_ready(qt,window)
        assert window.audit_offset==200 and window.audit_table.rowCount()>0
        assert window.audit_table.item(0,0).text()!=first and window.audit_previous.isEnabled()
        window.refresh_tools(reset=True); wait_ready(qt,window)
        assert window.audit_offset==0 and window.audit_table.item(0,0).text()==first
    finally:
        window._closing=True; window.close(); qt.processEvents()


def test_employee_ui_does_not_offer_super_user_scopes(qt,team,monkeypatch):
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:pytest.fail(str(args[-1])))
    client=DirectClient(team[0],team[0].login('a',PASSWORD))
    window=TeamWindow(client)
    try:
        wait_ready(qt,window)
        assert window.scope.findData('all_sheets')==-1 and window.scope.findData('archived')==-1
        assert window.dashboard_scope.findData('all')==-1
        assert window.report_request_options()['campaign_id']=='C1'
    finally:
        window._closing=True; window.close(); qt.processEvents()
