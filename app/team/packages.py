import base64
import io
import json
from pathlib import Path,PurePosixPath
import uuid
import zipfile
from app.team.access import require,audit
from app.core.campaign_manager import CampaignPackageImporter


class Packages:
    def op_legacy_snapshots(self,db,user,source_key=None):
        require(user['role']=='Super User')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='team_legacy_payloads'").fetchone():return []
        if source_key is not None:
            source=db.execute('SELECT * FROM team_legacy_payloads WHERE source_key=?',(source_key,)).fetchone()
            require(source is not None,'Historical worksheet unavailable.',404)
            payload=json.loads(source['payload_json'])
            require(len(payload.get('records',[]))<=5000,'This historical sheet exceeds the private sheet limit; export/reconcile it on the server.',409)
            sheet=self.op_sheet_create(db,user,source['campaign_id'],'Historical worksheet copy')
            saved=self.op_sheet_save(db,user,sheet['id'],1,payload)
            audit(db,user,'legacy-sheet-recovery',source_key)
            return {'sheet_id':sheet['id'],'campaign_id':source['campaign_id'],'version':saved['version']}
        return [{'source_key':r['source_key'],'campaign_id':r['campaign_id'],'rows':len(json.loads(r['payload_json']).get('records',[])),
                 'formulas':len(json.loads(r['payload_json']).get('formulas',[]))} for r in db.execute('SELECT * FROM team_legacy_payloads')]

    def op_campaign_package(self,db,user,filename,content):
        require(user['role']=='Super User')
        require(isinstance(filename,str) and Path(filename).name==filename and filename.lower().endswith('.zip') and len(filename)<=150,'Choose a campaign ZIP filename.',400)
        require(isinstance(content,str) and len(content)<=14_000_000,'ZIP uploads are limited to 10 MB.',400)
        try:raw=base64.b64decode(content,validate=True)
        except ValueError:raise ValueError('Invalid ZIP encoding.')
        require(zipfile.is_zipfile(io.BytesIO(raw)),'The uploaded file is not a valid ZIP archive.',400)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members=archive.infolist()
            require(len(members)<=500 and sum(m.file_size for m in members)<=100_000_000,'Campaign package expands beyond its 100 MB / 500 file limit.',400)
            for member in members:
                path=PurePosixPath(member.filename.replace('\\','/'))
                require(not path.is_absolute() and '..' not in path.parts and ':' not in str(path) and (member.external_attr>>16)&0o170000!=0o120000,'Unsafe campaign archive path.',400)
        folder=Path(self.path).parent/'team_campaign_files'/str(uuid.uuid4()); folder.mkdir(parents=True)
        source=folder/filename; source.write_bytes(raw)
        class Store:
            def save(self,profile):
                require(not db.execute('SELECT 1 FROM campaign_profiles WHERE campaign_id=?',(profile.campaign_id,)).fetchone(),'This CID already exists. Edit its configuration instead of replacing its package.',409)
                db.execute('INSERT INTO campaign_profiles(campaign_id,campaign_name,source_root,payload_json) VALUES(?,?,?,?)',(profile.campaign_id,profile.campaign_name,profile.source_root,json.dumps(profile.to_dict())))
        profile=CampaignPackageImporter(store=Store(),folder=folder/'extracted').import_package(source)
        audit(db,user,'campaign-package',profile.campaign_id,details={'files':len(profile.files)})
        return {'campaign_id':profile.campaign_id,'campaign_name':profile.campaign_name,'files':len(profile.files),'rules_to_review':sum(r.status=='Needs Review' for r in profile.rules)}

    def op_campaign_rules(self,db,user,campaign_id,index=None,status=None):
        require(user['role']=='Super User')
        row=db.execute('SELECT payload_json FROM campaign_profiles WHERE campaign_id=?',(campaign_id,)).fetchone()
        require(row is not None,'Campaign unavailable.',404)
        payload=json.loads(row[0]); rules=payload.get('rules',[])
        if index is not None:
            require(isinstance(index,int) and 0<=index<len(rules) and status in ('Confirmed','Needs Review','Rejected'),'Invalid rule review.',400)
            old=rules[index].get('status'); rules[index]['status']=status
            db.execute('UPDATE campaign_profiles SET payload_json=?,updated_at=CURRENT_TIMESTAMP WHERE campaign_id=?',(json.dumps(payload),campaign_id))
            audit(db,user,'campaign-rule-review',campaign_id,details={'index':index,'old':old,'new':status})
        return [{'index':i,**r} for i,r in enumerate(rules)]
