from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import uuid
import pytest
from app.team.service import Service
from app.team.access import ServiceError
from app.team.schema import transaction, migrate

PASSWORD='Testing-passphrase-482!'

def record(n=1):
    return {'First Name':'Person'+str(n),'Last Name':'Test','Company Name':'Acme',
            'Company Website':'acme.example','Business Email ID':f'person{n}@acme.example',
            'Prospect LinkedIn Link':f'https://www.linkedin.com/in/person-{n}'}

@pytest.fixture
def team(tmp_path):
    service=Service(tmp_path/'shared.sqlite3'); service.bootstrap('Administrator','admin','admin@example.com',PASSWORD)
    admin=service.login('admin',PASSWORD)['token']; users={}; tokens={'admin':admin}
    service.call(admin,'campaign_save',{'campaign_id':'C1','campaign_name':'Campaign 1','config':{'require_tal_match':False}})
    service.call(admin,'campaign_save',{'campaign_id':'C2','campaign_name':'Campaign 2','config':{'require_tal_match':False}})
    for name,role,dept,supervisor in [('manager','Department Manager','operations',None),('lead','Team Lead','operations',None),
       ('otherlead','Team Lead','operations',None),('a','Employee','operations','lead'),('b','Employee','operations','lead'),
       ('other','Employee','operations','otherlead'),('qualitylead','Team Lead','quality',None),('quality','Employee','quality','qualitylead'),
       ('deliverylead','Team Lead','delivery',None),('delivery','Employee','delivery','deliverylead')]:
        user=service.call(admin,'user_save',{'full_name':name,'username':name,'email':name+'@example.com','password':PASSWORD,
            'role':role,'department_id':dept,'team_lead_id':users[supervisor]['id'] if supervisor else None,
            'manager_id':users['manager']['id'] if dept=='operations' and name!='manager' else None})
        users[name]=user; tokens[name]=service.login(name,PASSWORD)['token']
        service.call(admin,'campaign_assign',{'campaign_id':'C1','user_ids':[user['id']]})
    return service,tokens,users

def call(team,who,op,**args): return team[0].call(team[1][who],op,args)
def commit(team,who,n=1,**kw): return call(team,who,'commit',campaign_id='C1',records=[record(n)],request_key=str(uuid.uuid4()),**kw)
def selected(team,who,lid):
    lead=call(team,who,'lead',lead_id=lid); return [{'id':lid,'version':lead['version']}]

def test_auth_sessions_passwords_deactivation_and_last_superuser(team):
    s,t,u=team
    with transaction(s.path,False) as db:
        hashes=[r[0] for r in db.execute('SELECT password_hash FROM team_users')]
        assert all(h.startswith('$argon2id$') and PASSWORD not in h for h in hashes)
    with pytest.raises(ServiceError): s.login('a','wrong')
    call(team,'admin','user_save',**{k:u['a'][k] for k in ('id','full_name','username','email','role','department_id','manager_id','team_lead_id')},active=False)
    with pytest.raises(ServiceError): call(team,'a','me')
    with pytest.raises(ServiceError): s.login('a',PASSWORD)
    admin=call(team,'admin','me')
    with pytest.raises(ServiceError): call(team,'admin','user_save',**{k:admin[k] for k in ('id','full_name','username','email','role')},active=False)
    call(team,'b','logout')
    with pytest.raises(ServiceError): call(team,'b','me')

def test_cross_user_campaign_and_team_scope(team):
    one=commit(team,'a')['committed'][0]['id']; two=commit(team,'b',2)['committed'][0]['id']; commit(team,'other',3)
    assert call(team,'a','leads',campaign_id='C1')['total']==1
    assert call(team,'lead','leads',campaign_id='C1')['total']==2
    assert call(team,'otherlead','leads',campaign_id='C1')['total']==1
    assert call(team,'manager','leads',campaign_id='C1')['total']==3
    assert call(team,'qualitylead','leads',campaign_id='C1')['total']==0
    for op,args in [('lead',{'lead_id':one}),('history',{'lead_id':one}),('export',{'lead_ids':[one]}),('lead_edit',{'lead_id':one,'version':1,'changes':{'First Name':'hacked'}})]:
        with pytest.raises(ServiceError): call(team,'b',op,**args)
    with pytest.raises(ServiceError): call(team,'a','leads',campaign_id='C2')

def test_duplicates_cross_users_and_private_sheets(team):
    lid=commit(team,'a')['committed'][0]['id']
    result=commit(team,'b'); assert result['committed']==[] and result['summary']=={'Duplicate':1}
    assert lid not in json.dumps(result) and team[2]['a']['id'] not in json.dumps(result)
    sheet=call(team,'a','sheet_create',campaign_id='C1',name='Private')
    call(team,'a','sheet_save',sheet_id=sheet['id'],version=1,payload={'records':[record(2)]})
    with pytest.raises(ServiceError): call(team,'b','sheet_load',sheet_id=sheet['id'])
    assert commit(team,'b',2)['summary']=={'Duplicate':1}
    assert call(team,'lead','sheets',campaign_id='C1')==[]

def test_concurrent_duplicate_commits_and_idempotency(team):
    key=str(uuid.uuid4())
    def run(who): return call(team,who,'commit',campaign_id='C1',records=[record(8)],request_key=key)
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,['a','b']))
    assert sum(len(r['committed']) for r in results)==1
    winner='a' if results[0]['committed'] else 'b'
    repeat=run(winner); assert repeat['committed']==next(r['committed'] for r in results if r['committed'])
    assert call(team,'admin','report',campaign_id='C1')['total']==1
    with pytest.raises(ServiceError): call(team,winner,'commit',campaign_id='C1',records=[record(9)],request_key=key)

def test_field_permissions_export_history_and_search(team):
    lid=commit(team,'a')['committed'][0]['id']
    call(team,'admin','policy_save',kind='permissions',values={'department_id':'operations','role':'Employee','campaign_id':'C1','field':'Business Email ID','access':'Hidden'})
    assert 'Business Email ID' not in call(team,'a','lead',lead_id=lid)['record']
    assert 'Business Email ID' not in call(team,'a','export',lead_ids=[lid])[0]
    assert 'person1@' not in json.dumps(call(team,'a','history',lead_id=lid))
    assert call(team,'a','leads',campaign_id='C1',search='person1@')['total']==0
    with pytest.raises(ServiceError): call(team,'a','lead_edit',lead_id=lid,version=1,changes={'Business Email ID':'new@acme.example'})

def test_workflow_transfer_assignment_rework_and_original_identity(team):
    lid=commit(team,'a')['committed'][0]['id']
    call(team,'a','transition',selection=selected(team,'a',lid),state='Pending Team Lead Review')
    call(team,'lead','transition',selection=selected(team,'lead',lid),state='Approved')
    with pytest.raises(ServiceError): call(team,'a','transfer',selection=selected(team,'a',lid),route_id='1')
    old=selected(team,'lead',lid)
    call(team,'lead','transfer',selection=old,route_id='1',note='Reviewed')
    with pytest.raises(ServiceError): call(team,'lead','transfer',selection=old,route_id='1')
    assert call(team,'qualitylead','leads',campaign_id='C1',view='incoming')['total']==1
    assert call(team,'quality','leads',campaign_id='C1')['total']==0
    assert call(team,'deliverylead','leads',campaign_id='C1')['total']==0
    call(team,'qualitylead','assign',selection=selected(team,'qualitylead',lid),user_ids=[team[2]['quality']['id']])
    assert call(team,'quality','lead',lead_id=lid)['owner_id']==team[2]['a']['id']
    call(team,'quality','rework',selection=selected(team,'quality',lid),reason_id='2',comment='Please correct')
    lead=call(team,'a','lead',lead_id=lid)
    assert lead['state']=='Rework Required' and lead['assigned_id']==team[2]['a']['id']
    assert len(call(team,'a','transfer_history',lead_id=lid))==2
    assert call(team,'a','notifications')['unread']>0

def test_optimistic_conflicts_and_safe_bulk_rollback(team):
    one=commit(team,'a')['committed'][0]['id']; two=commit(team,'b',2)['committed'][0]['id']
    version=selected(team,'a',one)[0]['version']
    call(team,'a','lead_edit',lead_id=one,version=version,changes={'Job Title':'Engineer'})
    with pytest.raises(ServiceError): call(team,'a','lead_edit',lead_id=one,version=version,changes={'Job Title':'Manager'})
    with pytest.raises(ServiceError): call(team,'lead','assign',selection=[*selected(team,'lead',one),{'id':two,'version':999}],user_ids=[team[2]['a']['id']])
    assert call(team,'b','lead',lead_id=two)['assigned_id']==team[2]['b']['id']

def test_sheets_persist_independently_and_delete_keeps_committed_leads(team):
    sheet=call(team,'a','sheet_create',campaign_id='C1',name='One')
    call(team,'a','sheet_save',sheet_id=sheet['id'],version=1,payload={'records':[record(20)],'custom_columns':['Calc'],'formulas':[]})
    dup=call(team,'a','sheet_create',campaign_id='C1',name='Two',duplicate_id=sheet['id'])
    call(team,'a','sheet_delete',sheet_id=dup['id'],version=1)
    commit(team,'a',20,sheet_id=sheet['id'])
    reloaded=call(team,'a','sheet_load',sheet_id=sheet['id'])
    assert reloaded['payload']['records']==[]
    call(team,'a','sheet_delete',sheet_id=sheet['id'],version=reloaded['version'])
    assert call(team,'a','leads',campaign_id='C1')['total']==1
    team[1]['a']=team[0].login('a',PASSWORD)['token']
    assert call(team,'a','sheets',campaign_id='C1')==[]

def test_migration_preserves_existing_tables_and_is_repeatable(tmp_path):
    p=tmp_path/'existing.sqlite3'
    with sqlite3.connect(p) as db:
        db.execute('CREATE TABLE historical(value TEXT)'); db.execute("INSERT INTO historical VALUES('preserved')")
    migrate(p); migrate(p)
    with sqlite3.connect(p) as db:
        assert db.execute('SELECT value FROM historical').fetchone()[0]=='preserved'
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM team_migrations').fetchone()[0]==4
