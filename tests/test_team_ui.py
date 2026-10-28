import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from app.team.service import Service
from app.ui_qt.team_window import TeamWindow


class DirectClient:
    def __init__(self, service, login):
        self.service=service; self.token=login['token']; self.user=login['user']
    def call(self, operation, **args): return self.service.call(self.token,operation,args)
    def logout(self):
        self.call('logout'); self.token=None


def wait_ready(qt, window):
    until=time.monotonic()+20
    while (window.busy or window._module_tasks) and time.monotonic()<until:
        qt.processEvents(); QTest.qWait(20)
    assert not window.busy and not window._module_tasks


def test_shared_window_sheet_formula_selection_and_save(qt,tmp_path,monkeypatch):
    errors=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *args:errors.append(args[-1]))
    service=Service(tmp_path/'team.sqlite3'); password='Testing-long-password-82'
    service.bootstrap('Test Admin','admin','admin@example.com',password)
    client=DirectClient(service,service.login('admin',password))
    client.call('campaign_save',campaign_id='C1',campaign_name='Campaign test',config={'require_tal_match':False})
    sheet=client.call('sheet_create',campaign_id='C1',name='Sheet1')
    window=TeamWindow(client); window.show()
    try:
        wait_ready(qt,window); assert not errors
        window.nav.setCurrentRow(window.items.index('Lead Workspace')); wait_ready(qt,window); assert not errors
        controller=window.controller
        assert controller.sheet['id']==sheet['id']
        controller.change_columns(['column1','column2','Total'])
        controller.edit_cells({(0,'column1'):'2',(0,'column2'):'3',(0,'Total'):'=column1+column2'})
        assert controller.data_manager.records[0]['Total']=='5'
        window.leads.refresh(); window.save(); wait_ready(qt,window)
        assert not errors
        controller.change_columns(['Temporary'])
        window.save(); wait_ready(qt,window)
        assert not controller.dirty
        assert controller.undo_edit() and controller.dirty and 'Temporary' not in controller.data_manager.headers
        window.save(); wait_ready(qt,window)
        column=controller.data_manager.headers.index('column1')
        window.leads.proxy.set_condition(column,{'operator':'gt','value':'1','type':'number'})
        window.remember_view(); window.leads.clear_filters(); window.restore_view()
        assert window.leads.proxy.column_conditions[column]['value']=='1'
        window.leads.clear_filters(); window.remember_view()
        window.load_sheet(sheet['id']); wait_ready(qt,window)
        assert controller.data_manager.raw_value(0,'Total')=='=column1+column2'
        table=window.leads.table
        visible=next(i for i in range(table.model().columnCount()) if not table.isColumnHidden(i))
        table.setCurrentIndex(table.model().index(0,visible)); table.setFocus()
        QTest.keyClick(table,Qt.Key.Key_Space,Qt.KeyboardModifier.ShiftModifier)
        assert len({i.column() for i in table.selectionModel().selectedIndexes()})>1
        QTest.keyClick(table,Qt.Key.Key_Space,Qt.KeyboardModifier.ControlModifier)
        assert len({i.row() for i in table.selectionModel().selectedIndexes()})>1
        window.grab().save(str(tmp_path/'team-workspace.png'))
    finally:
        window._closing=True; window.close(); qt.processEvents()
        assert not window.autosave.isActive() and not window.poll.isActive()


def test_shared_commit_from_ui_and_authorized_clipboard(qt,tmp_path,monkeypatch):
    from tests.test_team_service import record
    from PySide6.QtWidgets import QApplication
    from app.ui_qt.dialogs.team_dialogs import RowsDialog
    errors=[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a[-1]))
    monkeypatch.setattr(QMessageBox,'information',lambda *a:errors.append(a[-1]))
    monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(RowsDialog,'exec',lambda self:0)
    service=Service(tmp_path/'ui-commit.sqlite3'); password='Testing-long-password-82'
    service.bootstrap('Test Admin','admin','admin@example.com',password)
    client=DirectClient(service,service.login('admin',password))
    client.call('campaign_save',campaign_id='C1',campaign_name='Campaign test',config={'require_tal_match':False})
    client.call('sheet_create',campaign_id='C1',name='Draft')
    window=TeamWindow(client); window.show()
    try:
        wait_ready(qt,window); window.nav.setCurrentRow(window.items.index('Lead Workspace')); wait_ready(qt,window)
        window.controller.edit_cells({(i,k):v for i in range(2) for k,v in record(321+i).items()})
        window.leads.refresh(); window.commit_draft(); wait_ready(qt,window)
        assert not errors and not window.controller.data_manager.records
        window.set_workspace_mode('mine'); wait_ready(qt,window)
        assert len(window.controller.lead_rows)==2
        p=window.leads; p.view_selector.setCurrentText('All columns')
        column=window.controller.data_manager.headers.index('First Name')
        from PySide6.QtCore import QItemSelection,QItemSelectionModel
        selection=QItemSelection(p.proxy.index(0,column),p.proxy.index(1,column))
        p.table.selectionModel().select(selection,QItemSelectionModel.SelectionFlag.ClearAndSelect)
        selected_ids={r['id'] for r in window.selection()}
        window.controller.edit_cells({(0,'Job Title'):'Director'})
        window.save(); wait_ready(qt,window)
        assert {r['id'] for r in window.selection()}==selected_ids and len(selected_ids)==2
        table=p.frozen_table if p.table.isColumnHidden(column) else p.table
        table.clearSelection(); table.setCurrentIndex(p.proxy.index(0,column)); qt.processEvents()
        selected_indexes=table.selectedIndexes(); assert len(selected_indexes)==1
        expected=selected_indexes[0].data()
        table.copy_selection(); wait_ready(qt,window)
        assert QApplication.clipboard().text()==expected
        assert not errors
    finally:window._closing=True; window.close(); qt.processEvents()


def test_http_authentication_and_malformed_requests(tmp_path):
    from fastapi.testclient import TestClient
    from app.team.api import create_app
    app=create_app(tmp_path/'api.sqlite3')
    app.state.service.bootstrap('Admin','admin','admin@example.com','Long-test-password-42')
    with TestClient(app) as client:
        assert client.get('/health').json()['status']=='ok'
        assert client.post('/rpc/me',json={}).status_code==401
        assert client.post('/login',content='{').status_code==400
        response=client.post('/login',json={'username':'admin','password':'Long-test-password-42'})
        assert response.status_code==200
        headers={'Authorization':'Bearer '+response.json()['token']}
        assert client.post('/rpc/me',json={},headers=headers).json()['username']=='admin'
        assert client.post('/rpc/campaign_save',json={'unknown':'value'},headers=headers).status_code==400
        assert client.post('/rpc/_private',json={},headers=headers).status_code==404
        assert client.post('/rpc/logout',json={},headers=headers).status_code==200
        assert client.post('/rpc/me',json={},headers=headers).status_code==401
