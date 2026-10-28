"""Authorization primitives used inside every service transaction."""
import json
from contextvars import ContextVar
from app.constants import STANDARD_HEADERS

class ServiceError(Exception):
    def __init__(self, message, status=400): super().__init__(message); self.status=status

def require(condition, message="This operation is not permitted.", status=403):
    if not condition: raise ServiceError(message,status)

def campaign_access(db, user, cid):
    require(db.execute("SELECT 1 FROM campaign_profiles WHERE campaign_id=?",(cid,)).fetchone(),"Campaign unavailable.",404)
    require(user['role']=='Super User' or db.execute("SELECT 1 FROM team_campaign_users WHERE campaign_id=? AND user_id=?",(cid,user['id'])).fetchone())

def scope_sql(user, alias='l'):
    if user['role']=='Super User': return '1=1',[]
    prefix=f"EXISTS(SELECT 1 FROM team_campaign_users cu WHERE cu.campaign_id={alias}.campaign_id AND cu.user_id=?)"
    args=[user['id']]
    if user['role']=='Department Manager':
        return prefix+f" AND ({alias}.department_id=? OR EXISTS(SELECT 1 FROM team_transfers tr WHERE tr.lead_id={alias}.id AND tr.from_department=?))",args+[user['department_id'],user['department_id']]
    if user['role']=='Team Lead':
        return prefix+f" AND (({alias}.department_id=? AND ({alias}.assigned_id IS NULL OR {alias}.assigned_id=? OR {alias}.assigned_id IN (SELECT id FROM team_users WHERE team_lead_id=? AND department_id=?))) OR EXISTS(SELECT 1 FROM team_transfers tr WHERE tr.lead_id={alias}.id AND tr.from_department=? AND (tr.transferred_by=? OR tr.previous_assignee IN (SELECT id FROM team_users WHERE team_lead_id=? AND department_id=?))))",args+[user['department_id'],user['id'],user['id'],user['department_id'],user['department_id'],user['id'],user['id'],user['department_id']]
    return prefix+f" AND ({alias}.owner_id=? OR {alias}.assigned_id=?)",args+[user['id'],user['id']]

def get_lead(db,user,lead_id,*,edit=False):
    clause,args=scope_sql(user)
    row=db.execute(f"SELECT l.* FROM team_leads l WHERE l.id=? AND ({clause})",[lead_id,*args]).fetchone()
    require(row is not None,"Lead unavailable.",404)
    if edit:
        require(not row['archived'],"Archived leads cannot be edited.",409)
        require(user['role']=='Super User' or row['department_id']==user['department_id'])
        require(user['role'] in ('Super User','Department Manager','Team Lead') or row['assigned_id']==user['id'])
        require(user['role']=='Super User' or row['state'] not in ('Approved','Quality Qualified','Delivery Approved','Delivered'),"This workflow stage is locked; return the lead for rework first.",409)
    return row

def field_category(field):
    if field.startswith(('QA ','Primary Reason','Audited','Validation')): return '@Quality'
    if field.startswith('Delivery'): return '@Delivery'
    if field in ('Company Name','Company Website','Industry','Company Size','Revenue','SIC Code','NAICS Code','Industry Link','Revenue Link','SIC/NAICS Code Link'): return '@Company'
    return '@Prospect'

permission_cache=ContextVar('team_permission_cache',default=None)

def field_access(db,user,cid,field):
    cache=permission_cache.get(); key=(user['id'],cid,field)
    if cache is not None and key in cache:return cache[key]
    value=_field_access(db,user,cid,field)
    if cache is not None:cache[key]=value
    return value

def _field_access(db,user,cid,field):
    if user['role']=='Super User': return 'Edit'
    rules=db.execute("""SELECT * FROM team_permissions WHERE (department_id IS NULL OR department_id=?)
       AND (role IS NULL OR role=?) AND (campaign_id IS NULL OR campaign_id=?) AND field IN (?,?, '*')""",
       (user['department_id'],user['role'],cid,field,field_category(field))).fetchall()
    if rules:
        # More specific rules win; equally specific Hidden wins rather than grants.
        rank={'Edit':0,'Approve':1,'Export':2,'Read Only':3,'Hidden':4}
        rule=max(rules,key=lambda r:(int(r['field']==field)*32+int(r['field']==field_category(field))*16+int(r['campaign_id'] is not None)*8+int(r['role'] is not None)*4+int(r['department_id'] is not None)*2,rank[r['access']]))
        return rule['access']
    if field_category(field)=='@Quality': return 'Read Only'
    return 'Edit'

def fields_out(db,user,cid,record,export=False):
    allowed={'Edit','Approve','Export'} if export else {'Edit','Approve','Export','Read Only'}
    return {k:v for k,v in record.items() if field_access(db,user,cid,k) in allowed}

def fields_in(db,user,cid,record):
    require(isinstance(record,dict) and len(record)<=250,'Invalid lead data.',400)
    protected={'Lead ID','CID','Campaign ID','Team Lead','Owner ID','Department','Current Department','Original Owner','Assigned User','Workflow Status','Transfer Status'}
    output={}
    for field,value in record.items():
        require(isinstance(field,str) and 0<len(field)<=120,'Invalid field name.',400)
        if field in protected: continue
        require(isinstance(value,(str,int,float,bool)) or value is None,'Invalid field value.',400)
        text='' if value is None else str(value)
        require(len(text)<=32767,'A field exceeds the maximum length.',400)
        if text.strip() not in {'','-'}:
            require(field_access(db,user,cid,field)=='Edit',f'You cannot edit {field}.')
        output[field]=text
    return output

def check_version(row,version):
    require(isinstance(version,int) and row['version']==version,'This record changed in another session. Refresh before trying again.',409)

def public_user(row):
    return {k:row[k] for k in ('id','full_name','username','email','department_id','role','manager_id','team_lead_id','active','created_at','last_login')}

def audit(db,user,event,resource=None,outcome='success',details=None):
    db.execute("INSERT INTO team_audit(user_id,event,resource,outcome,details_json) VALUES(?,?,?,?,?)",
               (user['id'] if user else None,event,resource,outcome,json.dumps(details or {})))

def history(db,user,lead,event,field,old,new):
    db.execute("INSERT INTO team_history(lead_id,user_id,campaign_id,department_id,event,field,old_json,new_json) VALUES(?,?,?,?,?,?,?,?)",
               (lead['id'],user['id'],lead['campaign_id'],lead['department_id'],event,field,json.dumps(old),json.dumps(new)))

def notify(db,user_id,event,cid,lead_id=None,text='Workflow updated'):
    if user_id: db.execute("INSERT INTO team_notifications(user_id,event,campaign_id,lead_id,text) VALUES(?,?,?,?,?)",(user_id,event,cid,lead_id,text))
