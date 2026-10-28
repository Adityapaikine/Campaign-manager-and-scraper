import json
import sqlite3
import uuid
import pytest
from tests.test_team_service import team,call,commit,record,selected
from app.team.access import ServiceError
from app.team.legacy import adopt_workspaces
from app.core.workspace_store import WorkspaceStore
from app.team.schema import transaction


def test_atomic_sheet_commit_recovery_and_optimistic_sheet_conflict(team):
    sid=call(team,'a','sheet_create',campaign_id='C1',name='Recovery')['id']
    call(team,'a','sheet_save',sheet_id=sid,version=1,payload={'records':[record(43)]})
    key=str(uuid.uuid4()); args={'campaign_id':'C1','records':[record(43)],'sheet_id':sid,'request_key':key}
    first=call(team,'a','commit',**args); assert len(first['committed'])==1
    assert call(team,'a','commit',**args)==first
    assert call(team,'a','sheet_load',sheet_id=sid)['payload']['records']==[]
    with pytest.raises(ServiceError):call(team,'a','sheet_save',sheet_id=sid,version=2,payload={'records':[record(43)]})
    assert call(team,'a','validate_leads',selection=selected(team,'a',first['committed'][0]['id']))[0]['category']=='Valid'


def test_configured_duplicate_priority_caps_and_possible_review(team):
    config={'require_tal_match':False,'duplicate_keys':['email'],'domain_cap_default':1}
    call(team,'admin','campaign_save',campaign_id='C1',campaign_name='One',config=config,version=1)
    first=commit(team,'a',51); assert len(first['committed'])==1
    assert commit(team,'b',52)['summary']=={'Invalid':1}
    changed=record(51); changed['Business Email ID']='another@acme.example'
    result=call(team,'b','validate_draft',campaign_id='C1',records=[changed])
    assert result['summary']=={'Pending Review':1}
    assert first['committed'][0]['id'] not in json.dumps(result)
    invalid={**config,'start_date':'not a date'}
    with pytest.raises(ServiceError):call(team,'admin','campaign_save',campaign_id='C1',campaign_name='One',config=invalid,version=2)


def test_transferred_team_monitoring_does_not_allow_changes(team):
    lid=commit(team,'a',60)['committed'][0]['id']
    call(team,'a','transition',selection=selected(team,'a',lid),state='Pending Team Lead Review')
    call(team,'lead','transition',selection=selected(team,'lead',lid),state='Approved')
    call(team,'lead','transfer',selection=selected(team,'lead',lid),route_id='1')
    assert call(team,'lead','leads',campaign_id='C1',view='transferred')['total']==1
    assert call(team,'lead','leads',campaign_id='C1',view='incoming')['total']==0
    assert call(team,'qualitylead','leads',campaign_id='C1',view='incoming')['total']==1
    assert call(team,'otherlead','leads',campaign_id='C1',view='transferred')['total']==0
    with pytest.raises(ServiceError):call(team,'lead','lead_edit',lead_id=lid,version=4,changes={'Job Title':'Changed'})
    assert call(team,'quality','leads',campaign_id='C1')['total']==0


def test_legacy_adoption_preserves_records_formulas_and_unknown_ownership(team,tmp_path):
    store=WorkspaceStore(tmp_path/'legacy'); source=store.key('C1')
    payload={'records':[record(80),record(80)],'custom_columns':['Calc'],'formulas':[{'row':0,'column':'Calc','expression':'=1+2'}]}
    store.save(source,payload)
    first=adopt_workspaces(team[0].path,store.folder); assert first['leads']==2 and first['duplicate_rows']==1
    assert adopt_workspaces(team[0].path,store.folder)['leads']==0
    assert call(team,'a','leads',campaign_id='C1')['total']==0
    rows=call(team,'admin','leads',campaign_id='C1')['rows']; assert len(rows)==2 and all(r['owner_id'] is None for r in rows)
    with transaction(team[0].path,False) as db:
        archived=json.loads(db.execute('SELECT payload_json FROM team_legacy_payloads').fetchone()[0]); assert archived['formulas']==payload['formulas']
    store.save(source,{**payload,'records':[record(81)]})
    with pytest.raises(ValueError):adopt_workspaces(team[0].path,store.folder)
    assert call(team,'admin','leads',campaign_id='C1')['total']==2


def test_hidden_formula_inputs_and_unread_counts(team):
    sid=call(team,'a','sheet_create',campaign_id='C1')['id']
    payload={'records':[{**record(90),'Calc':'person90@acme.example'}],'custom_columns':['Calc'],
        'headers':['Business Email ID','Calc'],'formulas':[{'row':0,'column':'Calc','expression':'=[Business Email ID]'}]}
    call(team,'a','sheet_save',sheet_id=sid,version=1,payload=payload)
    call(team,'admin','policy_save',kind='permissions',values={'department_id':'operations','role':'Employee','campaign_id':'C1','field':'Business Email ID','access':'Hidden'})
    loaded=call(team,'a','sheet_load',sheet_id=sid)
    assert loaded['payload']['records'][0]['Calc']=='-'
    assert loaded['payload']['formulas']==[]
    exported=call(team,'a','export_draft',campaign_id='C1',sheet_id=sid,row_ids=loaded['payload']['row_ids'])
    assert exported[0]['Calc']=='-' and 'Business Email ID' not in exported[0]
    with transaction(team[0].path) as db:
        db.executemany("INSERT INTO team_notifications(user_id,event,campaign_id,text) VALUES(?,'Test','C1','A notification')",[(team[2]['a']['id'],)]*250)
    result=call(team,'a','notifications',event='Test'); assert result['unread']==250 and len(result['rows'])==200


def test_quality_edit_revalidation_and_delivery_flow(team):
    lid=commit(team,'a',101)['committed'][0]['id']
    call(team,'a','transition',selection=selected(team,'a',lid),state='Pending Team Lead Review')
    call(team,'lead','transition',selection=selected(team,'lead',lid),state='Approved')
    call(team,'lead','transfer',selection=selected(team,'lead',lid),route_id='1')
    call(team,'qualitylead','assign',selection=selected(team,'qualitylead',lid),user_ids=[team[2]['quality']['id']])
    call(team,'quality','transition',selection=selected(team,'quality',lid),state='Quality In Progress')
    lead=call(team,'quality','lead',lead_id=lid)
    call(team,'quality','lead_edit',lead_id=lid,version=lead['version'],changes={'Job Title':'Marketing Director'})
    call(team,'quality','validate_leads',selection=selected(team,'quality',lid))
    assert call(team,'quality','lead',lead_id=lid)['state']=='Quality In Progress'
    call(team,'quality','transition',selection=selected(team,'quality',lid),state='Quality Qualified')
    call(team,'qualitylead','transfer',selection=selected(team,'qualitylead',lid),route_id='2')
    assert call(team,'admin','dashboard')[0]['qualified']==1
    call(team,'deliverylead','assign',selection=selected(team,'deliverylead',lid),user_ids=[team[2]['delivery']['id']])
    call(team,'deliverylead','transition',selection=selected(team,'deliverylead',lid),state='Delivery Approved')
    call(team,'delivery','transition',selection=selected(team,'delivery',lid),state='Delivered')
    assert call(team,'delivery','report',campaign_id='C1')['states']=={'Delivered':1}
    assert call(team,'admin','dashboard')[0]['qualified']==1
    assert call(team,'a','lead',lead_id=lid)['owner_id']==team[2]['a']['id']
    with transaction(team[0].path) as db:db.execute('UPDATE team_leads SET created_at=? WHERE id=?',('2026-01-02 23:59:59',lid))
    assert call(team,'a','report_export',campaign_id='C1',date_from='2026-01-02',date_to='2026-01-02')['total']==1


def test_recovery_export_permission_and_account_session_expiry(team):
    sid=call(team,'a','sheet_create',campaign_id='C1')['id']
    saved=call(team,'a','sheet_save',sheet_id=sid,version=1,payload={'records':[record(120)]})
    call(team,'admin','policy_save',kind='permissions',values={'department_id':'operations','role':'Employee','campaign_id':'C1','field':'Business Email ID','access':'Export'})
    rows=call(team,'a','export_draft',campaign_id='C1',sheet_id=sid,row_ids=saved['row_ids'])
    assert rows[0]['Business Email ID']=='person120@acme.example'
    with pytest.raises(ServiceError):call(team,'b','export_draft',campaign_id='C1',sheet_id=sid,row_ids=saved['row_ids'])
    copy=call(team,'a','sheet_recovery',campaign_id='C1',payload={'records':[record(121)|{'Business Email ID':''}]})
    assert copy['id']!=sid and len(call(team,'a','sheets',campaign_id='C1'))==2
    with transaction(team[0].path) as db:db.execute('UPDATE team_sessions SET expires=0 WHERE user_id=?',(team[2]['a']['id'],))
    with pytest.raises(ServiceError) as error:call(team,'a','me')
    assert error.value.status==401


def test_campaign_package_rules_and_unsafe_archive_rejection(team):
    import io,base64,zipfile
    def archive(name):
        output=io.BytesIO()
        with zipfile.ZipFile(output,'w') as z:z.writestr(name,'Company Name,Domain\nAcme,acme.example\n')
        return base64.b64encode(output.getvalue()).decode()
    safe=archive('777 - Example/TAL.csv')
    with pytest.raises(ServiceError):call(team,'a','campaign_package',filename='Example.zip',content=safe)
    result=call(team,'admin','campaign_package',filename='Example.zip',content=safe)
    assert result['campaign_id']=='777'
    rules=call(team,'admin','campaign_rules',campaign_id='777'); assert rules
    call(team,'admin','campaign_rules',campaign_id='777',index=0,status='Confirmed')
    with pytest.raises(ServiceError):call(team,'admin','campaign_package',filename='Evil.zip',content=archive('../outside.csv'))
    assert call(team,'a','leads',campaign_id='C1')['total']==0
