"""Public market analysis only. GET cannot control PAPER or read an account."""
from fastapi import APIRouter,Request
from fastapi.responses import JSONResponse

router=APIRouter(prefix='/api/analyst',tags=['Aura Analyst · manual read-only'])


@router.get('')
async def analyst(request:Request):
    service=request.app.state.aura_analyst
    return JSONResponse(await service.inspect(),headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
