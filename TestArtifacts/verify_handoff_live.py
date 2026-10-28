"""Verify additive demo provisioning, then live sign-in/read-only handoff previews."""
import sys,json,sqlite3
from collections import Counter
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root))
from suite_bootstrap import configure
configure()
from app.utils.config import DB_PATH
from app.team.client import TeamClient

backup=DB_PATH.with_name('before-demo-20261026-213916.sqlite3')
results={}
with sqlite3.connect(backup) as before,sqlite3.connect(DB_PATH) as after:
    tables=[r[0] for r in before.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    changed=[]
    for table in tables:
        identifier='"'+table.replace('"','""')+'"'
        if not Counter(before.execute('SELECT * FROM '+identifier).fetchall())<=Counter(after.execute('SELECT * FROM '+identifier).fetchall()):changed.append(table)
    results['preexisting_rows_preserved']=not changed; results['checked_tables']=len(tables); results['changed_tables']=changed
    results['integrity']=after.execute('PRAGMA integrity_check').fetchone()[0]
    results['foreign_key_errors']=len(after.execute('PRAGMA foreign_key_check').fetchall())
    results['counts']={table:after.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in ('team_users','team_leads','team_sheets','campaign_profiles')}
    results['demo_stages']=[{'department':r[0],'stage':r[1],'count':r[2]} for r in after.execute("SELECT department_id,state,count(*) FROM team_leads WHERE campaign_id='DEMO-FLOW' GROUP BY department_id,state")]
assert not changed and results['integrity']=='ok' and not results['foreign_key_errors']
lines=(DB_PATH.parent.parent/'demo-accounts.txt').read_text(encoding='utf-8').splitlines()
accounts=[line.split('\t') for line in lines if line.startswith('demo.')]
checks=[]
for username,password,role,department in accounts:
    client=TeamClient(); client.login(username,password)
    try:
        campaigns=client.call('campaigns'); assert [c['campaign_id'] for c in campaigns]==['DEMO-FLOW']
        modules=client.call('modules'); assert not modules['administration']['allowed']
        if department in ('quality','delivery'):assert not modules['scraper']['allowed']
        leads=client.call('leads',campaign_id='DEMO-FLOW',view='department' if role=='Team Lead' else 'mine')
        previewed=False
        if role=='Team Lead' and department in ('operations','quality'):
            row=next(r for r in leads['rows'] if r['state'] in ('Approved','Quality Qualified'))
            preview=client.call('selection_actions',selection=[{'id':row['id'],'version':row['version']}])
            assert any(route['ready']==1 for route in preview['routes']); previewed=True
        checks.append({'username':username,'login':True,'campaign_scope':'DEMO-FLOW only','handoff_preview':previewed,'rows_visible':leads['total']})
    finally:client.logout(); client.http.close()
results['live_accounts']=checks
(root/'TestArtifacts/handoff-live-verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
