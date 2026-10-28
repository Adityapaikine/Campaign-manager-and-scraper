"""Render ribbon and worksheet examples against synthetic, isolated data."""
import os,sys,tempfile,secrets,logging,json
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
temporary=tempfile.TemporaryDirectory(prefix='lead-excel-preview-')
os.environ['LEAD_WORKSPACE_DATA_DIR']=str(Path(temporary.name)/'Data'); os.environ['QT_QPA_PLATFORM']='offscreen'
from suite_bootstrap import configure
configure()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QItemSelectionModel
from app.team.service import Service
from app.team.demo import create_demo,sample_record
from app.ui_qt.team_window import TeamWindow
from tests.test_team_ui import DirectClient,wait_ready
qt=QApplication([]); qt.setStyle('Fusion')
for filename in ('segoeui.ttf','segoeuib.ttf'):QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/filename))
service=Service(Path(temporary.name)/'preview.sqlite3'); service.bootstrap('Preview admin','preview','preview@example.com',secrets.token_urlsafe(24))
demo=create_demo(service); measurements={}
for username,suffix in [('demo.ops.lead','shared'),('demo.ops.employee','draft')]:
    account=next(a for a in demo['accounts'] if a['username']==username)
    client=DirectClient(service,service.login(username,account['password']))
    window=TeamWindow(client); window.show(); wait_ready(qt,window)
    try:
        if suffix=='draft':
            window.set_workspace_mode('draft'); wait_ready(qt,window)
            rows=[sample_record(i) for i in range(11,45)]
            window.controller.data_manager.replace_all(rows); window.controller.dirty=True; window.leads.refresh(); window.mark_dirty()
            window.leads.view_selector.setCurrentText('Research')
        index=window.leads.proxy.mapFromSource(window.leads.model.index(0,window.controller.data_manager.headers.index('First Name')))
        window.leads.table.setCurrentIndex(index); window.leads.table.selectionModel().select(index,QItemSelectionModel.SelectionFlag.ClearAndSelect)
        window.resize(1540,940); qt.processEvents(); window.grab().save(str(root/f'TestArtifacts/excel-{suffix}-desktop.png'))
        window.resize(1366,768); qt.processEvents(); window.grab().save(str(root/f'TestArtifacts/excel-{suffix}-laptop.png'))
        measurements[suffix]={'grid_height':window.leads.table.viewport().height(),'width':window.width(),'height':window.height()}
        for tab in ('Data','Formulas','Review','View'):
            window.excel_workspace.show_tab(tab); qt.processEvents(); window.grab().save(str(root/f'TestArtifacts/excel-{suffix}-{tab.lower()}.png'))
        window.excel_workspace.show_tab('Home'); window.excel_workspace.toggle_ribbon(); qt.processEvents()
        measurements[suffix]['collapsed_grid_height']=window.leads.table.viewport().height()
        window.grab().save(str(root/f'TestArtifacts/excel-{suffix}-collapsed.png'))
        window.excel_workspace.toggle_ribbon(); window.controller.settings.appearance_mode='Dark'; window.apply_theme(); qt.processEvents()
        window.grab().save(str(root/f'TestArtifacts/excel-{suffix}-dark.png'))
        window.resize(1120,720); qt.processEvents(); window.grab().save(str(root/f'TestArtifacts/excel-{suffix}-minimum.png'))
    finally:window._closing=True; window.close(); qt.processEvents()
(root/'TestArtifacts/excel-layout-measurements.json').write_text(json.dumps(measurements,indent=2),encoding='utf-8')
logging.shutdown(); temporary.cleanup()
print(json.dumps(measurements))
