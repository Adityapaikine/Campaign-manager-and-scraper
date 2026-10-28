import json
import uuid
from collections import Counter
from app.team.access import require, get_lead, check_version, campaign_access, scope_sql, history, audit, notify, fields_out, field_access, ServiceError
from app.team.leads import config_for

class Workflow:
    def _selection(self,db,user,selection):
        require(isinstance(selection,list) and 0<len(selection)<=1000,'Select 1–1,000 leads.',400)
        require(all(isinstance(i,dict) and isinstance(i.get('id'),str) and isinstance(i.get('version'),int) for i in selection),'Invalid lead selection. Refresh and select the rows again.',400)
        require(len({i['id'] for i in selection})==len(selection),'Select each lead once.',400)
        result=[]
        for item in selection:
            lead=get_lead(db,user,item['id']); check_version(lead,item['version'])
            require(not lead['archived'],'Archived leads cannot be processed.',409)
            require(user['role']=='Super User' or lead['department_id']==user['department_id'])
            result.append(lead)
        return result

    def op_assignment_options(self,db,user,campaign_id):
        campaign_access(db,user,campaign_id); require(user['role']!='Employee')
        rows=self.op_directory(db,user)['users']
        return [r for r in rows if r['active'] and (r['role'] in ('Employee','Team Lead')) and
                db.execute('SELECT 1 FROM team_campaign_users WHERE campaign_id=? AND user_id=?',(campaign_id,r['id'])).fetchone()]

    def op_assign(self,db,user,selection,user_ids,method='Manual'):
        require(user['role'] in ('Super User','Department Manager','Team Lead'))
        require(method in ('Manual','Equal distribution','Round robin') and isinstance(user_ids,list) and 0<len(user_ids)<=100,'Choose eligible employees and an assignment method.',400)
        leads=self._selection(db,user,selection)
        users=[]
        for uid in dict.fromkeys(user_ids):
            employee=db.execute('SELECT * FROM team_users WHERE id=? AND active=1',(uid,)).fetchone()
            require(employee is not None and employee['role'] in ('Employee','Team Lead'),'Choose active employees or Team Leads.',400)
            if user['role']!='Super User': require(employee['department_id']==user['department_id'])
            if user['role']=='Team Lead': require(employee['id']==user['id'] or employee['team_lead_id']==user['id'])
            for lead in leads:
                require(employee['department_id']==lead['department_id'],'Transfers must occur before another department may assign leads.',409)
                campaign_access(db,employee,lead['campaign_id'])
            users.append(employee)
        require(method!='Manual' or len(users)==1,'Manual assignment requires one employee.',400)
        counts={u['id']:db.execute("SELECT count(*) FROM team_leads WHERE assigned_id=? AND archived=0 AND state NOT IN ('Delivered','Quality Disqualified')",(u['id'],)).fetchone()[0] for u in users}
        cursor_row=db.execute("SELECT value_json FROM team_preferences WHERE user_id=? AND key='assignment_cursor'",(user['id'],)).fetchone()
        cursor=json.loads(cursor_row[0]) if cursor_row else 0
        for index,lead in enumerate(leads):
            employee=min(users,key=lambda u:(counts[u['id']],u['id'])) if method=='Equal distribution' else users[(cursor+index)%len(users)] if method=='Round robin' else users[0]
            counts[employee['id']]+=1
            # Historical migrated leads remain ownerless until an explicit administrator assignment.
            db.execute('UPDATE team_leads SET assigned_id=?,team_lead_id=?,version=version+1,updated_at=CURRENT_TIMESTAMP,updated_by=? WHERE id=?',(employee['id'],employee['id'] if employee['role']=='Team Lead' else employee['team_lead_id'],user['id'],lead['id']))
            db.execute("UPDATE team_transfers SET status='Assigned' WHERE lead_id=? AND status='Pending Assignment'",(lead['id'],))
            history(db,user,lead,'assignment','assigned_id',lead['assigned_id'],employee['id'])
            notify(db,employee['id'],'New leads assigned',lead['campaign_id'],lead['id'],'A lead has been assigned to you.')
        if method=='Round robin': db.execute("INSERT INTO team_preferences VALUES(?,'assignment_cursor',?) ON CONFLICT(user_id,key) DO UPDATE SET value_json=excluded.value_json",(user['id'],json.dumps(cursor+len(leads))))
        audit(db,user,'assignment',details={'count':len(leads),'method':method,'users':user_ids})
        return {'updated':len(leads)}

    def op_workflow_options(self,db,user,lead_id):
        lead=get_lead(db,user,lead_id)
        transitions=[r[0] for r in db.execute('SELECT DISTINCT to_state FROM team_transitions WHERE active=1 AND from_state=? AND role=? AND (department_id IS NULL OR department_id=?)',(lead['state'],user['role'],lead['department_id']))]
        if lead['state']=='Validated' and user['role'] in ('Super User','Department Manager','Team Lead') and not config_for(db,lead['campaign_id']).get('review_required',True):transitions.append('Approved')
        routes=[dict(r) for r in db.execute('SELECT r.*,d.name FROM team_routes r JOIN team_departments d ON d.id=r.to_department WHERE r.active=1 AND d.active=1 AND r.from_department=? AND r.required_state=? AND (r.campaign_id IS NULL OR r.campaign_id=?)',(lead['department_id'],lead['state'],lead['campaign_id']))] if user['role']!='Employee' else []
        return {'transitions':transitions,'routes':routes,'reasons':[dict(r) for r in db.execute('SELECT id,name FROM team_reasons WHERE active=1')]}

    def op_transition(self,db,user,selection,state):
        leads=self._selection(db,user,selection)
        for lead in leads:
            require(user['role']!='Employee' or lead['assigned_id']==user['id'])
            require(state in self.op_workflow_options(db,user,lead['id'])['transitions'],'This workflow transition is not permitted.',409)
            if state in ('Approved','Quality Qualified','Delivery Approved','Delivered'):
                require(lead['validation']=='Valid','Validate the lead successfully before approval or delivery.',409)
                result=self._validate(db,user,lead['campaign_id'],[json.loads(lead['record_json'])],exclude_lead=lead['id'])[0]
                require(result['category']=='Valid','Current campaign validation no longer passes. Revalidate and correct the lead before approval.',409)
                require(field_access(db,user,lead['campaign_id'],'@Approval') in ('Edit','Approve'),'Approval permission is required.')
            if state=='Pending Team Lead Review': notify(db,lead['team_lead_id'],'Approval requested',lead['campaign_id'],lead['id'],'A lead is ready for review.')
            db.execute('UPDATE team_leads SET state=?,version=version+1,updated_at=CURRENT_TIMESTAMP,updated_by=? WHERE id=?',(state,user['id'],lead['id']))
            history(db,user,lead,'workflow','state',lead['state'],state)
            event={'Quality Qualified':'Quality review completed','Quality Disqualified':'Lead rejected','Quality TBD':'Quality review pending','Delivery Approved':'Delivery approval completed','Delivered':'Delivery completed'}.get(state,'Workflow updated')
            notify(db,lead['owner_id'],event,lead['campaign_id'],lead['id'],'Your submitted lead has a workflow update.')
        audit(db,user,'workflow',details={'count':len(leads),'state':state}); return {'updated':len(leads)}

    def _transfer_blocker(self,db,user,lead,route):
        if lead['department_id']!=route['from_department']:
            return 'This lead is in another department.'
        if route['campaign_id'] not in (None,lead['campaign_id']):
            return 'This route belongs to another campaign.'
        if lead['state']!=route['required_state']:
            return 'Required stage: '+route['required_state']+'. Use Review / change stage first.'
        configured=config_for(db,lead['campaign_id']).get('departments',[])
        if configured and route['to_department'] not in configured:
            return 'The destination department is not enabled for this campaign.'
        if lead['validation']!='Valid':
            return 'Validate and approve this lead before sending it.'
        result=self._validate(db,user,lead['campaign_id'],[json.loads(lead['record_json'])],exclude_lead=lead['id'])[0]
        if result['category']!='Valid':
            return 'Current campaign validation does not pass. Return for correction and revalidate.'
        return ''

    def op_selection_actions(self,db,user,selection):
        """Read-only bulk preview; the write checks the same versions and rules again."""
        leads=self._selection(db,user,selection)
        transitions=None
        for lead in leads:
            choices=set(self.op_workflow_options(db,user,lead['id'])['transitions'])
            if user['role']=='Employee' and lead['assigned_id']!=user['id']:choices=set()
            if lead['validation']!='Valid' or field_access(db,user,lead['campaign_id'],'@Approval') not in ('Edit','Approve'):
                choices-={'Approved','Quality Qualified','Delivery Approved','Delivered'}
            transitions=choices if transitions is None else transitions & choices
        previews=[]
        if user['role']!='Employee':
            departments={lead['department_id'] for lead in leads}
            campaigns={lead['campaign_id'] for lead in leads}
            routes=db.execute('SELECT r.*,d.name FROM team_routes r JOIN team_departments d ON d.id=r.to_department WHERE r.active=1 AND d.active=1 ORDER BY d.name,r.id')
            for route in routes:
                if route['from_department'] not in departments or route['campaign_id'] not in (None,*campaigns):continue
                rows=[]
                for lead in leads:
                    try:reason=self._transfer_blocker(db,user,lead,route)
                    except ServiceError as exc:reason=str(exc)
                    record=fields_out(db,user,lead['campaign_id'],json.loads(lead['record_json']))
                    name=' '.join(str(record.get(f,'')) for f in ('First Name','Last Name')).strip() or lead['id']
                    rows.append({'id':lead['id'],'name':name,'state':lead['state'],'ready':not reason,'reason':reason or 'Ready to send'})
                previews.append({**dict(route),'rows':rows,'ready':sum(r['ready'] for r in rows)})
        return {'count':len(leads),'transitions':sorted(transitions or []),'routes':previews}

    def op_transfer(self,db,user,selection,route_id,note=''):
        require(user['role'] in ('Super User','Department Manager','Team Lead'))
        require(isinstance(note,str) and len(note)<=2000,'Transfer note is too long.',400)
        route=db.execute('SELECT * FROM team_routes WHERE id=? AND active=1',(route_id,)).fetchone()
        require(route is not None,'Transfer route unavailable.',404)
        require(db.execute('SELECT 1 FROM team_departments WHERE id=? AND active=1',(route['to_department'],)).fetchone(),'Destination department is inactive.',409)
        leads=self._selection(db,user,selection)
        for lead in leads:
            blocker=self._transfer_blocker(db,user,lead,route)
            require(not blocker,blocker+' Nothing was transferred.',409)
            tid=str(uuid.uuid4())
            db.execute('INSERT INTO team_transfers(id,lead_id,from_department,to_department,previous_assignee,transferred_by,note) VALUES(?,?,?,?,?,?,?)',(tid,lead['id'],lead['department_id'],route['to_department'],lead['assigned_id'],user['id'],note))
            db.execute('UPDATE team_leads SET department_id=?,assigned_id=NULL,team_lead_id=NULL,state=?,version=version+1,updated_at=CURRENT_TIMESTAMP,updated_by=? WHERE id=?',(route['to_department'],route['arrival_state'],user['id'],lead['id']))
            history(db,user,lead,'transfer','department_id',lead['department_id'],route['to_department'])
            for supervisor in db.execute("SELECT u.id FROM team_users u JOIN team_campaign_users cu ON cu.user_id=u.id WHERE u.department_id=? AND u.active=1 AND u.role IN ('Department Manager','Team Lead') AND cu.campaign_id=?",(route['to_department'],lead['campaign_id'])):
                notify(db,supervisor[0],'Incoming leads',lead['campaign_id'],lead['id'],'A transferred lead is waiting for assignment.')
        audit(db,user,'transfer',route_id,details={'count':len(leads)}); return {'transferred':len(leads)}

    def op_rework(self,db,user,selection,reason_id,comment=''):
        require(user['role'] in ('Super User','Department Manager','Team Lead') or user['department_id']=='quality')
        reason=db.execute('SELECT name FROM team_reasons WHERE id=? AND active=1',(reason_id,)).fetchone()
        require(reason is not None,'Select an active rejection reason.',400)
        require(isinstance(comment,str) and len(comment)<=2000,'Comment is too long.',400)
        leads=self._selection(db,user,selection)
        for lead in leads:
            if user['role']=='Employee': require(lead['assigned_id']==user['id'])
            require(lead['state'] not in ('Delivered','Draft','Rework Required'),'This stage cannot be returned for rework.',409)
            owner=db.execute('SELECT * FROM team_users WHERE id=?',(lead['owner_id'],)).fetchone()
            require(owner and owner['department_id'],'Assign historical ownership before returning this lead.',409)
            original_department=lead['original_department_id'] or owner['department_id']
            original_assignment=owner['id'] if owner['active'] and owner['department_id']==original_department else None
            # Explicit audited return to the original department; inactive owners remain unassigned.
            db.execute('INSERT INTO team_transfers(id,lead_id,from_department,to_department,previous_assignee,transferred_by,note,status) VALUES(?,?,?,?,?,?,?,?)',(str(uuid.uuid4()),lead['id'],lead['department_id'],original_department,lead['assigned_id'],user['id'],reason[0]+': '+comment,'Rework'))
            db.execute("UPDATE team_leads SET department_id=?,assigned_id=?,team_lead_id=?,state='Rework Required',validation='Pending Review',version=version+1,updated_at=CURRENT_TIMESTAMP,updated_by=? WHERE id=?",(original_department,original_assignment,owner['team_lead_id'] if original_assignment else None,user['id'],lead['id']))
            history(db,user,lead,'rework','state',lead['state'],{'state':'Rework Required','reason':reason[0],'comment':comment})
            for uid in (owner['id'],owner['team_lead_id']): notify(db,uid,'Lead returned for correction',lead['campaign_id'],lead['id'],'A lead was returned for rework. Open its history for the reason.')
        audit(db,user,'rework',details={'count':len(leads),'reason_id':reason_id}); return {'returned':len(leads)}

    def op_transfer_history(self,db,user,lead_id):
        get_lead(db,user,lead_id)
        return [dict(r) for r in db.execute('SELECT * FROM team_transfers WHERE lead_id=? ORDER BY created_at DESC',(lead_id,))]

    def op_comments(self,db,user,lead_id,body=None):
        lead=get_lead(db,user,lead_id)
        if body is not None:
            require(isinstance(body,str) and 0<len(body.strip())<=4000,'Enter a comment of up to 4,000 characters.',400)
            db.execute('INSERT INTO team_comments(lead_id,user_id,body) VALUES(?,?,?)',(lead_id,user['id'],body.strip()))
            audit(db,user,'comment',lead_id)
        return [dict(r) for r in db.execute('SELECT c.id,c.body,c.created_at,u.full_name FROM team_comments c JOIN team_users u ON u.id=c.user_id WHERE lead_id=? ORDER BY c.id',(lead_id,))]

    def op_notifications(self,db,user,event=None,read_ids=None):
        if read_ids:
            require(isinstance(read_ids,list) and len(read_ids)<=200,'Invalid notification selection.',400)
            for nid in read_ids: db.execute('UPDATE team_notifications SET is_read=1 WHERE id=? AND user_id=?',(nid,user['id']))
        clause,args=scope_sql(user)
        query="SELECT n.* FROM team_notifications n WHERE n.user_id=? AND (n.campaign_id IS NULL OR EXISTS(SELECT 1 FROM team_campaign_users cu WHERE cu.user_id=? AND cu.campaign_id=n.campaign_id) OR ?='Super User') AND (n.lead_id IS NULL OR EXISTS(SELECT 1 FROM team_leads l WHERE l.id=n.lead_id AND ("+clause+")))"
        values=[user['id'],user['id'],user['role'],*args]
        if event: query+=' AND n.event=?'; values.append(event)
        unread=db.execute('SELECT count(*) FROM ('+query+' AND n.is_read=0)',values).fetchone()[0]
        events=[r[0] for r in db.execute('SELECT DISTINCT event FROM ('+query+')',values)]
        rows=[dict(r) for r in db.execute(query+' ORDER BY n.id DESC LIMIT 200',values)]
        return {'unread':unread,'rows':rows,'events':events}
