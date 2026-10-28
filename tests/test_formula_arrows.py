from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit

from app.ui_qt.controller import ApplicationController
from app.ui_qt.pages.leads_page import LeadsPage


def page_with_columns(qt):
    c = ApplicationController(); c.data_manager.add_columns(["column1", "column2", "Total"])
    c.data_manager.extend([{"First Name": "Ada", "column1": "12", "column2": "8"},
                           {"First Name": "Grace", "column1": "30", "column2": "2"}], "Test data")
    page = LeadsPage(c); page.resize(1250, 800)
    page.custom_views["Calculations"] = {"columns": ["First Name", "column1", "column2", "Total"], "freeze": True}
    page.view_selector.addItem("Calculations"); page.view_selector.setCurrentText("Calculations")
    page.show(); page.activateWindow(); qt.processEvents()
    page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(0, 44))); page.table.setFocus(); qt.processEvents()
    return c, page


def test_inline_arrows_build_sum_without_moving_output(qt):
    c, page = page_with_columns(qt)
    try:
        QTest.keyClicks(page.table, "="); qt.processEvents(); editor = QApplication.focusWidget()
        assert isinstance(editor, QLineEdit)
        QTest.keyClick(editor, Qt.Key.Key_Left); QTest.keyClick(editor, Qt.Key.Key_Left)
        assert editor.text() == "=AQ1"
        QTest.keyClicks(editor, "+"); QTest.keyClick(editor, Qt.Key.Key_Left)
        assert editor.text() == "=AQ1+AR1"
        assert page.proxy.mapToSource(page.table.currentIndex()).column() == 44
        assert page.table.reference_region == ((0, 43), (0, 43))
        QTest.keyClick(editor, Qt.Key.Key_Return); qt.processEvents()
        assert c.data_manager.records[0]["Total"] == "20"
        assert c.data_manager.records[0]["column1"] == "12"
        assert c.data_manager.records[0]["column2"] == "8"
        assert page.table.reference_region is None
    finally: page.close()


def test_formula_bar_shift_arrow_range_and_escape(qt):
    c, page = page_with_columns(qt)
    try:
        entry = page.formula_entry; entry.setFocus(); entry.setText("=SUM("); entry.setCursorPosition(len(entry.text()))
        QTest.keyClick(entry, Qt.Key.Key_Left)
        QTest.keyClick(entry, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
        assert entry.text() == "=SUM(AQ1:AR1"
        QTest.keyClicks(entry, ")"); QTest.keyClick(entry, Qt.Key.Key_Return)
        assert c.data_manager.records[0]["Total"] == "20"
        entry.setFocus(); entry.setText("="); QTest.keyClick(entry, Qt.Key.Key_Left)
        QTest.keyClick(entry, Qt.Key.Key_Escape)
        assert c.data_manager.records[0]["Total"] == "20"
        assert entry.text() == "=SUM(AQ1:AR1)" and page.table.reference_region is None
    finally: page.close()


def test_references_follow_original_rows_after_sort_and_filter(qt):
    c, page = page_with_columns(qt)
    try:
        page.proxy.set_column_filter(9, {"Grace"})
        page.table.sortByColumn(42, Qt.SortOrder.DescendingOrder)
        page.table.setCurrentIndex(page.proxy.index(0, 44))
        entry = page.formula_entry; entry.setFocus(); entry.setText("=")
        QTest.keyClick(entry, Qt.Key.Key_Left); QTest.keyClick(entry, Qt.Key.Key_Left)
        QTest.keyClicks(entry, "+"); QTest.keyClick(entry, Qt.Key.Key_Left)
        assert entry.text() == "=AQ2+AR2"
        QTest.keyClick(entry, Qt.Key.Key_Return)
        assert c.data_manager.records[1]["Total"] == "32"
        assert c.data_manager.records[0]["Total"] == "-"
    finally: page.close()


def test_f2_text_navigation_and_quotes_do_not_pick_cells(qt):
    c, page = page_with_columns(qt)
    try:
        entry = page.formula_entry; entry.setFocus(); entry.setText("=1+")
        QTest.keyClick(entry, Qt.Key.Key_F2); QTest.keyClick(entry, Qt.Key.Key_Left)
        assert entry.text() == "=1+" and entry.cursorPosition() == 2
        QTest.keyClick(entry, Qt.Key.Key_F2); entry.setText('="a+')
        QTest.keyClick(entry, Qt.Key.Key_Left)
        assert entry.text() == '="a+'
        entry.setText("="); QTest.keyClick(entry, Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier)
        assert entry.text() == "="
    finally: page.close()


def test_inline_escape_cancels_draft_and_restores_formula_bar(qt):
    c, page = page_with_columns(qt)
    try:
        c.edit_cells({(0, "Total"): "=1+2"}); page.refresh()
        page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(0, 44))); page.table.setFocus()
        QTest.keyClicks(page.table, "="); qt.processEvents(); editor = QApplication.focusWidget()
        QTest.keyClick(editor, Qt.Key.Key_Left); QTest.keyClick(editor, Qt.Key.Key_Escape); qt.processEvents()
        assert c.data_manager.records[0]["Total"] == "3"
        assert page.formula_entry.text() == "=1+2"
        assert page.table.reference_region is None
    finally: page.close()


def test_arrows_cross_frozen_pane_and_follow_sorted_rows(qt):
    c, page = page_with_columns(qt)
    try:
        page.view_selector.setCurrentText("All columns"); page.freeze_identity.setChecked(True)
        company = c.data_manager.headers.index("Company Name")
        assert page.resolve_formula_reference((0, 0), Qt.Key.Key_Left) == (0, company)
        assert page.resolve_formula_reference((0, company), Qt.Key.Key_Right) == (0, 0)
        page.table.sortByColumn(42, Qt.SortOrder.DescendingOrder)
        assert page.resolve_formula_reference((0, 44), Qt.Key.Key_Up) == (1, 44)
        entry = page.formula_entry; entry.setFocus(); entry.setText("=")
        QTest.keyClick(entry, Qt.Key.Key_F2)
        assert entry.text_navigation
        page.table.setCurrentIndex(page.proxy.mapFromSource(page.model.index(1, 44)))
        assert not entry.text_navigation
    finally: page.close()
