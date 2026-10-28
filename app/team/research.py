"""Reference lookup never expands the caller's campaign/field visibility."""
import json
from app.core.lead_reference import PROSPECT_FIELDS,COMPANY_FIELDS,prospect_key,company_key
from app.team.access import campaign_access,fields_in,fields_out,scope_sql,require,field_access,audit

class Research:
    def op_populate(self,db,user,campaign_id,records,columns,overwrite=False):
        campaign_access(db,user,campaign_id)
        require(isinstance(records,list) and len(records)<=5000 and isinstance(columns,list) and 0<len(columns)<=30,'Choose up to 5,000 rows and the fields to populate.',400)
        for field in columns:require(field in (*PROSPECT_FIELDS,*COMPANY_FIELDS) and field_access(db,user,campaign_id,field)=='Edit','This field cannot be populated.')
        for field in columns:
            key_field='Prospect LinkedIn Link' if field in PROSPECT_FIELDS else 'Company Website'
            require(field_access(db,user,campaign_id,key_field)!='Hidden','The lookup key is not visible.')
        clause,args=scope_sql(user); indices={f:{} for f in columns}
        for row in db.execute('SELECT l.record_json FROM team_leads l WHERE l.campaign_id=? AND l.archived=0 AND ('+clause+')',[campaign_id,*args]):
            record=fields_out(db,user,campaign_id,json.loads(row[0]))
            for field in columns:
                key=prospect_key(record.get('Prospect LinkedIn Link')) if field in PROSPECT_FIELDS else company_key(record.get('Company Website'))
                value=record.get(field)
                if key and value and value!='-':indices[field].setdefault(key,set()).add(value)
        edits=[]
        for i,record in enumerate(records):
            require(isinstance(record,dict),'Invalid record.',400)
            for field in columns:
                if not overwrite and str(record.get(field,'-')).strip() not in ('','-'):continue
                key=prospect_key(record.get('Prospect LinkedIn Link')) if field in PROSPECT_FIELDS else company_key(record.get('Company Website'))
                values=indices[field].get(key,set())
                if len(values)==1:edits.append({'row':i,'field':field,'value':next(iter(values))})
        audit(db,user,'reference-populate',campaign_id,details={'rows':len(records),'fields':columns,'cells':len(edits)})
        return {'edits':edits}
