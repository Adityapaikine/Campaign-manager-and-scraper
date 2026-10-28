"""Render synthetic workflow examples; no live accounts or leads are accessed."""
import os,sys,tempfile,secrets,logging
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
temporary=tempfile.TemporaryDirectory(prefix='lead-handoff-preview-')
os.environ['LEAD_WORKSPACE_DATA_DIR']=str(Path(temporary.name)/'Data')
os.environ['QT_QPA_PLATFORM']='offscreen'
from suite_bootstrap import configure
configure()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import QItemSelectionModel
from app.team.service import Service
from app.team.demo import create_demo
from app.ui_qt.team_window import TeamWindow
from app.ui_qt.dialogs.handoff_dialog import HandoffDialog
from tests.test_team_ui import DirectClient,wait_ready
qt=QApplication([]); qt.setStyle('Fusion')
for filename in ('segoeui.ttf','segoeuib.ttf'):QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/filename))
service=Service(Path(temporary.name)/'preview.sqlite3'); password=secrets.token_urlsafe(24)
service.bootstrap('Preview Admin','preview','preview@example.com',password)
demo=create_demo(service)
for username,suffix in [('demo.ops.lead','operations'),('demo.quality.lead','quality'),('demo.delivery.lead','delivery')]:
    account=next(a for a in demo['accounts'] if a['username']==username)
    client=DirectClient(service,service.login(username,account['password']))
    window=TeamWindow(client); window.show(); wait_ready(qt,window)
    window.leads.toggle_details(False)
    row=next((i for i,r in enumerate(window.controller.lead_rows) if r['state'] in ('Approved','Quality Qualified','Transferred to Delivery')),0)
    column=window.controller.data_manager.headers.index('First Name')
    index=window.leads.proxy.mapFromSource(window.leads.model.index(row,column))
    window.leads.table.setCurrentIndex(index)
    window.leads.table.selectionModel().select(index,QItemSelectionModel.SelectionFlag.ClearAndSelect)
    qt.processEvents(); window.grab().save(str(root/f'TestArtifacts/handoff-{suffix}.png'))
    if suffix=='operations':
        window.resize(1366,768); qt.processEvents(); window.grab().save(str(root/'TestArtifacts/handoff-laptop.png'))
        preview=client.call('selection_actions',selection=window.selection())
        dialog=HandoffDialog(window,preview); dialog.show(); qt.processEvents(); dialog.grab().save(str(root/'TestArtifacts/handoff-preview.png')); dialog.close()
    window._closing=True; window.close(); qt.processEvents()
logging.shutdown(); temporary.cleanup()
print('Rendered Operations, Quality, Delivery and transfer previews using synthetic data.')
