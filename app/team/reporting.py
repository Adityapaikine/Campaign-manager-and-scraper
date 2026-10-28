import json
from datetime import date
from app.core.campaign_dashboard import daily_target, parse_date, count_value
from app.team.access import scope_sql, campaign_access, require, audit, history, notify

class Reporting:
    def op_report_export(self,db,user,**filters):
        report=self.op_report(db,user,**filters)
        audit(db,user,'report-export',details={'campaign_id':filters.get('campaign_id'),'total':report['total']})
        return report

    def op_report(self,db,user,**filters):
        clause,args=self._lead_query(db,user,**filters)
        totals={r['state']:r['n'] for r in db.execute('SELECT l.state,count(*) n FROM team_leads l WHERE '+clause+' GROUP BY l.state',args)}
        validation={r['validation']:r['n'] for r in db.execute('SELECT l.validation,count(*) n FROM team_leads l WHERE '+clause+' GROUP BY l.validation',args)}
        employees=[dict(r) for r in db.execute("""SELECT l.assigned_id,u.full_name, count(*) assigned,
          sum(CASE WHEN l.state IN ('Delivered','Quality Qualified','Quality Disqualified') THEN 1 ELSE 0 END) completed,
          sum(CASE WHEN l.state='Rework Required' THEN 1 ELSE 0 END) rework,
          sum(CASE WHEN l.state NOT IN ('Delivered','Quality Qualified','Quality Disqualified','Rework Required') THEN 1 ELSE 0 END) pending
          FROM team_leads l LEFT JOIN team_users u ON u.id=l.assigned_id WHERE """+clause+' GROUP BY l.assigned_id,u.full_name',args)]
        departments=[dict(r) for r in db.execute('SELECT d.name,l.department_id,count(*) total FROM team_leads l LEFT JOIN team_departments d ON d.id=l.department_id WHERE '+clause+' GROUP BY l.department_id,d.name',args)]
        transfer_count=db.execute('SELECT count(*) FROM team_transfers t WHERE EXISTS(SELECT 1 FROM team_leads l WHERE l.id=t.lead_id AND '+clause+')',args).fetchone()[0]
        age=db.execute("SELECT avg((julianday(l.updated_at)-julianday(l.created_at))*24) FROM team_leads l WHERE "+clause+" AND l.state='Delivered'",args).fetchone()[0]
        today=db.execute("SELECT count(*) FROM team_leads l WHERE "+clause+" AND date(l.created_at)=date('now')",args).fetchone()[0]
        directory=self.op_directory(db,user)['users']
        active_employees=sum(u['active'] and u['role']=='Employee' for u in directory if not filters.get('campaign_id') or db.execute('SELECT 1 FROM team_campaign_users WHERE campaign_id=? AND user_id=?',(filters['campaign_id'],u['id'])).fetchone())
        trends=[dict(r) for r in db.execute('SELECT date(l.created_at) day,l.validation,count(*) leads FROM team_leads l WHERE '+clause+' GROUP BY date(l.created_at),l.validation ORDER BY day DESC LIMIT 300',args)]
        return {'total':sum(totals.values()),'states':totals,'validation':validation,'workload':employees,'departments':departments,'transfer_events':transfer_count,'mean_delivered_elapsed_hours':age,
                'submitted_today_utc':today,'active_employees':active_employees,'quality_by_created_date':trends,
                'definitions':'Each committed Lead ID is counted once. Drafts, sheet links and transfer history do not increase lead totals. Processing time is elapsed creation-to-delivery time, including waiting and rework.'}

    def op_dashboard(self,db,user):
        output=[]
        for campaign in self.op_campaigns(db,user):
            cid=campaign['campaign_id']; config=campaign['config']; report=self.op_report(db,user,campaign_id=cid)
            clause,args=scope_sql(user)
            names=[r[0] for r in db.execute('SELECT DISTINCT u.full_name FROM team_leads l JOIN team_users u ON u.id=l.team_lead_id WHERE l.campaign_id=? AND l.archived=0 AND ('+clause+')',[cid,*args])]
            allocation=count_value(config.get('allocation')); start=parse_date(config.get('start_date')); end=parse_date(config.get('end_date'))
            delivered=report['states'].get('Delivered',0)
            if user['role']=='Super User' and count_value(config.get('delivered')) is not None:delivered=count_value(config['delivered'])
            output.append({'campaign_id':cid,'campaign_name':campaign['campaign_name'],'team_lead':', '.join(names) or 'Unassigned',
                           'allocation':allocation,'start':start.isoformat() if start else None,'end':end.isoformat() if end else None,
                           'total':report['total'],'qualified':sum(report['states'].get(s,0) for s in ('Quality Qualified','Transferred to Delivery','Delivery Approved','Delivered')),'disqualified':report['states'].get('Quality Disqualified',0),
                           'delivered':delivered,'remaining':max(0,allocation-delivered) if allocation is not None else None,
                           'average':daily_target(allocation,start,end),'status':config.get('status','Not set'),'metrics':report})
        return output

    def op_historical_assignment(self,db,user,selection,owner_id):
        require(user['role']=='Super User')
        owner=db.execute('SELECT * FROM team_users WHERE id=? AND active=1',(owner_id,)).fetchone()
        require(owner and owner['department_id'],'Choose an active user with a department.',400)
        leads=self._selection(db,user,selection)
        for lead in leads:
            require(lead['owner_id'] is None,'Historical ownership has already been established and cannot be overwritten.',409)
            campaign_access(db,owner,lead['campaign_id'])
            db.execute('UPDATE team_leads SET owner_id=?,department_id=?,assigned_id=?,team_lead_id=?,version=version+1,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?',(owner_id,owner['department_id'],owner_id,owner['team_lead_id'],user['id'],lead['id']))
            db.execute('UPDATE team_leads SET original_department_id=? WHERE id=?',(owner['department_id'],lead['id']))
            history(db,user,lead,'historical-assignment','owner_id',None,owner_id)
            notify(db,owner_id,'New leads assigned',lead['campaign_id'],lead['id'],'Historical lead ownership was explicitly assigned to you.')
        audit(db,user,'historical-assignment',details={'count':len(leads),'owner_id':owner_id})
        return {'updated':len(leads)}
