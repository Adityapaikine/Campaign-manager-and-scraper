"""Render synthetic previews in isolated temporary storage; never use live records."""
import os,sys,tempfile,secrets
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
temporary=tempfile.TemporaryDirectory(prefix='team-preview-')
os.environ['LEAD_WORKSPACE_DATA_DIR']=str(Path(temporary.name)/'Data')
os.environ['QT_QPA_PLATFORM']='offscreen'
from suite_bootstrap import configure
configure()
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import Qt
from tests.test_team_ui import DirectClient,wait_ready
from app.team.service import Service
from app.ui_qt.team_window import TeamWindow
qt=QApplication([]); qt.setStyle('Fusion')
for name in ('segoeui.ttf','segoeuib.ttf'):QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR'])/'Fonts'/name))
service=Service(Path(temporary.name)/'preview.sqlite3'); password=secrets.token_urlsafe(30)
service.bootstrap('Preview Admin','preview','preview@example.com',password)
client=DirectClient(service,service.login('preview',password))
client.call('campaign_save',campaign_id='DEMO-2026',campaign_name='Business research · Preview data',config={'require_tal_match':False,'allocation':200,'delivered':3,'start_date':'2026-10-21','end_date':'2026-11-20','status':'Running'})
names=['Aarav','Maya','Rohan','Priya','Neha','Arjun','Sam','Aisha','Alex','Isha','Dev','Nina','Sana','Jay','Riya']
rows=[{'Date':'25-Oct-2026','Campaign Name':'Business research','Agent Name':'Research team','Calling Agent Name':'Research team',
       'First Name':name,'Last Name':'Sample','Company Name':'Example Company','Company Website':'example.com',
       'Phone Number':f'+1 202-555-{100+i:04d}','Business Email ID':f'sample{i}@example.com','Job Title':'Marketing Director',
       'Country':'United States','Prospect LinkedIn Link':f'https://www.linkedin.com/in/sample-{i}',
       'Dispo':['Connected','Follow Up','Not Interested'][i%3],'Comment':['Requested company information','Call next week','Review account requirements'][i%3]} for i,name in enumerate(names)]
client.call('commit',campaign_id='DEMO-2026',records=rows[:8],request_key=secrets.token_hex(16))
sheet=client.call('sheet_create',campaign_id='DEMO-2026',name='Research draft')
client.call('sheet_save',sheet_id=sheet['id'],version=1,payload={'records':rows})
window=TeamWindow(client); window.show(); wait_ready(qt,window)
window.navigate('dashboard'); wait_ready(qt,window)
window.grab().save(str(root/'TestArtifacts/unified-dashboard.png'))
window.nav.setCurrentRow(window.items.index('Lead Workspace')); wait_ready(qt,window)
window.leads.view_selector.setCurrentText('Lead overview'); qt.processEvents()
window.leads.table.setCurrentIndex(window.leads.proxy.index(0,0)); qt.processEvents()
window.grab().save(str(root/'TestArtifacts/unified-workspace.png'))
window.resize(1366,768); qt.processEvents()
assert window.width()<=1366
window.grab().save(str(root/'TestArtifacts/unified-workspace-laptop.png'))
window.navigate('administration'); wait_ready(qt,window)
window.admin_tabs.setCurrentIndex(window.admin_tabs.count()-1); qt.processEvents()
window.grab().save(str(root/'TestArtifacts/unified-module-permissions.png'))
window.navigate('scraper'); wait_ready(qt,window)
window.grab().save(str(root/'TestArtifacts/unified-scraper.png'))
window._closing=True; window.close(); qt.processEvents()
print('Rendered synthetic dashboard, workspace and 1366 x 768 previews.')
import logging
logging.shutdown()
temporary.cleanup()
