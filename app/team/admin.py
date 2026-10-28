import json
import uuid
from argon2 import PasswordHasher
from app.team.schema import ROLES, STATES
from app.team.access import require, public_user, audit, history, campaign_access, notify, ServiceError

PASSWORDS=PasswordHasher()

def validate_password(value):
    require(isinstance(value,str) and 12<=len(value)<=256,'Use a password of 12–256 characters.',400)
    return value

def password_hash(value):
    validate_password(value)
    return PASSWORDS.hash(value)

class Administration:
    def op_directory(self,db,user):
        if user['role']=='Super User': users=db.execute('SELECT * FROM team_users').fetchall()
        elif user['role']=='Department Manager': users=db.execute('SELECT * FROM team_users WHERE department_id=?',(user['department_id'],)).fetchall()
        elif user['role']=='Team Lead': users=db.execute('SELECT * FROM team_users WHERE id=? OR (team_lead_id=? AND department_id=?)',(user['id'],user['id'],user['department_id'])).fetchall()
        else: users=[user]
        return {'users':[public_user(u) for u in users], 'departments':[dict(r) for r in db.execute('SELECT * FROM team_departments')], 'roles':ROLES}

    def op_user_save(self,db,user,full_name,username,email,role,department_id=None,manager_id=None,team_lead_id=None,active=True,id=None,password=None):
        require(user['role']=='Super User')
        require(role in ROLES and all(isinstance(v,str) and 0<len(v.strip())<=150 for v in (full_name,username,email)),'Check user details.',400)
        require('@' in email and not any(c.isspace() for c in username),'Enter a valid username and email.',400)
        old=db.execute('SELECT * FROM team_users WHERE id=?',(id,)).fetchone() if id else None
        require(not id or old is not None,'User unavailable.',404)
        uid=id or str(uuid.uuid4())
        require(not db.execute('SELECT 1 FROM team_users WHERE id<>? AND (username=? COLLATE NOCASE OR email=? COLLATE NOCASE)',(uid,email.strip(),username.strip())).fetchone(),'Username or email overlaps an existing sign-in identity.',409)
        require(uid not in {manager_id,team_lead_id},'A user cannot report to themselves.',400)
        if role!='Super User': require(db.execute('SELECT 1 FROM team_departments WHERE id=? AND active=1',(department_id,)).fetchone(),'Choose an active department.',400)
        for supervisor,wanted in ((manager_id,'Department Manager'),(team_lead_id,'Team Lead')):
            if supervisor:
                s=db.execute('SELECT * FROM team_users WHERE id=? AND active=1',(supervisor,)).fetchone()
                require(s and s['role']==wanted and s['department_id']==department_id,'Reporting relationships must use an active supervisor in the same department.',400)
                if wanted=='Team Lead' and manager_id: require(s['manager_id']==manager_id,'Team Lead must report to the selected manager.',400)
        if old and old['role']=='Super User' and (not active or role!='Super User'):
            require(db.execute("SELECT count(*) FROM team_users WHERE role='Super User' AND active=1 AND id<>?",(uid,)).fetchone()[0]>0,'Keep at least one active Super User.',409)
        if old and (old['department_id']!=department_id or old['role']!=role):
            require(not db.execute('SELECT 1 FROM team_users WHERE (manager_id=? OR team_lead_id=?) AND active=1',(uid,uid)).fetchone(),'Reassign active reports before changing this supervisor role or department.',409)
        hashed=password_hash(password) if password else (old['password_hash'] if old else None)
        require(hashed,'A password is required for a new user.',400)
        db.execute('''INSERT INTO team_users(id,full_name,username,email,password_hash,department_id,role,manager_id,team_lead_id,active)
          VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET full_name=excluded.full_name,username=excluded.username,email=excluded.email,
          password_hash=excluded.password_hash,department_id=excluded.department_id,role=excluded.role,manager_id=excluded.manager_id,
          team_lead_id=excluded.team_lead_id,active=excluded.active''',
          (uid,full_name.strip(),username.strip(),email.strip().lower(),hashed,department_id,role,manager_id,team_lead_id,int(bool(active))))
        if old:
            db.execute('DELETE FROM team_sessions WHERE user_id=?',(uid,))
            new_team=uid if role=='Team Lead' else team_lead_id
            for lead in db.execute('SELECT * FROM team_leads WHERE assigned_id=? AND department_id=?',(uid,department_id)).fetchall():
                if lead['team_lead_id']!=new_team:
                    history(db,user,lead,'reporting-change','team_lead_id',lead['team_lead_id'],new_team)
                    db.execute('UPDATE team_leads SET team_lead_id=?,version=version+1,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(new_team,user['id'],lead['id']))
            # Existing work is not silently reassigned when an account is disabled.
        audit(db,user,'user-save',uid,details={'role':role,'department_id':department_id,'active':bool(active)})
        return public_user(db.execute('SELECT * FROM team_users WHERE id=?',(uid,)).fetchone())

    def op_department_save(self,db,user,name,id=None,active=True):
        require(user['role']=='Super User')
        require(isinstance(name,str) and 1<=len(name.strip())<=100,'Enter a department name.',400)
        uid=id or str(uuid.uuid4())
        if not active: require(not db.execute('SELECT 1 FROM team_users WHERE department_id=? AND active=1',(uid,)).fetchone(),'Deactivate or move its users first.',409)
        db.execute('INSERT INTO team_departments VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,active=excluded.active',(uid,name.strip(),int(bool(active))))
        audit(db,user,'department-save',uid)
        return {'id':uid}

    def op_campaigns(self,db,user):
        clause='1=1' if user['role']=='Super User' else 'EXISTS(SELECT 1 FROM team_campaign_users cu WHERE cu.campaign_id=p.campaign_id AND cu.user_id=?)'
        args=[] if user['role']=='Super User' else [user['id']]
        result=[]
        for r in db.execute(f'SELECT p.campaign_id,p.campaign_name,c.config_json,c.version FROM campaign_profiles p LEFT JOIN team_campaign_config c ON c.campaign_id=p.campaign_id WHERE {clause} ORDER BY p.campaign_name',args):
            item=dict(r); item['config']=json.loads(item.pop('config_json') or '{}'); item['version']=item['version'] or 0
            if user['role']!='Super User':
                item['config'].pop('tal',None); item['config'].pop('suppression',None)
            result.append(item)
        return result

    def op_campaign_save(self,db,user,campaign_id,campaign_name,config,version=0):
        require(user['role']=='Super User')
        require(isinstance(campaign_id,str) and 1<=len(campaign_id)<=80 and isinstance(campaign_name,str) and 1<=len(campaign_name)<=200,'Enter campaign name and ID.',400)
        require(isinstance(config,dict),'Invalid configuration.',400)
        allowed={'client','departments','required_fields','duplicate_keys','require_tal_match','enable_suppression','tal','suppression','allocation','start_date','end_date','delivered','status','review_required','domain_caps','domain_cap_default'}
        require(set(config)<=allowed,'Unknown campaign configuration.',400)
        for key in ('tal','suppression'): require(isinstance(config.get(key,[]),list) and len(config.get(key,[]))<=100000,'Invalid reference list.',400)
        from app.core.campaign_dashboard import parse_date, count_value
        for key in ('allocation','delivered'):
            if config.get(key) is not None: require(count_value(config[key]) is not None,'Counts must be non-negative whole numbers.',400)
        start,end=parse_date(config.get('start_date')),parse_date(config.get('end_date'))
        require(not config.get('start_date') or start is not None,'Invalid start date.',400)
        require(not config.get('end_date') or end is not None,'Invalid end date.',400)
        require(isinstance(config.get('duplicate_keys',[]),list) and set(config.get('duplicate_keys',[]))<={'email','linkedin','person_domain'},'Invalid duplicate keys.',400)
        require(isinstance(config.get('required_fields',[]),list) and all(isinstance(f,str) and 0<len(f)<=120 for f in config.get('required_fields',[])),'Invalid mandatory fields.',400)
        require(isinstance(config.get('departments',[]),list) and all(db.execute('SELECT 1 FROM team_departments WHERE id=? AND active=1',(d,)).fetchone() for d in config.get('departments',[])),'Invalid campaign departments.',400)
        require(isinstance(config.get('domain_caps',{}),dict) and all(count_value(v) is not None for v in config.get('domain_caps',{}).values()),'Invalid domain caps.',400)
        require(config.get('domain_cap_default') is None or count_value(config['domain_cap_default']) is not None,'Invalid default domain cap.',400)
        require(not(start and end and end<start),'End date cannot precede start date.',400)
        require(config.get('status','Running') in ('Running','Paused','Closed','Archived'),'Invalid campaign status.',400)
        old=db.execute('SELECT * FROM team_campaign_config WHERE campaign_id=?',(campaign_id,)).fetchone()
        require((old['version'] if old else 0)==version,'Campaign configuration changed. Refresh first.',409)
        db.execute("INSERT INTO campaign_profiles(campaign_id,campaign_name,source_root,payload_json) VALUES(?,?,'','{}') ON CONFLICT(campaign_id) DO UPDATE SET campaign_name=excluded.campaign_name,updated_at=CURRENT_TIMESTAMP",(campaign_id,campaign_name))
        db.execute('INSERT INTO team_campaign_config VALUES(?,?,?) ON CONFLICT(campaign_id) DO UPDATE SET version=excluded.version,config_json=excluded.config_json',(campaign_id,version+1,json.dumps(config)))
        if old and json.loads(old['config_json']).get('duplicate_keys')!=config.get('duplicate_keys'):
            from app.team.leads import keys_for
            db.execute('DELETE FROM team_lead_keys WHERE campaign_id=?',(campaign_id,))
            for lead in db.execute('SELECT id,record_json FROM team_leads WHERE campaign_id=?',(campaign_id,)).fetchall():
                for kind,value in keys_for(json.loads(lead['record_json']),config):
                    db.execute('INSERT INTO team_lead_keys VALUES(?,?,?,?)',(campaign_id,kind,value,lead['id']))
            for sheet in db.execute('SELECT id,payload_json FROM team_sheets WHERE campaign_id=? AND archived=0',(campaign_id,)).fetchall():
                self._draft_index(db,sheet['id'],campaign_id,json.loads(sheet['payload_json']))
        audit(db,user,'campaign-configuration',campaign_id,details={'old':json.loads(old['config_json']) if old else {},'new':config})
        return {'version':version+1}

    def op_campaign_assign(self,db,user,campaign_id,user_ids,remove=False):
        require(user['role']=='Super User')
        campaign_access(db,user,campaign_id)
        require(isinstance(user_ids,list) and len(user_ids)<=1000,'Invalid user selection.',400)
        for uid in set(user_ids):
            require(db.execute('SELECT 1 FROM team_users WHERE id=?',(uid,)).fetchone(),'User unavailable.',404)
            if remove: db.execute('DELETE FROM team_campaign_users WHERE campaign_id=? AND user_id=?',(campaign_id,uid))
            else: db.execute('INSERT OR IGNORE INTO team_campaign_users VALUES(?,?)',(campaign_id,uid))
            notify(db,uid,'Campaign assignment changed',campaign_id,text='Your campaign assignment changed.')
        audit(db,user,'campaign-assign',campaign_id,details={'users':user_ids,'removed':remove})
        return {'updated':len(set(user_ids))}

    def op_policy(self,db,user):
        require(user['role']=='Super User')
        return {name:[dict(r) for r in db.execute('SELECT * FROM team_'+name)] for name in ('permissions','routes','reasons','transitions')}

    def op_policy_save(self,db,user,kind,values,id=None):
        require(user['role']=='Super User')
        fields={'permissions':('department_id','role','campaign_id','field','access'),
                'routes':('campaign_id','from_department','to_department','required_state','arrival_state','active'),
                'reasons':('name','active'),'transitions':('from_state','to_state','role','department_id','active')}
        require(kind in fields and isinstance(values,dict) and set(values)==set(fields[kind]),'Invalid policy.',400)
        if kind=='permissions': require(values['access'] in ('Hidden','Read Only','Edit','Approve','Export') and isinstance(values['field'],str) and 0<len(values['field'])<=120,'Invalid field permission.',400)
        if 'role' in values: require(values['role'] is None or values['role'] in ROLES,'Invalid role.',400)
        for key in ('from_state','to_state','required_state','arrival_state'):
            if key in values: require(isinstance(values[key],str) and 0<len(values[key])<=80,'Invalid workflow state.',400)
        uid=id or str(uuid.uuid4()); names=fields[kind]
        db.execute(f"INSERT INTO team_{kind}(id,{','.join(names)}) VALUES({','.join('?' for _ in range(len(names)+1))}) ON CONFLICT(id) DO UPDATE SET {','.join(f'{k}=excluded.{k}' for k in names)}",[uid,*[values[k] for k in names]])
        audit(db,user,'policy-save',uid,details={'kind':kind,'values':values})
        return {'id':uid}

    def op_audit(self,db,user,offset=0):
        clause,args=('1=1',[]) if user['role']=='Super User' else ('user_id=?',[user['id']])
        return [dict(r) for r in db.execute(f'SELECT * FROM team_audit WHERE {clause} ORDER BY id DESC LIMIT 200 OFFSET ?',(*args,max(0,int(offset))))]

    def op_preferences(self,db,user,key=None,value=None,save=False):
        if save:
            require(isinstance(key,str) and 0<len(key)<=100 and len(json.dumps(value))<=100000,'Invalid preference.',400)
            db.execute('INSERT INTO team_preferences VALUES(?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET value_json=excluded.value_json',(user['id'],key,json.dumps(value)))
        return {r['key']:json.loads(r['value_json']) for r in db.execute('SELECT * FROM team_preferences WHERE user_id=?',(user['id'],))}
