"""Visual check using isolated synthetic accounts; never opens the live database."""
import os,sys,tempfile,secrets,logging
from pathlib import Path
root=Path.cwd(); sys.path.insert(0,str(root))
temp=tempfile.TemporaryDirectory(prefix='lead-super-preview-')
os.environ['LEAD_WORKSPACE_DATA_DIR']=str(Path(temp.name)/'Data'); os.environ['QT_QPA_PLATFORM']='offscreen'
from suite_bootstrap import configure
configure()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from app.team.service import Service
from app.team.demo import create_demo
from app.ui_qt.team_window import TeamWindow
from tests.test_team_ui import DirectClient,wait_ready
qt=QApplication([]); qt.setStyle('Fusion')
for name in ('segoeui.ttf','segoeuib.ttf'): QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/name))
secret=secrets.token_urlsafe(24)
service=Service(Path(temp.name)/'preview.sqlite3'); service.bootstrap('Super User Preview','preview','preview@example.com',secret)
demo=create_demo(service)
client=DirectClient(service,service.login('preview',secret))
window=TeamWindow(client); window.show(); wait_ready(qt,window)
try:
    window.select_campaign_id('DEMO-FLOW'); wait_ready(qt,window)
    window.set_workspace_mode('all_sheets'); wait_ready(qt,window)
    target=next(s for s in window.sheet_rows if s['owner_id']!=client.user['id'])
    window.load_sheet(target['id']); wait_ready(qt,window)
    window.leads.view_selector.setCurrentText('Research'); window.excel_workspace.show_tab('Review')
    for width,height,suffix in [(1366,768,'laptop'),(1120,720,'minimum')]:
        window.resize(width,height); qt.processEvents(); window.grab().save(str(root/f'TestArtifacts/super-user-worksheets-{suffix}.png'))
        print(f'{suffix}: window={window.width()}x{window.height()}, grid={window.leads.table.viewport().height()}px')
finally:
    window._closing=True; window.close(); qt.processEvents(); logging.shutdown(); temp.cleanup()
