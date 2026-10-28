"""Repeatable, server-local adoption of legacy snapshots, without guessing owners."""
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path
from app.core.workspace_store import WorkspaceStore
from app.team.schema import migrate,transaction
from app.team.leads import keys_for,config_for


def adopt_workspaces(database,folder):
    migrate(database); store=WorkspaceStore(folder); summary={'sources':0,'leads':0,'skipped_sources':0,'duplicate_rows':0}
    with transaction(database) as db:
        db.execute('CREATE TABLE IF NOT EXISTS team_legacy_payloads(source_key TEXT PRIMARY KEY,campaign_id TEXT NOT NULL,payload_json TEXT NOT NULL)')
        profiles=list(db.execute('SELECT campaign_id FROM campaign_profiles'))
        sources=[(r[0],WorkspaceStore.key(r[0])) for r in profiles]
        sources.append(('legacy-general','general'))
        for cid,key in sources:
            payload=store.load(key)
            if not payload:continue
            digest=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            prior=db.execute('SELECT digest FROM team_legacy_sources WHERE source_key=?',(key,)).fetchone()
            if prior:
                if prior[0]!=digest:raise ValueError('A previously adopted legacy worksheet changed. Stop local edits and reconcile it before repeating migration: '+key)
                summary['skipped_sources']+=1; continue
            if cid=='legacy-general':
                db.execute("INSERT OR IGNORE INTO campaign_profiles(campaign_id,campaign_name,source_root,payload_json) VALUES(?,'Historical general worksheet','','{}')",(cid,))
            db.execute('INSERT INTO team_legacy_payloads VALUES(?,?,?)',(key,cid,json.dumps(payload)))
            config=config_for(db,cid)
            for index,record in enumerate(payload['records']):
                lid=str(uuid.uuid5(uuid.NAMESPACE_URL,'lead-workspace:'+key+':'+str(index)))
                duplicate=False
                db.execute("INSERT INTO team_leads(id,campaign_id,record_json,state,validation) VALUES(?,?,?,'Pending Validation','Pending Review')",(lid,cid,json.dumps(record)))
                for kind,value in keys_for(record,config):
                    cursor=db.execute('INSERT OR IGNORE INTO team_lead_keys VALUES(?,?,?,?)',(cid,kind,value,lid))
                    duplicate=duplicate or cursor.rowcount==0
                if duplicate:
                    db.execute("UPDATE team_leads SET validation='Duplicate' WHERE id=?",(lid,)); summary['duplicate_rows']+=1
                db.execute("INSERT INTO team_history(lead_id,campaign_id,event,field,new_json) VALUES(?,?,'legacy-adoption','record',?)",(lid,cid,json.dumps(record)))
                summary['leads']+=1
            db.execute('INSERT INTO team_legacy_sources(source_key,digest) VALUES(?,?)',(key,digest)); summary['sources']+=1
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'campaign_tracking' in tables:
            for row in db.execute('SELECT * FROM campaign_tracking').fetchall():
                values=dict(row); cid=values.get('campaign_id')
                if cid and not db.execute('SELECT 1 FROM team_campaign_config WHERE campaign_id=?',(cid,)).fetchone():
                    config={k:values[k] for k in ('allocation','start_date','end_date','delivered','status') if k in values and values[k] is not None}
                    db.execute('INSERT INTO team_campaign_config(campaign_id,config_json) VALUES(?,?)',(cid,json.dumps(config)))
    return summary


def backup_database(database,destination):
    if not Path(database).is_file():raise ValueError('The source database does not exist.')
    target=Path(destination)
    if target.exists():raise ValueError('Backup destination already exists.')
    target.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(database) as source,sqlite3.connect(target) as copy:
        source.backup(copy)
        if copy.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Backup integrity check failed.')
    return str(target)
