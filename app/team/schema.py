"""Additive, versioned multi-user schema. Legacy tables and files are untouched."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

ROLES = ("Super User", "Department Manager", "Team Lead", "Employee")
STATES = ("Draft", "Pending Validation", "Validation Failed", "Validated", "Pending Team Lead Review", "Approved",
          "Rework Required", "Transferred to Quality", "Quality In Progress", "Quality Qualified", "Quality Disqualified",
          "Quality TBD", "Transferred to Delivery", "Delivery Approved", "Delivered")
REASONS = ("Incorrect Job Title", "Invalid Email", "Duplicate Lead", "Incorrect Company", "Incorrect Country",
           "Incorrect Industry", "Incorrect Company Size", "Prospect Not Eligible", "Account Not in Target Account List",
           "Account in Suppression List", "Missing Mandatory Fields", "Other")

SCHEMA = """
CREATE TABLE IF NOT EXISTS team_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS team_departments(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
CREATE TABLE IF NOT EXISTS team_users(
 id TEXT PRIMARY KEY, full_name TEXT NOT NULL, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
 email TEXT NOT NULL UNIQUE COLLATE NOCASE, password_hash TEXT NOT NULL,
 department_id TEXT REFERENCES team_departments(id), role TEXT NOT NULL CHECK(role IN ('Super User','Department Manager','Team Lead','Employee')),
 manager_id TEXT REFERENCES team_users(id), team_lead_id TEXT REFERENCES team_users(id),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_login TEXT);
CREATE TABLE IF NOT EXISTS team_sessions(hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES team_users(id), expires REAL NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS team_login_attempts(key TEXT PRIMARY KEY, failures INTEGER NOT NULL, blocked_until REAL NOT NULL);
CREATE TABLE IF NOT EXISTS team_campaign_users(campaign_id TEXT NOT NULL REFERENCES campaign_profiles(campaign_id), user_id TEXT NOT NULL REFERENCES team_users(id), PRIMARY KEY(campaign_id,user_id));
CREATE TABLE IF NOT EXISTS team_campaign_config(campaign_id TEXT PRIMARY KEY REFERENCES campaign_profiles(campaign_id), version INTEGER NOT NULL DEFAULT 1, config_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS team_leads(
 id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaign_profiles(campaign_id),
 owner_id TEXT REFERENCES team_users(id), created_by TEXT REFERENCES team_users(id), assigned_id TEXT REFERENCES team_users(id),
 department_id TEXT REFERENCES team_departments(id), team_lead_id TEXT REFERENCES team_users(id),
 record_json TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'Draft', validation TEXT NOT NULL DEFAULT 'Pending Review',
 validation_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_by TEXT REFERENCES team_users(id));
CREATE INDEX IF NOT EXISTS team_leads_campaign ON team_leads(campaign_id, archived, department_id, state);
CREATE INDEX IF NOT EXISTS team_leads_owner ON team_leads(owner_id, campaign_id);
CREATE INDEX IF NOT EXISTS team_leads_assigned ON team_leads(assigned_id, campaign_id);
CREATE INDEX IF NOT EXISTS team_leads_team ON team_leads(team_lead_id, department_id);
CREATE TABLE IF NOT EXISTS team_lead_keys(campaign_id TEXT NOT NULL REFERENCES campaign_profiles(campaign_id), kind TEXT NOT NULL, value TEXT NOT NULL, lead_id TEXT NOT NULL REFERENCES team_leads(id), PRIMARY KEY(campaign_id,kind,value));
CREATE INDEX IF NOT EXISTS team_keys_lead ON team_lead_keys(lead_id);
CREATE TABLE IF NOT EXISTS team_sheets(id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaign_profiles(campaign_id), owner_id TEXT NOT NULL REFERENCES team_users(id), name TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}', version INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS team_sheets_owner ON team_sheets(owner_id,campaign_id,archived);
CREATE TABLE IF NOT EXISTS team_sheet_leads(sheet_id TEXT NOT NULL REFERENCES team_sheets(id), lead_id TEXT NOT NULL REFERENCES team_leads(id), PRIMARY KEY(sheet_id,lead_id));
CREATE TABLE IF NOT EXISTS team_draft_keys(campaign_id TEXT NOT NULL REFERENCES campaign_profiles(campaign_id), sheet_id TEXT NOT NULL REFERENCES team_sheets(id), row_number INTEGER NOT NULL, kind TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(sheet_id,row_number,kind));
CREATE INDEX IF NOT EXISTS team_draft_match ON team_draft_keys(campaign_id,kind,value);
CREATE TABLE IF NOT EXISTS team_batches(id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaign_profiles(campaign_id), user_id TEXT NOT NULL REFERENCES team_users(id), request_key TEXT NOT NULL, digest TEXT NOT NULL, source_name TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,request_key));
CREATE TABLE IF NOT EXISTS team_history(id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT NOT NULL REFERENCES team_leads(id), user_id TEXT REFERENCES team_users(id), campaign_id TEXT NOT NULL, department_id TEXT, event TEXT NOT NULL, field TEXT NOT NULL, old_json TEXT, new_json TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS team_history_lead ON team_history(lead_id,id);
CREATE TABLE IF NOT EXISTS team_transfers(id TEXT PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES team_leads(id), from_department TEXT REFERENCES team_departments(id), to_department TEXT NOT NULL REFERENCES team_departments(id), previous_assignee TEXT REFERENCES team_users(id), transferred_by TEXT NOT NULL REFERENCES team_users(id), note TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Pending Assignment', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS team_transfers_lead ON team_transfers(lead_id,created_at);
CREATE TABLE IF NOT EXISTS team_notifications(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL REFERENCES team_users(id), event TEXT NOT NULL, campaign_id TEXT, lead_id TEXT REFERENCES team_leads(id), text TEXT NOT NULL, is_read INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS team_comments(id INTEGER PRIMARY KEY AUTOINCREMENT, lead_id TEXT NOT NULL REFERENCES team_leads(id), user_id TEXT NOT NULL REFERENCES team_users(id), body TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS team_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, event TEXT NOT NULL, resource TEXT, outcome TEXT NOT NULL, details_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS team_permissions(id TEXT PRIMARY KEY, department_id TEXT REFERENCES team_departments(id), role TEXT, campaign_id TEXT REFERENCES campaign_profiles(campaign_id), field TEXT NOT NULL, access TEXT NOT NULL CHECK(access IN ('Hidden','Read Only','Edit','Approve','Export')));
CREATE TABLE IF NOT EXISTS team_reasons(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS team_routes(id TEXT PRIMARY KEY, campaign_id TEXT REFERENCES campaign_profiles(campaign_id), from_department TEXT NOT NULL REFERENCES team_departments(id), to_department TEXT NOT NULL REFERENCES team_departments(id), required_state TEXT NOT NULL, arrival_state TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, CHECK(from_department<>to_department));
CREATE TABLE IF NOT EXISTS team_transitions(id TEXT PRIMARY KEY, from_state TEXT NOT NULL, to_state TEXT NOT NULL, role TEXT NOT NULL, department_id TEXT REFERENCES team_departments(id), active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS team_preferences(user_id TEXT NOT NULL REFERENCES team_users(id), key TEXT NOT NULL, value_json TEXT NOT NULL, PRIMARY KEY(user_id,key));
CREATE TABLE IF NOT EXISTS team_legacy_sources(source_key TEXT PRIMARY KEY, digest TEXT NOT NULL, migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS team_module_permissions(subject_type TEXT NOT NULL CHECK(subject_type IN ('department','user')),subject_id TEXT NOT NULL,module TEXT NOT NULL,allowed INTEGER NOT NULL CHECK(allowed IN (0,1)),PRIMARY KEY(subject_type,subject_id,module));
"""

@contextmanager
def transaction(path, write=True):
    db = sqlite3.connect(path, timeout=30, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=30000")
    try:
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()

def migrate(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        # Campaign identity remains the existing campaign_profiles table.
        db.execute("""CREATE TABLE IF NOT EXISTS campaign_profiles(campaign_id TEXT PRIMARY KEY,campaign_name TEXT NOT NULL,
          source_root TEXT NOT NULL DEFAULT '',payload_json TEXT NOT NULL DEFAULT '{}',active INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        db.executescript(SCHEMA)
        if not db.execute("SELECT 1 FROM team_migrations WHERE version=1").fetchone():
            for name in ("Operations","Quality","DBA","Delivery"):
                db.execute("INSERT OR IGNORE INTO team_departments VALUES(?,?,1)",(name.lower(),name))
            for i,name in enumerate(REASONS): db.execute("INSERT OR IGNORE INTO team_reasons VALUES(?,?,1)",(str(i+1),name))
            routes=[('operations','quality','Approved','Transferred to Quality'),('quality','delivery','Quality Qualified','Transferred to Delivery')]
            for i,route in enumerate(routes): db.execute("INSERT OR IGNORE INTO team_routes VALUES(?,NULL,?,?,?,?,1)",(str(i+1),*route))
            transitions=[('Draft','Pending Validation',ROLES,None),('Validation Failed','Pending Validation',ROLES,None),
                ('Validated','Pending Team Lead Review',ROLES,None),('Rework Required','Pending Validation',ROLES,None),
                ('Pending Team Lead Review','Approved',ROLES[:3],None),('Transferred to Quality','Quality In Progress',ROLES,'quality'),
                ('Quality In Progress','Quality Qualified',ROLES,'quality'),('Quality In Progress','Quality Disqualified',ROLES,'quality'),
                ('Quality In Progress','Quality TBD',ROLES,'quality'),('Quality TBD','Quality In Progress',ROLES,'quality'),
                ('Transferred to Delivery','Delivery Approved',ROLES[:3],'delivery'),('Delivery Approved','Delivered',ROLES,'delivery')]
            for i,(old,new,roles,dept) in enumerate(transitions):
                for j,role in enumerate(roles):
                    db.execute("INSERT OR IGNORE INTO team_transitions VALUES(?,?,?,?,?,1)",(f'{i}-{j}',old,new,role,dept))
            db.execute("INSERT INTO team_migrations(version) VALUES(1)")
        if not db.execute('SELECT 1 FROM team_migrations WHERE version=2').fetchone():
            db.execute('ALTER TABLE team_leads ADD COLUMN original_department_id TEXT REFERENCES team_departments(id)')
            db.execute('UPDATE team_leads SET original_department_id=department_id WHERE owner_id IS NOT NULL')
            db.execute('INSERT INTO team_migrations(version) VALUES(2)')
        if not db.execute('SELECT 1 FROM team_migrations WHERE version=3').fetchone():
            db.execute('ALTER TABLE team_leads ADD COLUMN validation_resume_state TEXT')
            for ident,dept,field,access in [('delivery-view','delivery','*','Read Only'),('delivery-approval','delivery','@Approval','Approve'),('delivery-fields','delivery','@Delivery','Edit'),('quality-fields','quality','@Quality','Edit')]:
                db.execute('INSERT OR IGNORE INTO team_permissions(id,department_id,field,access) VALUES(?,?,?,?)',(ident,dept,field,access))
            db.execute('INSERT INTO team_migrations(version) VALUES(3)')
        db.execute('INSERT OR IGNORE INTO team_migrations(version) VALUES(4)')
        db.commit()

