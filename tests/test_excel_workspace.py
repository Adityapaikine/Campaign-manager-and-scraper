import pytest
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QMessageBox
from app.team.service import Service
from app.ui_qt.team_window import TeamWindow
from app.ui_qt.dialogs.workspace_dialogs import ColumnViewDialog
from app.ui_qt.widgets.lead_table import column_letters
from tests.test_team_ui import DirectClient,wait_ready
from tests.test_team_service import PASSWORD,record


@pytest.fixture
def workbook(qt,tmp_path,monkeypatch):
    errors=[]; monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a[-1]))
    service=Service(tmp_path/'ribbon.sqlite3'); service.bootstrap('Admin','admin','admin@example.com',PASSWORD)
    client=DirectClient(service,service.login('admin',PASSWORD))
    client.call('campaign_save',campaign_id='C1',campaign_name='UI checks',config={'require_tal_match':False})
    window=TeamWindow(client); window.show(); wait_ready(qt,window)
    yield window,client,errors
    window._closing=True; window.close(); qt.processEvents()
    assert not errors


def test_excel_layout_keeps_columns_visible_and_gives_grid_space(qt,workbook):
    window,_,_=workbook; p=window.leads; ribbon=window.excel_workspace
    window.controller.edit_cells({(0,'First Name'):'Sample'}); p.refresh()
    window.resize(1366,768); qt.processEvents()
    assert p.table.viewport().height()>=340
    assert window.sheet_bar.isVisible() and window.sheet_bar.mapTo(window,QPoint()).y()>p.table.mapTo(window,QPoint(0,p.table.height())).y()
    for name in ('Home','Data','Formulas','Review','View','File'):
        ribbon.show_tab(name); qt.processEvents()
        assert p.view_selector.isVisible() and p.columns_button.isVisible() and p.formula_entry.isVisible()
    before=p.table.viewport().height(); ribbon.toggle_ribbon(); qt.processEvents()
    assert p.table.viewport().height()>=before+85
    assert p.view_selector.isVisible() and p.columns_button.isVisible()
    ribbon.toggle_ribbon(); qt.processEvents()
    ribbon.show_tab('Home'); window.resize(1120,720); qt.processEvents()
    assert window.width()==1120 and p.view_selector.isVisible()
    assert p.columns_button.mapTo(window,QPoint(p.columns_button.width(),0)).x()<window.width()


def test_custom_column_view_order_survives_switch_save_and_reload(qt,workbook,monkeypatch):
    window,client,_=workbook; p=window.leads; controller=window.controller
    controller.edit_cells({(0,k):v for k,v in record(601).items()}); p.refresh()
    def choose(dialog):
        dialog.name.setText('My calling view'); dialog.check_columns(False)
        for i in range(dialog.columns.count()):
            item=dialog.columns.item(i)
            if item.text() in ('First Name','Company Name','Business Email ID'):item.setCheckState(Qt.CheckState.Checked)
        dialog.freeze.setChecked(False); return 1
    monkeypatch.setattr(ColumnViewDialog,'exec',choose)
    p.columns_button.click(); qt.processEvents(); assert p.view_selector.currentText()=='My calling view'
    headers=controller.data_manager.headers; head=p.table.horizontalHeader(); email=headers.index('Business Email ID')
    head.moveSection(head.visualIndex(email),0)
    assert p._view_orders['My calling view'][0]=='Business Email ID'
    p.view_selector.setCurrentText('Research'); p.view_selector.setCurrentText('My calling view')
    assert head.logicalIndex(0)==email
    window.save(); wait_ready(qt,window); window.auto_save(); wait_ready(qt,window)
    prefs=client.call('preferences')
    assert prefs['lead_column_orders']['My calling view'][0]=='Business Email ID'
    assert set(prefs['lead_column_views']['My calling view']['columns'])=={'First Name','Company Name','Business Email ID'}
    window.load_sheet(controller.sheet['id']); wait_ready(qt,window)
    assert head.logicalIndex(0)==email
    assert controller.data_manager.records[0]['First Name']=='Person601'
    reopened=TeamWindow(client); reopened.show()
    try:
        wait_ready(qt,reopened)
        assert reopened.leads.view_selector.currentText()=='My calling view'
        assert reopened.leads.table.horizontalHeader().logicalIndex(0)==email
    finally:reopened._closing=True; reopened.close(); qt.processEvents()


def test_formula_arrows_follow_moved_columns_and_letters_select_columns(qt,workbook):
    window,_,_=workbook; p=window.leads; controller=window.controller
    controller.change_columns(['column1','column2','Total']); controller.edit_cells({(0,'column1'):'12',(0,'column2'):'8'})
    p.custom_views['Calculations']={'columns':['column1','column2','Total'],'freeze':False}
    p.view_selector.addItem('Calculations'); p.view_selector.setCurrentText('Calculations'); p.refresh()
    headers=controller.data_manager.headers; x,y,total=[headers.index(f) for f in ('column1','column2','Total')]
    head=p.table.horizontalHeader(); head.moveSection(head.visualIndex(y),0)
    p.table.setCurrentIndex(p.proxy.mapFromSource(p.model.index(0,total)))
    entry=p.formula_entry; entry.setFocus(); entry.setText('='); QTest.keyClick(entry,Qt.Key.Key_Left)
    assert entry.text()=='='+column_letters(x)+'1'
    QTest.keyClicks(entry,'+'); QTest.keyClick(entry,Qt.Key.Key_Left); QTest.keyClick(entry,Qt.Key.Key_Left)
    QTest.keyClick(entry,Qt.Key.Key_Return); qt.processEvents()
    assert controller.data_manager.records[0]['Total']=='20'
    p.formula_address.setText(column_letters(y)+'1'); p.formula_address.returnPressed.emit(); qt.processEvents()
    assert p.table.currentIndex().column()==y
    QTest.mouseClick(head.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(head.sectionViewportPosition(x)+20,9))
    assert {index.column() for index in p.table.selectedIndexes()}=={x}


def test_column_picker_search_and_reorder_preserve_hidden_selections(qt):
    dialog=ColumnViewDialog(None,['First Name','Company Name','Email'],['First Name','Email'])
    dialog.search.setText('Company'); qt.processEvents()
    assert dialog.selected_columns()==['First Name','Email']
    dialog.search.clear(); item=dialog.columns.takeItem(2); dialog.columns.insertItem(0,item)
    assert dialog.selected_columns()==['Email','First Name']
    dialog.check_columns(True); assert len(dialog.selected_columns())==3
    dialog.close()
