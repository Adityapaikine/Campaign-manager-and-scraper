import json
import pytest
from PySide6.QtCore import QItemSelection,QItemSelectionModel
from PySide6.QtWidgets import QMessageBox,QInputDialog,QDialog
from app.team.access import ServiceError
from app.team.schema import transaction
from app.team.demo import create_demo,CAMPAIGN_ID
from app.team.service import Service
from app.ui_qt.team_window import TeamWindow
from app.ui_qt.dialogs.handoff_dialog import HandoffDialog
from tests.test_team_ui import DirectClient,wait_ready
from tests.test_team_service import team,call,commit,selected,PASSWORD


def approve(team,lid):
    call(team,'a','transition',selection=selected(team,'a',lid),state='Pending Team Lead Review')
    call(team,'lead','transition',selection=selected(team,'lead',lid),state='Approved')


def test_bulk_preview_and_transfer_only_selected_rows(team):
    ids=[commit(team,'a',i)['committed'][0]['id'] for i in (201,202,203)]
    for lid in ids[:2]:approve(team,lid)
    selection=selected(team,'lead',ids[0])+selected(team,'lead',ids[2])
    preview=call(team,'lead','selection_actions',selection=selection)
    route=next(r for r in preview['routes'] if r['id']=='1')
    assert route['ready']==1 and 'Approved' in route['rows'][1]['reason']
    assert preview['transitions']==[]
    with pytest.raises(ServiceError,match='Nothing was transferred'):
        call(team,'lead','transfer',selection=selection,route_id='1')
    assert all(call(team,'lead','lead',lead_id=lid)['department_id']=='operations' for lid in ids)
    call(team,'lead','transfer',selection=selected(team,'lead',ids[0]),route_id='1')
    assert call(team,'qualitylead','leads',campaign_id='C1',view='incoming')['total']==1
    assert call(team,'lead','lead',lead_id=ids[1])['department_id']=='operations'
    with pytest.raises(ServiceError):call(team,'a','transfer',selection=selected(team,'a',ids[1]),route_id='1')
    assert call(team,'a','selection_actions',selection=selected(team,'a',ids[1]))['routes']==[]


def test_handoff_checks_policy_changes_and_stale_selection(team):
    lid=commit(team,'a',210)['committed'][0]['id']; approve(team,lid)
    selection=selected(team,'lead',lid)
    assert call(team,'lead','selection_actions',selection=selection)['routes'][0]['ready']==1
    call(team,'admin','campaign_save',campaign_id='C1',campaign_name='Campaign 1',version=1,
         config={'require_tal_match':False,'required_fields':['Address']})
    assert call(team,'lead','selection_actions',selection=selection)['routes'][0]['ready']==0
    with pytest.raises(ServiceError,match='validation'):call(team,'lead','transfer',selection=selection,route_id='1')
    assert call(team,'lead','lead',lead_id=lid)['department_id']=='operations'
    with pytest.raises(ServiceError):call(team,'lead','selection_actions',selection=[{'id':lid,'version':999}])
    with pytest.raises(ServiceError):call(team,'lead','selection_actions',selection=[{}])


@pytest.fixture
def demo(tmp_path):
    service=Service(tmp_path/'demo.sqlite3'); service.bootstrap('Existing Admin','existing','existing@example.com',PASSWORD)
    admin=service.login('existing',PASSWORD)['token']
    service.call(admin,'campaign_save',{'campaign_id':'REAL','campaign_name':'Existing campaign','config':{'require_tal_match':False}})
    before=service.call(admin,'campaigns')
    result=create_demo(service)
    clients={a['username']:DirectClient(service,service.login(a['username'],a['password'])) for a in result['accounts']}
    return service,admin,result,clients,before


def test_demo_isolated_preserves_existing_accounts_and_repeat_is_safe(demo):
    service,admin,result,clients,before=demo
    assert len(result['lead_ids'])==10
    assert service.call(admin,'campaigns')[1:]==before  # DEMO name sorts first.
    service.login('existing',PASSWORD)
    for client in clients.values():
        assert [c['campaign_id'] for c in client.call('campaigns')]==[CAMPAIGN_ID]
        with pytest.raises(ServiceError):client.call('leads',campaign_id='REAL')
        with pytest.raises(ServiceError):client.call('policy')
    with pytest.raises(ServiceError,match='already exists'):create_demo(service)
    with transaction(service.path,False) as db:
        assert db.execute('SELECT count(*) FROM team_users').fetchone()[0]==7
        assert db.execute('SELECT count(*) FROM team_leads').fetchone()[0]==10
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    quality=clients['demo.quality.lead']; delivery=clients['demo.delivery.lead']
    assert not quality.call('modules')['scraper']['allowed']
    assert not delivery.call('modules')['scraper']['allowed']
    assert delivery.call('leads',campaign_id=CAMPAIGN_ID,view='incoming')['total']==2
    assert clients['demo.ops.lead'].call('leads',campaign_id=CAMPAIGN_ID,view='department')['total']==5
    with pytest.raises(ServiceError):clients['demo.ops.employee'].call('leads',campaign_id=CAMPAIGN_ID,view='department')
    assert clients['demo.delivery.employee'].call('leads',campaign_id=CAMPAIGN_ID)['total']==1


def test_demo_complete_handoff_with_employee_assignment(demo):
    _,_,_,clients,_=demo
    ops=clients['demo.ops.lead']; qa=clients['demo.quality.lead']; delivery=clients['demo.delivery.lead']
    employee=clients['demo.quality.employee']
    lead=next(r for r in ops.call('leads',campaign_id=CAMPAIGN_ID)['rows'] if r['state']=='Approved')
    lid=lead['id']; owner=lead['owner_id']
    def selection(client):
        r=client.call('lead',lead_id=lid); return [{'id':lid,'version':r['version']}]
    ops.call('transfer',selection=selection(ops),route_id='1')
    with pytest.raises(ServiceError):employee.call('lead',lead_id=lid)
    qa.call('assign',selection=selection(qa),user_ids=[employee.user['id']])
    employee.call('transition',selection=selection(employee),state='Quality In Progress')
    employee.call('transition',selection=selection(employee),state='Quality Qualified')
    assert qa.call('selection_actions',selection=selection(qa))['routes'][0]['ready']==1
    qa.call('transfer',selection=selection(qa),route_id='2')
    received=delivery.call('lead',lead_id=lid)
    assert received['owner_id']==owner and received['assigned_id'] is None
    assert received['state']=='Transferred to Delivery'
    assert len(delivery.call('transfer_history',lead_id=lid))==2
    assert delivery.call('leads',campaign_id=CAMPAIGN_ID,view='incoming')['total']==3


def test_visible_push_preview_and_incoming_controls(qt,demo,monkeypatch,tmp_path):
    _,_,_,clients,_=demo; errors=[]; notices=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a[-1]))
    monkeypatch.setattr(QMessageBox,'information',lambda *a:notices.append(a[-1]))
    ops=clients['demo.ops.lead']; window=TeamWindow(ops); window.show()
    try:
        wait_ready(qt,window)
        window.excel_workspace.actions['Review and send'].click(); qt.processEvents()
        assert window.scope.currentData()=='department' and window.push_button.isVisible()
        assert window.push_button.text()=='Push to Quality' and not window.push_button.isEnabled()
        assert window.leads.view_selector.currentText()=='Workflow'
        ready=next(i for i,r in enumerate(window.controller.lead_rows) if r['state']=='Approved')
        column=window.controller.data_manager.headers.index('First Name')
        index=window.leads.proxy.mapFromSource(window.leads.model.index(ready,column))
        window.leads.table.selectionModel().select(index,QItemSelectionModel.SelectionFlag.ClearAndSelect)
        assert window.push_button.isEnabled() and '1 selected' in window.handoff_hint.text()
        chosen=window.selection(); previews=[]
        def confirm(dialog):
            previews.append(dialog.preview)
            assert dialog.send_button.isEnabled() and dialog.send_button.text()=='Push to Quality'
            dialog.note.setText('UI handoff test'); return QDialog.DialogCode.Accepted
        monkeypatch.setattr(HandoffDialog,'exec',confirm)
        window.push_button.click(); wait_ready(qt,window)
        assert not errors and previews and notices[-1].startswith('1 selected lead(s) sent to Quality')
        assert clients['demo.quality.lead'].call('lead',lead_id=chosen[0]['id'])['department_id']=='quality'
        window.resize(1366,768); qt.processEvents()
        assert window.width()==1366 and window.push_button.mapTo(window,window.push_button.rect().topRight()).x()<window.width()
        window.grab().save(str(tmp_path/'handoff-operations.png'))
    finally:window._closing=True; window.close(); qt.processEvents()
    quality_window=TeamWindow(clients['demo.quality.lead']); quality_window.show()
    try:
        wait_ready(qt,quality_window)
        quality_window.excel_workspace.show_tab('Review'); qt.processEvents()
        assert quality_window.push_button.text()=='Push to Delivery'
        quality_window.incoming_button.click(); wait_ready(qt,quality_window)
        assert quality_window.scope.currentData()=='incoming' and quality_window.total==1
        assert not errors
    finally:quality_window._closing=True; quality_window.close(); qt.processEvents()


def test_blocked_preview_disables_send(qt,team):
    lid=commit(team,'a',250)['committed'][0]['id']
    preview=call(team,'lead','selection_actions',selection=selected(team,'lead',lid))
    dialog=HandoffDialog(None,preview)
    assert not dialog.send_button.isEnabled() and '0 of 1' in dialog.summary.text()
    assert 'Approved' in dialog.table.item(0,2).text()
    dialog.accept(); assert dialog.result()!=QDialog.DialogCode.Accepted
    dialog.close()
