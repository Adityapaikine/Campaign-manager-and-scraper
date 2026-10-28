"""A bounded authenticated API. It never exposes database or workspace files."""
import json
import sqlite3
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from app.team.service import Service
from app.team.access import ServiceError

MAX_BODY=16_000_000

def create_app(path):
    service=Service(path)
    app=FastAPI(title='Lead Workspace service',docs_url=None,redoc_url=None,openapi_url=None)
    app.state.service=service

    @app.middleware('http')
    async def bounded_body(request,call_next):
        # No cookies/CORS: the desktop uses an in-memory bearer token.
        if request.method=='POST':
            chunks=[]; size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>MAX_BODY: return JSONResponse({'error':'Request too large.'},status_code=413)
                chunks.append(chunk)
            request._body=b''.join(chunks)
        response=await call_next(request)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request,exc): return JSONResponse({'error':str(exc)},status_code=exc.status)

    async def body(request):
        try: value=await request.json()
        except (ValueError,UnicodeError): raise ServiceError('Invalid JSON.',400)
        if not isinstance(value,dict): raise ServiceError('Expected an object.',400)
        return value

    @app.get('/health')
    def health(): return {'status':'ok','service':'Lead Workspace','schema':4}

    @app.post('/login')
    async def login(request:Request):
        data=await body(request)
        return await run_in_threadpool(service.login,data.get('username',''),data.get('password',''),request.client.host if request.client else 'unknown')

    @app.post('/rpc/{operation}')
    async def rpc(operation:str,request:Request):
        auth=request.headers.get('Authorization','')
        if not auth.startswith('Bearer '): raise ServiceError('Sign in to continue.',401)
        data=await body(request)
        try: return await run_in_threadpool(service.call,auth[7:],operation,data)
        except (TypeError,KeyError,ValueError): raise ServiceError('Invalid operation arguments.',400)
        except sqlite3.OperationalError: raise ServiceError('The database is busy or unavailable. No partial change was saved; retry after refreshing.',503)
    return app
