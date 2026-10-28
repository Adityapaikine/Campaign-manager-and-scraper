import json
import uuid
from app.team.access import require, campaign_access, fields_in, fields_out, field_access, check_version, audit
from app.team.leads import config_for, keys_for, require_open_campaign

class Worksheets:
    def _redact_formula_values(self,db,user,cid,payload):
        headers=set(payload.get('headers',[]))
        for record in payload.get('records',[]):headers.update(record)
        if any(field_access(db,user,cid,field)=='Hidden' for field in headers):
            for entry in payload.get('formulas',[]):
                index=entry.get('row'); field=entry.get('column')
                if isinstance(index,int) and 0<=index<len(payload.get('records',[])) and field in payload['records'][index]:payload['records'][index][field]='-'
            payload['formulas']=[]
        return payload

    def op_sheet_recovery(self,db,user,campaign_id,payload,name='Recovered edits'):
        sheet=self.op_sheet_create(db,user,campaign_id,name)
        self.op_sheet_save(db,user,sheet['id'],1,payload)
        audit(db,user,'sheet-recovery',sheet['id'])
        return sheet

    def _sheet(self,db,user,sheet_id,cid=None,*,write=False):
        row=db.execute('SELECT * FROM team_sheets WHERE id=?',(sheet_id,)).fetchone()
        require(row is not None and (user['role']=='Super User' or
                (row['owner_id']==user['id'] and not row['archived'])),'Worksheet unavailable.',404)
        campaign_access(db,user,row['campaign_id'])
        require(cid is None or cid==row['campaign_id'])
        if write:
            require(row['owner_id']==user['id'] and not row['archived'],
                    'This worksheet is read-only. Duplicate it into your working drafts to make changes.')
        return row

    def _sheet_details(self,db,user,row):
        owner=db.execute('SELECT full_name,username FROM team_users WHERE id=?',(row['owner_id'],)).fetchone()
        return {'owner_id':row['owner_id'],'owner_name':owner['full_name'],'owner_username':owner['username'],
                'archived':bool(row['archived']),'read_only':row['owner_id']!=user['id'] or bool(row['archived'])}

    def op_sheets(self,db,user,campaign_id,include_all=False):
        campaign_access(db,user,campaign_id)
        require(isinstance(include_all,bool),'Invalid worksheet scope.',400)
        require(not include_all or user['role']=='Super User','Only a Super User can view everyone\'s worksheets.')
        where='campaign_id=?'; params=[campaign_id]
        if not include_all:where+=' AND owner_id=? AND archived=0'; params.append(user['id'])
        rows=db.execute('SELECT id,name,version,updated_at,owner_id,archived FROM team_sheets WHERE '+where+' ORDER BY archived,rowid',params).fetchall()
        return [{**dict(r),**self._sheet_details(db,user,r)} for r in rows]

    def op_sheet_create(self,db,user,campaign_id,name='Sheet1',duplicate_id=None):
        campaign_access(db,user,campaign_id); require_open_campaign(db,campaign_id)
        require(isinstance(name,str) and 1<=len(name.strip())<=100,'Enter a sheet name.',400)
        payload={}; source=None
        if duplicate_id:
            source=self._sheet(db,user,duplicate_id,campaign_id)
            payload=json.loads(source['payload_json'])
        sid=str(uuid.uuid4())
        db.execute('INSERT INTO team_sheets(id,campaign_id,owner_id,name,payload_json) VALUES(?,?,?,?,?)',(sid,campaign_id,user['id'],name.strip(),json.dumps(payload)))
        if source:
            db.execute('INSERT INTO team_sheet_leads SELECT ?,lead_id FROM team_sheet_leads WHERE sheet_id=?',(sid,source['id']))
            self._draft_index(db,sid,campaign_id,payload)
        audit(db,user,'sheet-create',sid)
        return {'id':sid,'version':1}

    def _draft_index(self,db,sid,cid,payload):
        db.execute('DELETE FROM team_draft_keys WHERE sheet_id=?',(sid,))
        config=config_for(db,cid)
        for index,record in enumerate(payload.get('records',[])):
            for kind,value in keys_for(record,config):
                db.execute('INSERT INTO team_draft_keys VALUES(?,?,?,?,?)',(cid,sid,index,kind,value))

    def op_sheet_load(self,db,user,sheet_id):
        row=self._sheet(db,user,sheet_id); payload=json.loads(row['payload_json'])
        details=self._sheet_details(db,user,row)
        if details['read_only']:
            audit(db,user,'sheet-inspect',sheet_id,details={'owner_id':row['owner_id'],'archived':bool(row['archived'])})
        self._redact_formula_values(db,user,row['campaign_id'],payload)
        payload['records']=[fields_out(db,user,row['campaign_id'],r) for r in payload.get('records',[])]
        visible=set().union(*(set(r) for r in payload['records'])) if payload['records'] else set()
        payload['custom_columns']=[h for h in payload.get('custom_columns',[]) if field_access(db,user,row['campaign_id'],h)!='Hidden']
        payload['headers']=[f for f in payload.get('headers',[]) if field_access(db,user,row['campaign_id'],f)!='Hidden']
        return {'id':row['id'],'name':row['name'],'campaign_id':row['campaign_id'],'version':row['version'],'payload':payload,**details,
                'committed_count':db.execute('SELECT count(*) FROM team_sheet_leads WHERE sheet_id=?',(sheet_id,)).fetchone()[0]}

    def op_sheet_save(self,db,user,sheet_id,version,payload):
        row=self._sheet(db,user,sheet_id,write=True); check_version(row,version); require_open_campaign(db,row['campaign_id'])
        require(isinstance(payload,dict) and len(json.dumps(payload))<=12_000_000,'Worksheet exceeds the 12 MB limit. Split it into smaller sheets.',400)
        records=payload.get('records',[])
        require(isinstance(records,list) and len(records)<=5000,'A draft sheet supports up to 5,000 rows. Use another sheet for additional rows.',400)
        old=json.loads(row['payload_json']); old_ids=old.get('row_ids',[])
        old_rows=dict(zip(old_ids,old.get('records',[])))
        row_ids=payload.get('row_ids') or [str(uuid.uuid4()) for _ in records]
        require(isinstance(row_ids,list) and len(row_ids)==len(records) and len(set(row_ids))==len(row_ids) and all(isinstance(i,str) and len(i)<=80 for i in row_ids),'Invalid draft row identities.',400)
        clean=[]
        for rid,record in zip(row_ids,records):
            value=fields_in(db,user,row['campaign_id'],record)
            for field,previous in old_rows.get(rid,{}).items():
                if field_access(db,user,row['campaign_id'],field)!='Edit': value[field]=previous
            clean.append(value)
        columns=payload.get('custom_columns',[])
        require(isinstance(columns,list) and len(columns)<=200 and all(isinstance(x,str) and 0<len(x)<=120 for x in columns),'Invalid columns.',400)
        headers=payload.get('headers',[]); formulas=payload.get('formulas',[])
        require(isinstance(headers,list) and len(headers)<=250 and all(isinstance(x,str) and 0<len(x)<=120 for x in headers),'Invalid worksheet headers.',400)
        require(isinstance(formulas,list) and all(isinstance(f,dict) and isinstance(f.get('row'),int) and 0<=f['row']<len(records) and
            isinstance(f.get('column'),str) and 0<len(f['column'])<=120 and isinstance(f.get('expression'),str) and
            f['expression'].startswith('=') and len(f['expression'])<=32767 for f in formulas),'Invalid worksheet formulas.',400)
        allowed={'custom_columns','formulas','view','headers'}
        stored={k:payload[k] for k in allowed if k in payload}; stored.update(records=clean,row_ids=row_ids)
        db.execute('UPDATE team_sheets SET payload_json=?,version=version+1,updated_at=CURRENT_TIMESTAMP WHERE id=?',(json.dumps(stored),sheet_id))
        self._draft_index(db,sheet_id,row['campaign_id'],stored)
        audit(db,user,'sheet-save',sheet_id,details={'rows':len(clean)})
        return {'version':version+1,'row_ids':row_ids}

    def op_sheet_rename(self,db,user,sheet_id,version,name):
        row=self._sheet(db,user,sheet_id,write=True); check_version(row,version)
        require(isinstance(name,str) and 0<len(name.strip())<=100,'Enter a sheet name.',400)
        db.execute('UPDATE team_sheets SET name=?,version=version+1 WHERE id=?',(name.strip(),sheet_id))
        audit(db,user,'sheet-rename',sheet_id); return {'version':version+1}

    def op_sheet_delete(self,db,user,sheet_id,version):
        row=self._sheet(db,user,sheet_id,write=True); check_version(row,version)
        db.execute('UPDATE team_sheets SET archived=1,version=version+1 WHERE id=?',(sheet_id,))
        db.execute('DELETE FROM team_draft_keys WHERE sheet_id=?',(sheet_id,))
        audit(db,user,'sheet-archive',sheet_id)
        return {'archived':True,'committed_leads_preserved':True}
