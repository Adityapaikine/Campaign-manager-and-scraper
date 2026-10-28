"""Run on the trusted server PC only. Never distribute its Data folder."""
import argparse
import getpass
from pathlib import Path
from suite_bootstrap import configure
configure()

def setup_super_user(service):
    """Validate interactive input before provisioning; never print passwords."""
    from app.team.access import ServiceError
    from app.team.admin import validate_password
    from app.team.schema import transaction
    with transaction(service.path,False) as db:
        if db.execute('SELECT 1 FROM team_users').fetchone():
            print('A Super User has already been provisioned. Sign in with your existing account. No account was changed.')
            return False
    try:
        while True:
            name=input('Super User full name: ').strip(); username=input('Username: ').strip(); email=input('Email: ').strip()
            if all(0<len(x)<=150 for x in (name,username,email)) and '@' in email and not any(c.isspace() for c in username):break
            print('Enter a full name, a username without spaces, and an email address (maximum 150 characters each). Please try again.')
        while True:
            password=getpass.getpass('Password (12–256 characters): ')
            try:validate_password(password)
            except ServiceError as exc:
                print(str(exc)+' Please try again.'); continue
            if getpass.getpass('Confirm password: ')!=password:
                print('Passwords did not match. Please try again.'); continue
            try:service.bootstrap(name,username,email,password)
            except ServiceError as exc:
                print(str(exc)+' No account was changed.'); return False
            return True
    except (EOFError,KeyboardInterrupt):
        print('\nSetup canceled. No account was created.'); return False

def main():
    from app.utils.config import DB_PATH
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['setup','serve','check','adopt-legacy','backup','create-demo'])
    parser.add_argument('--database',type=Path,default=DB_PATH)
    parser.add_argument('--host',default='127.0.0.1'); parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--cert'); parser.add_argument('--key')
    parser.add_argument('--workspace-folder',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.command=='serve':
        if args.host not in ('127.0.0.1','localhost','::1') and not (args.cert and args.key):
            parser.error('Remote access requires --cert and --key. Keep the database on this PC and restrict its folder access.')
        import uvicorn
        from app.team.api import create_app
        uvicorn.run(create_app(args.database),host=args.host,port=args.port,ssl_certfile=args.cert,ssl_keyfile=args.key,
                    access_log=False,limit_concurrency=50,timeout_keep_alive=5)
    else:
        from app.team.service import Service
        from app.team.schema import transaction
        if args.command=='backup':
            from app.team.legacy import backup_database
            if not args.output:parser.error('Supply --output with a new backup filename.')
            print(backup_database(args.database,args.output))
        elif args.command=='create-demo':
            from app.team.demo import create_demo,credential_text
            from app.team.legacy import backup_database
            from app.team.access import ServiceError
            from datetime import datetime
            output=args.output or args.database.parent.parent/'demo-accounts.txt'
            if output.exists():parser.error('The demo credential file already exists. It will not be overwritten.')
            output.parent.mkdir(parents=True,exist_ok=True)
            backup=args.database.with_name('before-demo-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3')
            backup_database(args.database,backup)
            try:result=create_demo(Service(args.database))
            except ServiceError as exc:raise SystemExit(str(exc))
            output.write_text(credential_text(result),encoding='utf-8')
            print('Created six demo accounts, ten sample leads and a two-row private draft in DEMO-FLOW.')
            print('Sign-in sheet:',output)
            print('Pre-demo database backup:',backup)
        elif args.command=='adopt-legacy':
            from app.team.legacy import adopt_workspaces,backup_database
            from app.utils.config import DATA_DIR
            from datetime import datetime
            backup_database(args.database,args.database.with_name('before-adoption-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3'))
            print(adopt_workspaces(args.database,args.workspace_folder or DATA_DIR/'workspaces'))
            from app.team.mode import enable_shared_mode
            enable_shared_mode(args.database)
            print('All shortcuts open Lead Workspace with research and shared operations in one window.')
        elif args.command=='setup':
            service=Service(args.database)
            if not setup_super_user(service):return
            from app.team.mode import enable_shared_mode
            enable_shared_mode(args.database)
            print('Super User created. Start the server, then sign in to Lead Workspace.')
        else:
            Service(args.database)
            with transaction(args.database,False) as db:
                print('Integrity:',db.execute('PRAGMA integrity_check').fetchone()[0])
                print('Provisioned:',bool(db.execute('SELECT 1 FROM team_users').fetchone()))
                print('Schema:',db.execute('SELECT max(version) FROM team_migrations').fetchone()[0])

if __name__=='__main__': main()
