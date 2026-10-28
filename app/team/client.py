"""HTTP-only client. Session tokens never go to disk or URLs."""
from urllib.parse import urlsplit
import httpx
import ssl
import os
from app.team.access import ServiceError

class TeamClient:
    def __init__(self,url='http://127.0.0.1:8765',*,transport=None):
        parts=urlsplit(url)
        if parts.scheme not in ('http','https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
            raise ValueError('Enter a valid server URL without credentials.')
        if parts.scheme!='https' and parts.hostname not in ('127.0.0.1','localhost','::1'):
            raise ValueError('Connections to another computer require HTTPS.')
        self.url=url.rstrip('/'); self.token=None; self.user=None
        context=ssl.create_default_context()
        if os.getenv('LEAD_TEAM_CA_FILE'):context.load_verify_locations(cafile=os.environ['LEAD_TEAM_CA_FILE'])
        self.http=httpx.Client(base_url=self.url,timeout=90,follow_redirects=False,transport=transport,trust_env=False,verify=context)

    def _post(self,path,data):
        try: response=self.http.post(path,json=data,headers={'Authorization':'Bearer '+self.token} if self.token else {})
        except httpx.HTTPError as exc: raise ServiceError('Cannot reach the shared server. Your pending draft remains open; reconnect and retry.',503) from exc
        if response.status_code>=400:
            try: message=response.json().get('error','Request failed.')
            except ValueError: message='The server returned an invalid response.'
            if response.status_code==401: self.token=None; self.user=None
            raise ServiceError(message,response.status_code)
        return response.json()

    def login(self,username,password):
        result=self._post('/login',{'username':username,'password':password})
        self.token=result['token']; self.user=result['user']; return result

    def call(self,operation,**args):
        if not self.token: raise ServiceError('Sign in to continue.',401)
        return self._post('/rpc/'+operation,args)

    def logout(self):
        try:
            if self.token: self.call('logout')
        finally: self.token=None; self.user=None
