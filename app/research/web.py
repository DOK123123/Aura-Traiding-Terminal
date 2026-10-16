"""Local-only workbench app; no terminal lifespan, Paper, Supabase or scheduler."""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from .api import router,instance
from .service import Service
from .persistence import configured_store

ROOT=Path(__file__).resolve().parents[2]
app=FastAPI(title='Aura isolated Research Workbench')
app.include_router(router)

def workbench():
    from fastapi import HTTPException,Depends
    try:
        store=configured_store(writable=True)
        if store is None:raise ValueError()
        return Service(ROOT,store=store,writable=True)
    except Exception:raise HTTPException(503,'Configure isolated durable Research storage.') from None

# instance dependency already includes owner auth. Override retains an explicit owner dep.
from fastapi import Depends
from app.lab.api import owner

def authenticated_workbench(_=Depends(owner)):return workbench()
app.dependency_overrides[instance]=authenticated_workbench

@app.get('/api/health')
def health():return dict(status='ok',research_only=True,worker_dispatch=False)

@app.get('/')
def root():return RedirectResponse('/static/research.html')

app.mount('/static',StaticFiles(directory=ROOT/'static'),name='research-static')

if __name__=='__main__':
    if os.getenv('RENDER'):raise SystemExit('RESEARCH_LOCAL_WORKBENCH_REQUIRED')
    import uvicorn
    uvicorn.run('app.research.web:app',host='127.0.0.1',port=8001,workers=1)
