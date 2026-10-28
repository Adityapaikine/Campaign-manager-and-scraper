"""Explicit local-server demo provisioning; never exposed as an unauthenticated RPC."""
import secrets
import uuid
from datetime import date,timedelta
from app.team.access import require,audit
from app.team.schema import transaction

CAMPAIGN_ID='DEMO-FLOW'
ACCOUNTS=[
    ('demo.ops.lead','Operations Lead','operations','Team Lead',None),
    ('demo.ops.employee','Operations Employee','operations','Employee','demo.ops.lead'),
    ('demo.quality.lead','Quality Lead','quality','Team Lead',None),
    ('demo.quality.employee','Quality Employee','quality','Employee','demo.quality.lead'),
    ('demo.delivery.lead','Delivery Lead','delivery','Team Lead',None),
    ('demo.delivery.employee','Delivery Employee','delivery','Employee','demo.delivery.lead'),
]


def sample_record(number):
    return {'First Name':f'Demo {number:02d}','Last Name':'Sample','Company Name':f'Demo Company {number:02d}',
        'Company Website':'example.com','Business Email ID':f'demo.flow.{number:02d}@example.com',
        'Prospect LinkedIn Link':f'https://www.linkedin.com/in/demo-flow-sample-{number:02d}',
        'Job Title':'Research Director','Country':'United States',
        'Comment':'DEMO DATA — fictional contact for workflow training; do not contact.'}


def create_demo(service):
    """Create one isolated campaign atomically through the normal validated operations.

    The command is for the trusted server operator with direct database access.
    It never reads, changes or resets an existing user's password or records.
    """
    with transaction(service.path) as db:
        admin=db.execute("SELECT * FROM team_users WHERE role='Super User' AND active=1 ORDER BY created_at,id LIMIT 1").fetchone()
        require(admin is not None,'Set up the initial Super User before creating demo accounts.',409)
        require(not db.execute('SELECT 1 FROM campaign_profiles WHERE campaign_id=?',(CAMPAIGN_ID,)).fetchone(),
                'DEMO-FLOW already exists. No accounts, passwords or leads were changed. Use the existing demo sign-in sheet.',409)
        for username,*_ in ACCOUNTS:
            require(not db.execute('SELECT 1 FROM team_users WHERE username=? COLLATE NOCASE OR email=? COLLATE NOCASE',(username,username+'@example.com')).fetchone(),
                    'A demo sign-in identity already exists. No accounts were changed.',409)
        for dept in ('operations','quality','delivery'):
            require(db.execute('SELECT 1 FROM team_departments WHERE id=? AND active=1',(dept,)).fetchone(),'The Operations, Quality and Delivery departments must be active.',409)
        today=date.today()
        service.op_campaign_save(db,admin,CAMPAIGN_ID,'DEMO · Operations → Quality → Delivery',{
            'client':'Fictional workflow training only','departments':['operations','quality','delivery'],
            'require_tal_match':False,'review_required':True,'allocation':12,'start_date':today.isoformat(),
            'end_date':(today+timedelta(days=6)).isoformat(),'status':'Running'})
        users={}; credentials=[]
        for username,label,dept,role,supervisor in ACCOUNTS:
            password=secrets.token_urlsafe(15)
            person=service.op_user_save(db,admin,full_name='DEMO · '+label,username=username,email=username+'@example.com',
                role=role,department_id=dept,team_lead_id=users[supervisor]['id'] if supervisor else None,password=password)
            users[username]=db.execute('SELECT * FROM team_users WHERE id=?',(person['id'],)).fetchone()
            credentials.append({'username':username,'password':password,'role':role,'department':dept})
            service.op_campaign_assign(db,admin,CAMPAIGN_ID,[person['id']])
            for key,value in {'last_campaign':CAMPAIGN_ID,'workspace_scope':'department' if role=='Team Lead' else 'mine',
                              'lead_last_view':'Workflow'}.items():
                service.op_preferences(db,users[username],key,value,True)
        # Reuse matching routes; fill a missing route only for the demo campaign.
        routes=[]
        for source,destination,required,arrival in [('operations','quality','Approved','Transferred to Quality'),
                                                   ('quality','delivery','Quality Qualified','Transferred to Delivery')]:
            existing=db.execute('SELECT id FROM team_routes WHERE active=1 AND (campaign_id IS NULL OR campaign_id=?) AND from_department=? AND to_department=? AND required_state=? AND arrival_state=?',
                (CAMPAIGN_ID,source,destination,required,arrival)).fetchone()
            routes.append(existing[0] if existing else service.op_policy_save(db,admin,'routes',{'campaign_id':CAMPAIGN_ID,'from_department':source,
                'to_department':destination,'required_state':required,'arrival_state':arrival,'active':1})['id'])
        ops=users['demo.ops.employee']; ops_lead=users['demo.ops.lead']; qa=users['demo.quality.employee']; qa_lead=users['demo.quality.lead']
        delivery_lead=users['demo.delivery.lead']; delivery=users['demo.delivery.employee']
        outcome=service.op_commit(db,ops,CAMPAIGN_ID,[sample_record(i) for i in range(1,11)],str(uuid.uuid4()),'DEMO training records')
        require(len(outcome['committed'])==10,'Demo sample records did not pass campaign validation. No demo changes were saved.',409)
        ids=[r['id'] for r in outcome['committed']]
        def selected(items):
            return [{'id':lid,'version':db.execute('SELECT version FROM team_leads WHERE id=?',(lid,)).fetchone()[0]} for lid in items]
        def stage(actor,items,state):service.op_transition(db,actor,selected(items),state)
        stage(ops,ids,'Pending Team Lead Review')
        approved=ids[:3]+ids[5:]; stage(ops_lead,approved,'Approved')
        service.op_transfer(db,ops_lead,selected(ids[5:]),routes[0],'DEMO: reviewed by Operations')
        service.op_assign(db,qa_lead,selected(ids[5:]),[qa['id']])
        stage(qa,ids[5:],'Quality In Progress'); stage(qa,ids[5:],'Quality Qualified')
        service.op_transfer(db,qa_lead,selected(ids[7:]),routes[1],'DEMO: qualified by Quality')
        service.op_assign(db,delivery_lead,selected(ids[9:]),[delivery['id']])
        stage(delivery_lead,ids[9:],'Delivery Approved'); stage(delivery,ids[9:],'Delivered')
        sheet=service.op_sheet_create(db,ops,CAMPAIGN_ID,'DEMO · Practice draft')
        service.op_sheet_save(db,ops,sheet['id'],1,{'records':[sample_record(11),sample_record(12)]})
        audit(db,admin,'demo-provision',CAMPAIGN_ID,details={'users':6,'leads':10,'draft_rows':2,'source':'trusted local server command'})
        return {'campaign_id':CAMPAIGN_ID,'accounts':credentials,'lead_ids':ids,'sheet_id':sheet['id']}


def credential_text(result):
    lines=['DEMO WORKFLOW SIGN-IN SHEET','Server: http://127.0.0.1:8765','Campaign: '+result['campaign_id'],
           'Synthetic training accounts. These accounts are assigned only to DEMO-FLOW.',
           'Open Start Lead Workspace.vbs for each sign-in. Keep this sheet private.',
           'Disable these accounts in Administration > Users after training.','',
           'Username\tPassword\tRole\tDepartment']
    lines.extend('\t'.join(r[k] for k in ('username','password','role','department')) for r in result['accounts'])
    return '\n'.join(lines)+'\n'
