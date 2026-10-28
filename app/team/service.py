"""All public operations authenticate and authorize inside a database transaction."""
import hashlib
import json
import re
import secrets
import sqlite3
import time
import uuid
from argon2.exceptions import VerificationError, InvalidHashError
from app.team.access import ServiceError, require, public_user, audit, permission_cache
from app.team.admin import Administration, PASSWORDS, password_hash
from app.team.schema import migrate, transaction
from app.team.leads import LeadOperations
from app.team.sheets import Worksheets
from app.team.workflow import Workflow
from app.team.reporting import Reporting
from app.team.research import Research
from app.team.packages import Packages
from app.team.modules import ModulePermissions, OPERATION_MODULES, require_module

class Service(ModulePermissions, Administration, LeadOperations, Worksheets, Workflow, Reporting, Research, Packages):
    def __init__(self,path):
        self.path=path
        migrate(path)
        self._dummy=PASSWORDS.hash(secrets.token_urlsafe(32))

    def bootstrap(self,full_name,username,email,password):
        hashed=password_hash(password)
        require(all(isinstance(x,str) and 0<len(x.strip())<=150 for x in (full_name,username,email)) and '@' in email,'Enter valid account details.',400)
        with transaction(self.path) as db:
            require(not db.execute('SELECT 1 FROM team_users').fetchone(),'A Super User has already been provisioned.',409)
            uid=str(uuid.uuid4())
            db.execute("INSERT INTO team_users(id,full_name,username,email,password_hash,role) VALUES(?,?,?,?,?,'Super User')",(uid,full_name.strip(),username.strip(),email.strip().lower(),hashed))
            audit(db,{'id':uid},'initial-provision',uid)
            return uid

    def login(self,username,password,peer='local'):
        require(isinstance(username,str) and isinstance(password,str) and len(username)<=150 and len(password)<=256,'Invalid credentials.',401)
        key=hashlib.sha256((username.strip().casefold()+'|'+peer).encode()).hexdigest()
        failed=False; now=time.time()
        with transaction(self.path) as db:
            attempt=db.execute('SELECT * FROM team_login_attempts WHERE key=?',(key,)).fetchone()
            require(not attempt or attempt['blocked_until']<=now,'Too many attempts. Try again later.',429)
            user=db.execute('SELECT * FROM team_users WHERE username=? COLLATE NOCASE OR email=? COLLATE NOCASE',(username.strip(),username.strip())).fetchone()
            try: valid=PASSWORDS.verify(user['password_hash'] if user else self._dummy,password)
            except (VerificationError,InvalidHashError): valid=False
            if not user or not user['active'] or not valid:
                failures=(attempt['failures'] if attempt else 0)+1
                db.execute('INSERT INTO team_login_attempts VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET failures=excluded.failures,blocked_until=excluded.blocked_until',(key,failures,now+min(900,30*2**min(5,failures-5)) if failures>=5 else 0))
                audit(db,None,'login',outcome='denied'); failed=True
            else:
                db.execute('DELETE FROM team_login_attempts WHERE key=?',(key,))
                if PASSWORDS.check_needs_rehash(user['password_hash']): db.execute('UPDATE team_users SET password_hash=? WHERE id=?',(PASSWORDS.hash(password),user['id']))
                token=secrets.token_urlsafe(48); expires=now+8*3600
                db.execute('DELETE FROM team_sessions WHERE expires<?',(now,))
                db.execute('INSERT INTO team_sessions(hash,user_id,expires) VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user['id'],expires))
                db.execute('UPDATE team_users SET last_login=CURRENT_TIMESTAMP WHERE id=?',(user['id'],))
                audit(db,user,'login')
                result={'token':token,'expires':expires,'user':public_user(user)}
        if failed: raise ServiceError('Invalid credentials or inactive account.',401)
        return result

    def authenticate(self,db,token):
        require(isinstance(token,str) and 20<=len(token)<=200,'Sign in to continue.',401)
        row=db.execute('SELECT u.* FROM team_sessions s JOIN team_users u ON u.id=s.user_id WHERE s.hash=? AND s.expires>? AND u.active=1',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
        require(row is not None,'Your session expired or was revoked. Sign in again.',401)
        return row

    def call(self,token,operation,args=None):
        require(isinstance(operation,str) and re.fullmatch('[a-z_]{1,40}',operation),'Unknown operation.',404)
        method=getattr(self,'op_'+operation,None)
        require(callable(method),'Unknown operation.',404)
        user=None
        cache_token=permission_cache.set({})
        try:
            readonly={'me','directory','campaigns','policy','leads','lead','history','transfer_history','sheets','dashboard','report','field_access','workflow_options','selection_actions','assignment_options','audit','modules','module_check','module_policy'}
            with transaction(self.path,write=operation not in readonly) as db:
                user=self.authenticate(db,token)
                require(operation in OPERATION_MODULES, 'Unknown operation.', 404)
                for module in OPERATION_MODULES[operation]: require_module(db,user,module)
                if operation=='preferences' and (args or {}).get('save') and (args or {}).get('key')=='app_settings':
                    require_module(db,user,'settings')
                return method(db,user,**(args or {}))
        except ServiceError as exc:
            if user and exc.status in (403,404):
                with transaction(self.path) as db: audit(db,user,operation,outcome='denied')
            raise
        except sqlite3.IntegrityError as exc:
            raise ServiceError('The change conflicts with an existing record or relationship. Refresh and check the values.',409) from exc
        finally:permission_cache.reset(cache_token)

    def op_me(self,db,user): return public_user(user)

    def op_logout(self,db,user):
        db.execute('DELETE FROM team_sessions WHERE user_id=?',(user['id'],))
        audit(db,user,'logout'); return {'logged_out':True}

    def op_change_password(self,db,user,current_password,new_password):
        try: valid=PASSWORDS.verify(user['password_hash'],current_password)
        except (VerificationError,InvalidHashError): valid=False
        require(valid,'Current password is incorrect.',403)
        db.execute('UPDATE team_users SET password_hash=? WHERE id=?',(password_hash(new_password),user['id']))
        db.execute('DELETE FROM team_sessions WHERE user_id=?',(user['id'],))
        audit(db,user,'password-change'); return {'sign_in_again':True}
