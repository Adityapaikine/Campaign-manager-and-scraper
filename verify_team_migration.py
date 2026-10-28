"""Verify migration on a fresh copy, never print record contents."""
from pathlib import Path
import json
import sqlite3
from datetime import datetime
from suite_bootstrap import configure
configure()
from app.utils.config import DB_PATH,DATA_DIR
from app.team.legacy import backup_database,adopt_workspaces
from app.team.schema import transaction

target=Path('TestArtifacts')/('migration-copy-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
target.mkdir(parents=True)
copy=target/'lead_manager.sqlite3'; backup_database(DB_PATH,copy)
with sqlite3.connect(copy) as db:
    tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'team_%'")]
    before={t:db.execute('SELECT count(*) FROM "'+t.replace('"','""')+'"').fetchone()[0] for t in tables}
first=adopt_workspaces(copy,DATA_DIR/'workspaces'); second=adopt_workspaces(copy,DATA_DIR/'workspaces')
with transaction(copy,False) as db:
    after={t:db.execute('SELECT count(*) FROM "'+t.replace('"','""')+'"').fetchone()[0] for t in tables}
    assert all(after[t]==before[t] for t in tables if t!='campaign_profiles')
    assert second['leads']==0
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert not db.execute('SELECT 1 FROM team_leads WHERE owner_id IS NOT NULL').fetchone()
    report={'first':first,'repeat':second,'legacy_table_counts_preserved':True,'integrity':'ok','foreign_keys':'ok','unknown_owners_remain_unassigned':True}
(target/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8'); print(json.dumps({'artifact':str(target),'result':report}))
