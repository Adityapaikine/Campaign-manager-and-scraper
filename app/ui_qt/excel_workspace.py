"""Excel-style composition of the existing worksheet controls and actions.

This module arranges widgets only. Editing, imports, formulas and authorized
workflow operations continue to use their existing handlers.
"""
import re
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QShortcut,QKeySequence
from PySide6.QtWidgets import (QWidget,QFrame,QHBoxLayout,QVBoxLayout,QLabel,QPushButton,
    QToolButton,QTabBar,QStackedWidget,QScrollArea,QSizePolicy,QLineEdit,QMenu,QMessageBox)
from app.ui_qt.widgets.icons import icon


class ExcelWorkspace:
    def __init__(self,window):
        self.window=window; self.page=p=window.leads; self.pages={}; self.actions={}
        p.excel_layout=True; p._details_preference=False
        window.workspace.layout().setContentsMargins(0,0,0,0); window.workspace.layout().setSpacing(0)
        p.layout().setContentsMargins(0,0,0,0); p.layout().setSpacing(0)
        for old in (p.header_widget,p.toolbar_card,p.table_top,window.operations_bar,window.page_bar):old.hide()
        self.ribbon=QFrame(); self.ribbon.setObjectName('excelRibbon')
        root=QVBoxLayout(self.ribbon); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        strip=QWidget(); strip.setObjectName('ribbonStrip'); strip.setFixedHeight(32); top=QHBoxLayout(strip); top.setContentsMargins(5,0,5,0); top.setSpacing(4)
        self.tabs=QTabBar(); self.tabs.setObjectName('ribbonTabs'); self.tabs.setExpanding(False); self.tabs.setDrawBase(False)
        top.addWidget(self.tabs); top.addStretch(1)
        save=window.workspace_buttons['Save']; save.setToolTip('Save this worksheet · Ctrl+S'); top.addWidget(save); save.show()
        for button in (p.undo_button,p.redo_button):top.addWidget(button); button.show()
        self.collapse=QToolButton(); self.collapse.setIcon(icon('chevron-up','#217346')); self.collapse.setAccessibleName('Collapse ribbon'); self.collapse.setToolTip('Collapse ribbon · Ctrl+F1')
        self.collapse.clicked.connect(self.toggle_ribbon); top.addWidget(self.collapse); root.addWidget(strip)
        self.stack=QStackedWidget(); self.stack.setFixedHeight(96); root.addWidget(self.stack)
        for name in ('File','Home','Data','Formulas','Review','View'):
            self.tabs.addTab(name)
            scroll=QScrollArea(); scroll.setObjectName('ribbonScroll'); scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True); scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            body=QWidget(); body.setObjectName('ribbonPage'); layout=QHBoxLayout(body); layout.setContentsMargins(6,3,6,3); layout.setSpacing(8)
            scroll.setWidget(body); self.stack.addWidget(scroll); self.pages[name]=layout
        self.tabs.setMinimumWidth(max(420,sum(self.tabs.fontMetrics().horizontalAdvance(self.tabs.tabText(i))+36 for i in range(self.tabs.count()))))
        self.tabs.setUsesScrollButtons(False)
        self.tabs.currentChanged.connect(self.stack.setCurrentIndex)
        self.tabs.tabBarClicked.connect(lambda index:self.show_tab(self.tabs.tabText(index)))
        self.tabs.tabBarDoubleClicked.connect(lambda _:self.toggle_ribbon())
        p.layout().insertWidget(0,self.ribbon)
        self._build_commands()
        for name,layout in self.pages.items():
            if name!='Review':layout.addStretch(1)
        self.context=QWidget(); self.context.setObjectName('sheetContext'); row=QHBoxLayout(self.context)
        row.setContentsMargins(9,5,9,5); row.setSpacing(6)
        row.addWidget(QLabel('Records')); window.scope.setMinimumWidth(145); window.scope.setMaximumWidth(190); row.addWidget(window.scope); window.scope.show()
        column_label=QLabel('Column view'); column_label.setObjectName('columnViewLabel'); row.addWidget(column_label)
        p.view_selector.setMinimumWidth(125); p.view_selector.setMaximumWidth(165); row.addWidget(p.view_selector); p.view_selector.show()
        p.columns_button.setText('Manage columns'); row.addWidget(p.columns_button); p.columns_button.show()
        row.addStretch(1); p.search.setMinimumWidth(125); p.search.setMaximumWidth(220); p.search.setPlaceholderText('Find in sheet'); row.addWidget(p.search); p.search.show()
        p.clear_filters_btn.setText('Clear filters'); row.addWidget(p.clear_filters_btn); p.clear_filters_btn.show()
        row.addWidget(p.details_button); p.details_button.show()
        p.layout().insertWidget(1,self.context)
        # Active jobs still have visible pause/resume/cancel controls when used.
        p.layout().insertWidget(2,p.job_controls)
        self._formula_bar()
        self.footer=QWidget(); self.footer.setObjectName('sheetFooter'); bottom=QHBoxLayout(self.footer); bottom.setContentsMargins(6,3,6,3); bottom.setSpacing(6)
        bottom.addWidget(window.sheet_bar,1); window.sheet_bar.show()
        self.shared_label=QLabel('Campaign leads'); self.shared_label.setObjectName('sharedSheetLabel'); bottom.addWidget(self.shared_label)
        bottom.addWidget(p.reference_label,1); p.reference_label.setWordWrap(False); p.reference_label.show()
        for widget in (window.previous,window.paging,window.next):bottom.addWidget(widget); widget.show()
        p.layout().addWidget(self.footer)
        p.details_panel.hide(); p.details_button.setChecked(False)
        for table in (p.table,p.frozen_table):
            table.horizontalHeader().show_column_letters=True; table.horizontalHeader().setFixedHeight(48)
            table.verticalHeader().setDefaultSectionSize(27)
        self.show_tab('Home')
        shortcut=QShortcut(QKeySequence('Ctrl+F1'),p); shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut); shortcut.activated.connect(self.toggle_ribbon)
        self.ribbon.setStyleSheet('''
            QFrame#excelRibbon {background:#f8faf9;border-bottom:1px solid #ccd9d1;}
            QWidget#ribbonStrip {background:#217346;}
            QTabBar#ribbonTabs::tab {color:white;background:transparent;padding:7px 15px;border:0;margin:0;}
            QTabBar#ribbonTabs::tab:selected {background:#f8faf9;color:#185c37;border:0;}
            QTabBar#ribbonTabs::tab:hover {background:#308558;color:white;}
            QWidget#ribbonPage {background:#f8faf9;}
            QFrame#ribbonGroup {border:0;border-right:1px solid #d9e2dc;}
            QLabel#ribbonGroupLabel {color:#65746a;font-size:8pt;}
            QToolButton,QPushButton {padding:3px 7px;min-height:18px;max-height:27px;border-radius:3px;font-size:9pt;}
            QLabel,QCheckBox {font-size:9pt;color:#26382e;}
            QWidget#ribbonStrip QPushButton,QWidget#ribbonStrip QToolButton {background:#fff;color:#185c37;}
            QLineEdit,QComboBox {padding:4px 6px;min-height:18px;max-height:27px;}
        ''')
        self.context.setStyleSheet('QWidget#sheetContext{background:#f3f6f4;border-bottom:1px solid #d8e2db;} QLabel{color:#26382e;} QLabel#columnViewLabel{font-weight:650;color:#185c37;} QPushButton,QLineEdit,QComboBox{padding:4px 7px;min-height:18px;max-height:28px;font-size:9pt;}')
        self.footer.setStyleSheet('QWidget#sheetFooter{background:#eef2ef;border-top:1px solid #d2ddd5;} QTabBar::tab{padding:5px 12px;margin:0;} QTabBar::tab:selected{background:white;color:#217346;border-bottom:2px solid #217346;} QPushButton,QToolButton{padding:3px 6px;min-height:18px;max-height:26px;} QLabel{font-size:8pt;color:#526759;}')
        self._light_styles={widget:widget.styleSheet() for widget in (self.ribbon,self.context,self.footer,p.formula_bar)}

    def apply_theme(self,dark):
        colors={'#f8faf9':'#202b25','#f3f6f4':'#202b25','#eef2ef':'#202b25','#26382e':'#e2eee6',
                '#526759':'#bccdc1','#65746a':'#bccdc1','#185c37':'#9ed8b1','#ccd9d1':'#43584a',
                '#d9e2dc':'#43584a','#d8e2db':'#43584a','#d2ddd5':'#43584a','#d5ded8':'#43584a'}
        for widget,original in self._light_styles.items():
            style=original
            if dark:
                for source,target in colors.items():style=style.replace(source,target)
                style=style.replace('background:#fff;','background:#202b25;').replace('background:white;','background:#202b25;')
            widget.setStyleSheet(style)

    def button(self,label,callback,symbol=None):
        button=QToolButton(); button.setText(label); button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        if symbol:button.setIcon(icon(symbol,'#37694a'))
        button.setMinimumWidth(button.fontMetrics().horizontalAdvance(label)+48)
        button.clicked.connect(lambda checked=False:callback()); self.actions[label]=button
        return button

    def menu(self,label,entries,symbol=None):
        button=self.button(label,lambda:None,symbol); button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup); menu=QMenu(button)
        for text,callback in entries:menu.addAction(text,callback)
        button.setMenu(menu); return button

    def group(self,tab,title,*columns):
        group=QFrame(); group.setObjectName('ribbonGroup'); root=QVBoxLayout(group); root.setContentsMargins(4,1,10,0); root.setSpacing(1)
        row=QHBoxLayout(); row.setContentsMargins(0,0,0,0); row.setSpacing(5); root.addLayout(row,1)
        for controls in columns:
            col=QVBoxLayout(); col.setSpacing(3)
            for widget in controls:col.addWidget(widget); widget.show()
            col.addStretch(1); row.addLayout(col)
        label=QLabel(title); label.setObjectName('ribbonGroupLabel'); label.setAlignment(Qt.AlignmentFlag.AlignCenter); root.addWidget(label)
        self.pages[tab].addWidget(group)
        return group

    def _build_commands(self):
        p=self.page; w=self.window
        self.group('File','Worksheets',[self.button('New worksheet',w.new_sheet,'plus'),self.button('Save recovery draft',w.recover_draft,'document')])
        self.group('File','Export',[p.export_button,self.button('Export validation errors',w.export_errors,'validation')])
        self.group('File','Help',[self.button('Worksheet shortcuts',p.formula_help,'info')])
        self.group('Home','Clipboard',[self.button('Paste',p.table.paste_clipboard,'document'),self.button('Copy',p.table.copy_selection,'copy')],
            [self.button('Cut',lambda:w.copy_authorized(p.table,True),'edit'),self.button('Clear cells',self.clear_cells,'close')])
        self.group('Home','Columns',[p.add_columns_button,self.button('Delete custom columns',p.delete_columns,'columns')])
        self.group('Home','Editing',[w.workspace_buttons['Find / replace'],self.button('Filter selected column',self.filter_column,'filter')])
        validation={b.text():b for b in p.validation_actions.findChildren(QPushButton)+p.validation_actions.findChildren(QToolButton)}
        self.validation_widgets=[validation['Validate'],validation['Rows'],validation['Summary']]
        self.validation_group=self.group('Home','Validation',[validation['Validate'],validation['Rows']])
        self.group('Home','Workflow',[self.button('Review and send',lambda:self.show_tab('Review'),'arrow')])
        references=next(b for b in p.action_controls.findChildren(QToolButton) if b.text()=='Reference lists')
        self.group('Data','Get data',[p.import_button,validation['Find emails']])
        self.group('Data','Reference data',[p.populate_button,references])
        self.group('Data','Filter',[QLabel('Validation status'),p.status])
        self.campaign_search_group=self.group('Data','Search all campaign leads',[w.query,self.button('Search campaign',w.refresh_records,'search')])
        self.group('Formulas','Function library',[p.formula_button,self.button('Insert column reference',p.insert_column_reference,'columns')])
        self.group('Formulas','Quick functions',[self.button('Sum',lambda:p.insert_named_function('SUM'),'plus'),self.button('Lookup',lambda:p.insert_named_function('XLOOKUP'),'search')])
        self.group('Formulas','Fill',[self.button('Fill down',p.fill_down,'download'),self.button('Fill right',p.fill_right,'arrow')])
        show=QToolButton(); show.setDefaultAction(p.show_formulas_action); self.actions['Show formulas']=show
        self.group('Formulas','Calculate',[self.button('Recalculate',p.calculate_now,'check'),show],
            [self.button('Convert formulas to values',p.formulas_to_values,'edit'),self.button('Formula help',p.formula_help,'info')])
        # Reuse the permission-aware handoff controls, grouped like the other tabs.
        review=QWidget(); layout=QVBoxLayout(review); layout.setContentsMargins(0,0,0,0); layout.setSpacing(1)
        self.pages['Review'].addWidget(review,1); self.pages['Review']=QHBoxLayout(); self.pages['Review'].setSpacing(6); layout.addLayout(self.pages['Review'],1)
        w.handoff_bar.hide()
        self.group('Review','Review stage',[w.stage_button,w.workspace_buttons['Return for rework']])
        self.assignment_group=self.group('Review','Assignment',[w.incoming_button,w.assign_button])
        self.handoff_group=self.group('Review','Send leads',[w.push_button])
        self.group('Review','History',[w.workspace_buttons['View History'],self.menu('Notes and history',[('Comments',w.comments),('Transfer history',w.transfer_history)],'document')])
        self.review_validation_group=self.group('Review','Validation',[validation['Summary'],w.commit_button])
        w.commit_button.setText('Commit valid rows')
        self.record_group=self.group('Review','Records',[self.menu('Manage records',[('Archive selected',w.archive_selected),('Restore selected',w.restore_selected),('Assign historical owner',w.assign_historical)],'settings')])
        self.pages['Review'].addStretch(1)
        w.handoff_hint.setWordWrap(False); w.handoff_hint.setFixedHeight(17)
        w.handoff_hint.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        layout.addWidget(w.handoff_hint); w.handoff_hint.show()
        self.group('View','Freeze',[p.freeze_identity])
        self.group('View','Saved filters',[self.button('Save filter view',w.save_filter_view,'filter'),self.button('Load filter view',w.load_filter_view,'folder')])
        self.group('View','Column sizing',[self.button('Fit columns to content',self.fit_columns,'columns')])
        self.group('View','Workspace',[self.button('Collapse / expand ribbon',self.toggle_ribbon,'menu'),self.button('Collapse / expand sidebar',w.toggle_sidebar,'panel')])

    def _formula_bar(self):
        p=self.page; layout=p.formula_bar.layout()
        old=p.formula_address; layout.removeWidget(old); old.hide()
        p.formula_address=QLineEdit(); p.formula_address.setFixedWidth(76); p.formula_address.setMaxLength(12); p.formula_address.setAccessibleName('Cell address'); p.formula_address.setPlaceholderText('A1')
        p.formula_address.setToolTip('Go to an original worksheet cell, for example A1. Hidden or filtered cells stay hidden.'); p.formula_address.returnPressed.connect(self.go_to_cell)
        layout.insertWidget(0,p.formula_address)
        fx=self.button('ƒx',p.insert_function); fx.setToolTip('Insert function · Shift+F3'); fx.setFixedWidth(34); layout.insertWidget(1,fx)
        p.formula_bar.setStyleSheet('QWidget#formulaBar{background:#f3f6f4;border-bottom:1px solid #d5ded8;} QLineEdit{border-radius:0;padding:3px 5px;min-height:20px;} QToolButton,QPushButton{padding:2px 5px;min-height:20px;}')
        p.sync_formula_bar()

    def show_tab(self,name):
        index=next(i for i in range(self.tabs.count()) if self.tabs.tabText(i)==name)
        self.tabs.setCurrentIndex(index); self.set_collapsed(False)

    def toggle_ribbon(self):
        self.set_collapsed(not self.stack.isHidden())

    def set_collapsed(self,collapsed,persist=True):
        self.stack.setVisible(not collapsed); self.ribbon.setFixedHeight(32 if collapsed else 128)
        self.collapse.setIcon(icon('chevron-down' if collapsed else 'chevron-up','#217346'))
        self.collapse.setAccessibleName('Expand ribbon' if collapsed else 'Collapse ribbon')
        self.collapse.setToolTip(('Expand' if collapsed else 'Collapse')+' ribbon · Ctrl+F1')
        self.ribbon.updateGeometry(); self.page.layout().invalidate(); self.page.layout().activate()
        if persist:self.window.controller.settings_service.set('ribbon_collapsed',collapsed)

    def update_mode(self):
        w=self.window; draft=w.scope.currentData() in ('draft','all_sheets')
        editable=draft and w.controller.sheet is not None and not w.controller.read_only_sheet and not w.busy
        role=(w.client.user or {}).get('role'); supervisor=role in ('Super User','Department Manager','Team Lead')
        self.shared_label.setVisible(not draft)
        for widget in self.validation_widgets:widget.setVisible(w.allowed('validation'))
        self.validation_group.setVisible(w.allowed('validation')); self.review_validation_group.setVisible(w.allowed('validation'))
        self.campaign_search_group.setVisible(not draft)
        self.assignment_group.setVisible(supervisor); self.handoff_group.setVisible(supervisor and not draft)
        self.record_group.setVisible(not draft and role in ('Super User','Department Manager'))
        for action in self.actions['Manage records'].menu().actions():
            action.setVisible(role=='Super User' or action.text()=='Archive selected')
        w.workspace_buttons['Return for rework'].setVisible(not draft and (supervisor or (w.client.user or {}).get('department_id')=='quality'))
        self.actions['Search campaign'].setEnabled(not draft and not w.busy)
        self.actions['Delete custom columns'].setEnabled(editable)
        self.page.add_columns_button.setEnabled(editable)
        self.page.import_button.setEnabled(editable)
        self.page.import_button.setToolTip('Choose Records: Working drafts to import and validate before publishing.' if not editable else 'Import Excel or CSV into this draft.')

    def selected_table(self):
        p=self.page; column=p.table.currentIndex().column()
        return p.frozen_table if column>=0 and not p.frozen_table.isColumnHidden(column) else p.table

    def clear_cells(self):
        p=self.page
        if p._data_busy:return
        p.model.clear_cells([p.proxy.mapToSource(i) for i in p.table.selectedIndexes()]); p.refresh()

    def filter_column(self):
        index=self.page.table.currentIndex()
        if index.isValid():self.page.open_filter(index.column())

    def fit_columns(self):
        p=self.page
        for table in (p.table,p.frozen_table):
            for column in range(p.model.columnCount()):
                if not table.isColumnHidden(column):table.resizeColumnToContents(column)

    def go_to_cell(self):
        p=self.page
        if p._data_busy:return
        match=re.fullmatch(r'\$?([A-Za-z]+)\$?([1-9][0-9]*)',p.formula_address.text().strip())
        if not match:p.sync_formula_bar(); return
        column=0
        for char in match[1].upper():column=column*26+ord(char)-64
        column-=1; row=int(match[2])-1
        index=p.proxy.mapFromSource(p.model.index(row,column)) if row<p.model.rowCount() and column<p.model.columnCount() else None
        if index is None or not index.isValid() or (p.table.isColumnHidden(column) and p.frozen_table.isColumnHidden(column)):
            QMessageBox.information(p,'Go to cell','This cell is outside the current sheet or hidden by its column view or filters. Change the column view or clear filters first.'); p.sync_formula_bar(); return
        table=p.frozen_table if not p.frozen_table.isColumnHidden(column) else p.table
        table.setCurrentIndex(index); table.scrollTo(index); table.setFocus(); p.sync_formula_bar()
