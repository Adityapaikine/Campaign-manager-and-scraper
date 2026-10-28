import hashlib
import json
import uuid
from dataclasses import asdict
from collections import Counter, defaultdict
from app.core.normalizer import normalize_domain
from app.core.domain_cap_engine import DomainCapEngine
from app.constants import STANDARD_HEADERS, MISSING_VALUE
from app.core.duplicate_checker import DuplicateChecker, DuplicateResult
from app.core.validator import ValidationEngine
from app.core.campaign_models import CampaignProfile
from app.core.campaign_activation import build_campaign_validators
from app.core.reference_lists import ReferenceData
from app.core.tal_validator import TALValidator
from app.core.suppression_validator import SuppressionValidator
from app.team.access import (require, campaign_access, scope_sql, get_lead, fields_in, fields_out, field_access,
                             check_version, history, audit, notify, ServiceError)

def config_for(db,cid):
    row=db.execute('SELECT config_json FROM team_campaign_config WHERE campaign_id=?',(cid,)).fetchone()
    return json.loads(row[0]) if row else {}

def keys_for(record,config=None):
    checker=DuplicateChecker()
    kinds=[('email',checker._email_key),('linkedin',checker._linkedin_key),('person_domain',checker._person_domain_key)]
    enabled=(config or {}).get('duplicate_keys') or [k for k,_ in kinds]
    result=[]
    for kind,fn in kinds:
        value=fn(record)
        if value is not None and kind in enabled:
            result.append((kind,hashlib.sha256(json.dumps(value,ensure_ascii=False).encode()).hexdigest()))
    return result

def require_open_campaign(db,cid):
    require(config_for(db,cid).get('status','Running')=='Running','This campaign is paused, closed or archived.',409)

def serialize_lead(db,user,row,export=False):
    result={k:row[k] for k in ('id','campaign_id','owner_id','created_by','assigned_id','department_id','original_department_id','team_lead_id','state','validation','version','archived','created_at','updated_at','updated_by')}
    result['record']=fields_out(db,user,row['campaign_id'],json.loads(row['record_json']),export)
    team=db.execute('SELECT full_name FROM team_users WHERE id=?',(row['team_lead_id'],)).fetchone()
    result['team_lead']=team[0] if team else 'Unassigned'
    for key,table,column in [('assigned_name','team_users','assigned_id'),('owner_name','team_users','owner_id'),('department_name','team_departments','department_id')]:
        found=db.execute('SELECT '+('name' if table=='team_departments' else 'full_name')+' FROM '+table+' WHERE id=?',(row[column],)).fetchone()
        result[key]=found[0] if found else None
    transfer=db.execute('SELECT status FROM team_transfers WHERE lead_id=? ORDER BY rowid DESC LIMIT 1',(row['id'],)).fetchone()
    result['transfer_status']=transfer[0] if transfer else None
    result['field_access']={field:field_access(db,user,row['campaign_id'],field) for field in result['record']}
    result['validation_result']=json.loads(row['validation_json'])
    return result

class LeadOperations:
    def op_field_access(self,db,user,campaign_id,fields=None):
        campaign_access(db,user,campaign_id)
        names=list(STANDARD_HEADERS)+(fields or [])
        require(len(names)<=250 and all(isinstance(n,str) and len(n)<=120 for n in names),'Invalid fields.',400)
        return {name:field_access(db,user,campaign_id,name) for name in names}

    def op_bulk_edit(self,db,user,edits):
        require(isinstance(edits,list) and 0<len(edits)<=1000,'Edit up to 1,000 leads.',400)
        require(len({e['lead_id'] for e in edits})==len(edits),'Each lead must appear once.',400)
        return [self.op_lead_edit(db,user,**item) for item in edits]

    def op_export_draft(self,db,user,campaign_id,records=None,sheet_id=None,row_ids=None):
        campaign_access(db,user,campaign_id)
        if sheet_id:
            sheet=self._sheet(db,user,sheet_id,campaign_id); payload=json.loads(sheet['payload_json'])
            self._redact_formula_values(db,user,campaign_id,payload)
            available=dict(zip(payload.get('row_ids',[]),payload.get('records',[])))
            require(isinstance(row_ids,list) and len(row_ids)<=5000 and all(r in available for r in row_ids),'Draft selection changed. Reload the sheet.',409)
            clean=[available[r] for r in row_ids]
        else:
            require(isinstance(records,list) and len(records)<=5000,'Export up to 5,000 draft rows.',400)
            clean=[fields_in(db,user,campaign_id,row) for row in records]
        rows=[fields_out(db,user,campaign_id,row,export=True) for row in clean]
        require(any(rows),'No fields may be exported.')
        audit(db,user,'draft-export',campaign_id,details={'rows':len(rows),'sheet_id':sheet_id})
        return rows
    def _engine(self,db,cid):
        config=config_for(db,cid); profile=None; tal=suppression=None
        raw=db.execute('SELECT payload_json FROM campaign_profiles WHERE campaign_id=?',(cid,)).fetchone()
        payload=json.loads(raw[0]) if raw else {}
        if payload.get('campaign_id'):
            profile=CampaignProfile.from_dict(payload)
            tal,suppression,warnings=build_campaign_validators(profile)
            require(not warnings,'Campaign reference files are unavailable. Ask an administrator to repair them before validating.',409)
        for kind,rows in (("tal",config.get('tal')),('suppression',config.get('suppression'))):
            if rows is not None:
                reference=ReferenceData(kind=kind,source_path='',source_name='Campaign reference',columns=tuple({k for row in rows for k in row}),mapping={},records=tuple(rows))
                if kind=='tal': tal=TALValidator(reference)
                else: suppression=SuppressionValidator(reference)
        return ValidationEngine(tal_validator=tal,suppression_validator=suppression,
                                require_tal_match=config.get('require_tal_match',True),enable_suppression=config.get('enable_suppression',True),campaign_profile=profile)

    def _validate(self,db,user,cid,records,*,sheet_id=None,exclude_lead=None):
        campaign_access(db,user,cid)
        config=config_for(db,cid); engine=self._engine(db,cid)
        # Use the configured exact keys consistently for both the batch and the
        # committed index. Possible matches only request review; they never merge.
        batch_keys=Counter(key for record in records for key in keys_for(record,config))
        checker=engine.duplicate_checker
        possible=Counter(checker._person_company_key(r) for r in records)
        existing=[json.loads(r[0]) for r in db.execute('SELECT record_json FROM team_leads WHERE campaign_id=? AND id<>?',(cid,exclude_lead or ''))]
        existing_keys={key for r in existing for key in keys_for(r,config)}
        possible_existing={checker._person_company_key(r) for r in existing}
        for r in db.execute('SELECT payload_json FROM team_sheets WHERE campaign_id=? AND archived=0 AND id<>?',(cid,sheet_id or '')):
            possible_existing.update(checker._person_company_key(v) for v in json.loads(r[0]).get('records',[]))
        caps=dict(config.get('domain_caps',{})); default_cap=config.get('domain_cap_default')
        profile=engine.campaign_rule_validator.profile
        for rule in profile.rules if profile else []:
            if rule.status not in ('Confirmed','Extracted'): continue
            if rule.field in ('domain_caps','domain_limits') and isinstance(rule.value,dict): caps.update(rule.value)
            if rule.field in ('domain_cap_default','account_cap_default'): default_cap=rule.value
        cap_engine=DomainCapEngine(caps,default_cap)
        used=Counter(normalize_domain(r.get('Company Website')) for r in existing)
        output=[]
        for index,record in enumerate(records):
            pkey=checker._person_company_key(record)
            duplicate=DuplicateResult('Possible Duplicate' if pkey and (possible[pkey]>1 or pkey in possible_existing) else 'Unique')
            for kind,value in keys_for(record,config):
                exact=db.execute('SELECT lead_id FROM team_lead_keys WHERE campaign_id=? AND kind=? AND value=? AND lead_id<>?',(cid,kind,value,exclude_lead or '')).fetchone()
                draft=db.execute('SELECT 1 FROM team_draft_keys d WHERE campaign_id=? AND kind=? AND value=? AND sheet_id<>? AND NOT EXISTS(SELECT 1 FROM team_sheet_leads sl WHERE sl.sheet_id=d.sheet_id AND sl.lead_id=?) LIMIT 1',(cid,kind,value,sheet_id or '',exclude_lead or '')).fetchone()
                if exact or draft or (kind,value) in existing_keys or batch_keys[(kind,value)]>1:
                    duplicate=DuplicateResult('Exact Duplicate',(),kind); break
            result=engine.validate(record,duplicate_result=duplicate)
            required=[k for k in config.get('required_fields',[]) if str(record.get(k,'-')).strip() in ('','-')]
            if any(i.severity=='suppressed' for i in result.issues): category='Suppressed'
            elif duplicate.is_exact: category='Duplicate'
            elif required or result.status.startswith(('Invalid','Outside TAL')): category='Invalid'
            elif result.status.startswith('Valid'): category='Valid'
            else: category='Pending Review'
            messages=[]
            domain=normalize_domain(record.get('Company Website')); cap=cap_engine.cap_for(domain)
            if category=='Valid' and cap is not None:
                if used[domain]>=cap:
                    category='Invalid'; messages.append('Campaign domain cap reached.'); result.status='Invalid'
                else: used[domain]+=1
            for issue in result.issues:
                if issue.code.startswith('duplicate') or duplicate.is_exact and 'duplicate' in issue.code:
                    messages.append('Duplicate — Already Exists in Campaign or the current upload.')
                else:
                    # Only codes/authorized field names are returned, never matched lead contents or source paths.
                    messages.append(issue.code.replace('_',' ').capitalize())
            if required: messages.append('Missing mandatory fields: '+', '.join(k for k in required if field_access(db,user,cid,k)!='Hidden'))
            if duplicate.is_exact and not any('Duplicate' in m for m in messages): messages.append('Duplicate — Already Exists in Campaign or another worksheet.')
            output.append({'row':index,'category':category,'status':result.status,'messages':list(dict.fromkeys(messages)),
                           'qa_status':result.qa_status,'primary_reason':messages[0] if messages else 'Validation passed'})
        return output

    def op_validate_draft(self,db,user,campaign_id,records,sheet_id=None):
        campaign_access(db,user,campaign_id)
        require(isinstance(records,list) and len(records)<=5000,'Validate at most 5,000 draft rows per request.',400)
        if sheet_id: self._sheet(db,user,sheet_id,campaign_id)
        clean=[fields_in(db,user,campaign_id,r) for r in records]
        results=self._validate(db,user,campaign_id,clean,sheet_id=sheet_id)
        audit(db,user,'validate-draft',campaign_id,details={'count':len(records)})
        return {'results':results,'summary':dict(Counter(r['category'] for r in results)),'total':len(records)}

    def op_commit(self,db,user,campaign_id,records,request_key,source_name='Manual entry',sheet_id=None):
        campaign_access(db,user,campaign_id); require_open_campaign(db,campaign_id)
        require(isinstance(records,list) and 0<len(records)<=5000 and isinstance(request_key,str) and 8<=len(request_key)<=100,'Invalid import batch.',400)
        require(isinstance(source_name,str) and len(source_name)<=250,'Invalid source name.',400)
        if sheet_id: self._sheet(db,user,sheet_id,campaign_id,write=True)
        digest=hashlib.sha256(json.dumps([campaign_id,records,sheet_id],sort_keys=True).encode()).hexdigest()
        previous=db.execute('SELECT * FROM team_batches WHERE user_id=? AND request_key=?',(user['id'],request_key)).fetchone()
        if previous:
            require(previous['digest']==digest,'This request key was used for a different batch.',409)
            return json.loads(previous['result_json'])
        clean=[fields_in(db,user,campaign_id,r) for r in records]
        source_sheet=None
        if sheet_id:
            source_sheet=self._sheet(db,user,sheet_id,campaign_id,write=True)
            saved=json.loads(source_sheet['payload_json'])
            expected=[fields_in(db,user,campaign_id,{k:v for k,v in r.items() if field_access(db,user,campaign_id,k)=='Edit'}) for r in saved.get('records',[])]
            require(expected==clean,'The saved sheet changed. Reload it before committing.',409)
        results=self._validate(db,user,campaign_id,clean,sheet_id=sheet_id)
        accepted=[]; config=config_for(db,campaign_id); batch_id=str(uuid.uuid4())
        require(user['department_id'] is not None or user['role']=='Super User','Assign a department before uploading.')
        for row,result in zip(clean,results):
            if result['category']!='Valid': continue
            lid=str(uuid.uuid4()); row['QA Status']=result['qa_status']; row['Primary Reason']=result['primary_reason']; row['Source File Name']=source_name
            db.execute("""INSERT INTO team_leads(id,campaign_id,owner_id,created_by,assigned_id,department_id,team_lead_id,record_json,state,validation,validation_json,updated_by)
              VALUES(?,?,?,?,?,?,?,?,'Validated','Valid',?,?)""",(lid,campaign_id,user['id'],user['id'],user['id'],user['department_id'],user['team_lead_id'],json.dumps(row),json.dumps(result),user['id']))
            db.execute('UPDATE team_leads SET original_department_id=?,team_lead_id=? WHERE id=?',(user['department_id'],user['id'] if user['role']=='Team Lead' else user['team_lead_id'],lid))
            for kind,value in keys_for(row,config): db.execute('INSERT INTO team_lead_keys VALUES(?,?,?,?)',(campaign_id,kind,value,lid))
            if sheet_id: db.execute('INSERT INTO team_sheet_leads VALUES(?,?)',(sheet_id,lid))
            lead=db.execute('SELECT * FROM team_leads WHERE id=?',(lid,)).fetchone()
            history(db,user,lead,'commit','record',None,row)
            accepted.append({'row':result['row'],'id':lid,'version':1})
        outcome={'batch_id':batch_id,'committed':accepted,'results':results,'summary':dict(Counter(r['category'] for r in results))}
        if source_sheet and accepted:
            # Publish and remove accepted draft rows in the same transaction. A
            # lost HTTP reply cannot leave a second copy waiting to be committed.
            from app.core.data_manager import DataManager
            payload=json.loads(source_sheet['payload_json']); accepted_rows={r['row'] for r in accepted}
            manager=DataManager(); manager.add_columns(payload.get('custom_columns',[])); manager.replace_all(payload.get('records',[]))
            manager.restore_formulas(payload.get('formulas',[])); manager.delete_indices(sorted(accepted_rows))
            remaining=[r for i,r in enumerate(payload.get('records',[])) if i not in accepted_rows]
            payload['records']=[{field:manager.records[i].get(field,value) for field,value in row.items()} for i,row in enumerate(remaining)]
            payload['formulas']=manager.formula_payload()
            payload['row_ids']=[rid for i,rid in enumerate(payload.get('row_ids',[])) if i not in accepted_rows]
            db.execute('UPDATE team_sheets SET payload_json=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(json.dumps(payload),sheet_id))
            self._draft_index(db,sheet_id,campaign_id,payload)
            outcome['sheet_version']=source_sheet['version']+1
        db.execute('INSERT INTO team_batches(id,campaign_id,user_id,request_key,digest,source_name,result_json) VALUES(?,?,?,?,?,?,?)',(batch_id,campaign_id,user['id'],request_key,digest,source_name,json.dumps(outcome)))
        audit(db,user,'commit',campaign_id,details={'batch_id':batch_id,'uploaded':len(records),'committed':len(accepted)})
        notify(db,user['team_lead_id'],'New batch submitted',campaign_id,text='A team member committed a batch for review.')
        return outcome

    def _lead_query(self,db,user,campaign_id=None,view='all',search='',state=None,employee_id=None,department_id=None,team_lead_id=None,date_from=None,date_to=None,archived=False):
        clause,args=scope_sql(user); clauses=[f'({clause})','l.archived=?']; args.append(int(bool(archived)))
        if campaign_id: campaign_access(db,user,campaign_id)
        for field,value in [('campaign_id',campaign_id),('state',state),('assigned_id',employee_id),('department_id',department_id),('team_lead_id',team_lead_id)]:
            if value: clauses.append('l.'+field+'=?'); args.append(value)
        from datetime import date,timedelta
        if date_from: clauses.append('l.created_at>=?'); args.append(date.fromisoformat(date_from).isoformat())
        if date_to: clauses.append('l.created_at<?'); args.append((date.fromisoformat(date_to)+timedelta(days=1)).isoformat())
        if view=='mine': clauses.append('(l.owner_id=? OR l.assigned_id=?)'); args.extend([user['id'],user['id']])
        if view=='department':
            require(user['role'] in ('Department Manager','Team Lead') and user['department_id'],'Choose an available department view.')
            clauses.append('l.department_id=?'); args.append(user['department_id'])
        if view in ('incoming','pending_assignment'):
            require(user['role']!='Employee'); clauses.append('l.assigned_id IS NULL')
            if user['role']!='Super User': clauses.append('l.department_id=?'); args.append(user['department_id'])
            if view=='incoming':clauses.append("EXISTS(SELECT 1 FROM team_transfers t WHERE t.lead_id=l.id AND t.to_department=l.department_id AND t.status='Pending Assignment')")
        if view=='transferred': clauses.append('EXISTS(SELECT 1 FROM team_transfers t WHERE t.lead_id=l.id)')
        if search:
            require(campaign_id is not None,'Select a campaign before searching.',400)
            fields=[f for f in ('First Name','Last Name','Company Name','Business Email ID') if field_access(db,user,campaign_id,f)!='Hidden']
            require(bool(fields),'No searchable fields are visible.')
            clauses.append('('+' OR '.join('json_extract(l.record_json,?) LIKE ? ESCAPE CHAR(92)' for _ in fields)+')')
            escaped=search.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            for field in fields: args.extend(['$."'+field+'"','%'+escaped+'%'])
        return ' AND '.join(clauses),args

    def op_leads(self,db,user,offset=0,limit=200,sort='updated_at',descending=True,**filters):
        require(isinstance(offset,int) and offset>=0 and isinstance(limit,int) and 1<=limit<=1000,'Invalid page.',400)
        require(sort in ('updated_at','created_at','state','validation','id'),'Unsupported sort.',400)
        clause,args=self._lead_query(db,user,**filters)
        total=db.execute('SELECT count(*) FROM team_leads l WHERE '+clause,args).fetchone()[0]
        rows=db.execute('SELECT l.* FROM team_leads l WHERE '+clause+f' ORDER BY l.{sort} '+('DESC' if descending else 'ASC')+',l.id LIMIT ? OFFSET ?',[*args,limit,offset]).fetchall()
        return {'total':total,'rows':[serialize_lead(db,user,r) for r in rows],'offset':offset,'limit':limit}

    def op_lead(self,db,user,lead_id): return serialize_lead(db,user,get_lead(db,user,lead_id))

    def op_lead_edit(self,db,user,lead_id,version,changes):
        lead=get_lead(db,user,lead_id,edit=True); check_version(lead,version); require_open_campaign(db,lead['campaign_id'])
        clean=fields_in(db,user,lead['campaign_id'],changes); record=json.loads(lead['record_json'])
        for field,value in clean.items():
            require(field_access(db,user,lead['campaign_id'],field)=='Edit',f'You cannot edit {field}.')
            if record.get(field)!=value: history(db,user,lead,'edit',field,record.get(field),value)
            record[field]=value
        resumable={'Transferred to Quality','Quality In Progress','Quality TBD','Transferred to Delivery'}
        resume=lead['state'] if lead['state'] in resumable else lead['validation_resume_state']
        db.execute('UPDATE team_leads SET validation_resume_state=? WHERE id=?',(resume,lead_id))
        db.execute('DELETE FROM team_lead_keys WHERE lead_id=?',(lead_id,))
        for kind,value in keys_for(record,config_for(db,lead['campaign_id'])):
            db.execute('INSERT INTO team_lead_keys VALUES(?,?,?,?)',(lead['campaign_id'],kind,value,lead_id))
        db.execute("UPDATE team_leads SET record_json=?,state='Pending Validation',validation='Pending Review',validation_json='{}',version=version+1,updated_at=CURRENT_TIMESTAMP,updated_by=? WHERE id=?",(json.dumps(record),user['id'],lead_id))
        audit(db,user,'lead-edit',lead_id,details={'fields':list(clean)})
        return serialize_lead(db,user,get_lead(db,user,lead_id))

    def op_validate_leads(self,db,user,selection):
        require(isinstance(selection,list) and len(selection)<=1000,'Select up to 1,000 leads.',400)
        output=[]
        for item in selection:
            lead=get_lead(db,user,item['id'],edit=True); check_version(lead,item['version'])
            result=self._validate(db,user,lead['campaign_id'],[json.loads(lead['record_json'])],exclude_lead=lead['id'])[0]
            state=(lead['validation_resume_state'] or 'Validated') if result['category']=='Valid' else 'Validation Failed'
            if result['category']=='Valid':db.execute('UPDATE team_leads SET validation_resume_state=NULL WHERE id=?',(lead['id'],))
            record=json.loads(lead['record_json']); record['QA Status']=result['qa_status']; record['Primary Reason']=result['primary_reason']
            db.execute('UPDATE team_leads SET record_json=? WHERE id=?',(json.dumps(record),lead['id']))
            db.execute('UPDATE team_leads SET state=?,validation=?,validation_json=?,version=version+1,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(state,result['category'],json.dumps(result),user['id'],lead['id']))
            history(db,user,lead,'validation','state',lead['state'],state); output.append({'id':lead['id'],**result})
        audit(db,user,'validation',details={'count':len(output)})
        return output

    def op_archive(self,db,user,selection,restore=False):
        require(user['role'] in ('Super User','Department Manager'))
        if restore: require(user['role']=='Super User')
        require(isinstance(selection,list) and 0<len(selection)<=1000,'Select up to 1,000 leads.',400)
        for item in selection:
            lead=get_lead(db,user,item['id']); check_version(lead,item['version'])
            db.execute("UPDATE team_leads SET archived=?,state='Pending Validation',validation='Pending Review',version=version+1,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(0 if restore else 1,user['id'],lead['id']))
            history(db,user,lead,'restore' if restore else 'archive','archived',lead['archived'],0 if restore else 1)
        audit(db,user,'restore' if restore else 'archive',details={'count':len(selection)})
        return {'updated':len(selection)}

    def op_history(self,db,user,lead_id):
        lead=get_lead(db,user,lead_id)
        result=[]
        for row in db.execute('SELECT h.*,u.full_name FROM team_history h LEFT JOIN team_users u ON u.id=h.user_id WHERE lead_id=? ORDER BY h.id DESC LIMIT 500',(lead_id,)):
            item=dict(row)
            if item['field']=='record':
                for key in ('old_json','new_json'):
                    value=json.loads(item[key] or 'null'); item[key]=json.dumps(fields_out(db,user,lead['campaign_id'],value)) if isinstance(value,dict) else item[key]
            elif field_access(db,user,lead['campaign_id'],item['field'])=='Hidden': continue
            result.append(item)
        return result

    def op_export(self,db,user,lead_ids):
        require(isinstance(lead_ids,list) and 0<len(lead_ids)<=5000,'Export up to 5,000 selected leads.',400)
        rows=[]
        for lid in dict.fromkeys(lead_ids):
            lead=get_lead(db,user,lid); out=serialize_lead(db,user,lead,export=True)
            require(bool(out['record']),'No fields may be exported.')
            rows.append({'Lead ID':lead['id'],'CID':lead['campaign_id'],'Team Lead':out['team_lead'],**{k:v for k,v in out['record'].items() if k not in ('Lead ID','CID','Team Lead')}})
        audit(db,user,'export',details={'count':len(rows)})
        return rows
