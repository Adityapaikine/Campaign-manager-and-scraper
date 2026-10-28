from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from app.ui_qt.controller import ApplicationController
from app.ui_qt.pages.leads_page import LeadsPage


def test_row_column_shortcuts_respect_filters_hidden_columns_and_text_editors(qt):
    controller=ApplicationController()
    controller.data_manager.replace_all([{'First Name':'One','Country':'India'},{'First Name':'Hidden','Country':'USA'},{'First Name':'Three','Country':'India'}])
    page=LeadsPage(controller); page.show(); page.view_selector.setCurrentText('Research'); qt.processEvents()
    first=controller.data_manager.headers.index('First Name'); country=controller.data_manager.headers.index('Country')
    page.proxy.set_column_filter(country,{'india'})
    table=page.frozen_table if not page.frozen_table.isColumnHidden(first) else page.table
    table.setCurrentIndex(page.proxy.index(0,first)); table.setFocus()
    QTest.keyClick(table,Qt.Key.Key_Space,Qt.KeyboardModifier.ShiftModifier)
    assert {page.proxy.mapToSource(i).row() for i in table.selectedIndexes()}=={0}
    assert all(not page.table.isColumnHidden(i.column()) or not page.frozen_table.isColumnHidden(i.column()) for i in table.selectedIndexes())
    table.clearSelection(); table.setCurrentIndex(page.proxy.index(0,first))
    QTest.keyClick(table,Qt.Key.Key_Space,Qt.KeyboardModifier.ControlModifier)
    assert {page.proxy.mapToSource(i).row() for i in table.selectedIndexes()}=={0,2}
    table.copy_selection(); assert QApplication.clipboard().text().splitlines()==['One','Three']
    before={(i.row(),i.column()) for i in table.selectedIndexes()}
    page.search.setFocus(); QTest.keyClick(page.search,Qt.Key.Key_Space,Qt.KeyboardModifier.ShiftModifier)
    assert {(i.row(),i.column()) for i in table.selectedIndexes()}==before
    page.close()
