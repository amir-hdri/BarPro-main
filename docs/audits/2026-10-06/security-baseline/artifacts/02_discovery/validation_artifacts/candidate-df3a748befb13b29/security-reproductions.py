"""Synthetic HTTP/SQLite/Redis validation of the immutable audit baseline."""
import asyncio, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,os.environ.get('BARPRO_AUDIT_SOURCE_ROOT',str(ROOT)))
os.environ.update(ENVIRONMENT='test',JWT_SECRET='audit-only-synthetic-jwt-key-32bytes',MASTER_ADMIN_PASSWORD='audit-only-no-login',DRIVER_ENCRYPTION_KEY='CQVgdhGECQA3DfLOcuHbmFI-IzFspWiCkVfiz3NkUS4=',DATABASE_URL='sqlite+aiosqlite:////tmp/barpro-security-unused.db',REDIS_URL='redis://127.0.0.1:1/0',ALLOW_LIVE_SUBMIT='false')
import redis.asyncio as aioredis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from app.api.routes import otp_forwarder as route
from app.services import otp_wakeup_consumer as consumer
from app.automation.otp_keys import otp_phone_key,otp_pending_phone_key
from app.models_multitenant import Client,WaybillJob

async def main():
 with tempfile.TemporaryDirectory(prefix='barpro-security-repro-') as folder:
  socket=str(Path(folder)/'redis.sock')
  with open(Path(folder)/'redis.log','w') as out:
   proc=subprocess.Popen([shutil.which('redis-server'),'--port','0','--unixsocket',socket,'--save','','--appendonly','no','--dir',folder],stdout=out,stderr=subprocess.STDOUT)
   redis=None
   engine=create_async_engine('sqlite+aiosqlite:///:memory:')
   try:
    for _ in range(100):
     if Path(socket).exists(): break
     await asyncio.sleep(.02)
    redis=aioredis.Redis(unix_socket_path=socket,decode_responses=True)
    async with engine.begin() as conn: await conn.run_sync(SQLModel.metadata.create_all)
    factory=sessionmaker(engine,class_=AsyncSession,expire_on_commit=False)
    async with factory() as session:
     clients=[Client(client_code=f'AUDIT_{n}',name=f'Audit {n}',email=f'audit{n}@example.invalid',username=f'audit{n}',full_name=f'Audit {n}',hashed_password='unused') for n in (1,2)]
     session.add_all(clients); await session.flush()
     for n,tenant in enumerate(clients):
      session.add(WaybillJob(job_id=f'audit-job-{n}',idempotency_key=f'audit-job-{n}',client_id=tenant.id,status='success' if n==0 else 'unknown',payload_json={'driver_phone':f'0912000000{n}'},result_json={'document_id':str(991+n),'tracking_code':'99100001' if n==0 else ''}))
     await session.commit()
    victim='09120000001'
    keys=[otp_phone_key(victim),otp_pending_phone_key(victim)]
    await redis.set(keys[0],'synthetic-victim-otp'); await redis.set(keys[1],'audit-job-1')
    app=FastAPI(); app.include_router(route.router)
    app.dependency_overrides[route.get_current_user_or_admin]=lambda:{'role':'client','user':clients[0]}
    with patch.object(route,'async_session_factory',factory),patch.object(consumer,'async_session_factory',factory),patch.object(route.redis_manager,'get',AsyncMock(return_value=redis)),patch.object(route.utcms_config,'OTP_WEBHOOK_SECRET','audit-query-synthetic-token'):
     async with AsyncClient(transport=ASGITransport(app=app),base_url='http://audit.local') as client:
      response=await client.post('/api/v1/otp/submit-manual',json={'job_id':'audit-job-0','phone':victim,'code':'12345'})
      for _ in range(100):
       if not await redis.exists(keys[0]): break
       await asyncio.sleep(.01)
      remaining=[await redis.exists(k) for k in keys]
      assert response.status_code==200 and remaining==[0,0]
      print(json.dumps({'case':'owned_success_job_deletes_other_tenant_otp','http_status':response.status_code,'caller_tenant':clients[0].id,'victim_tenant':clients[1].id,'victim_keys_before':2,'victim_keys_after':sum(remaining),'utc_ms_calls':0}))
      query=await client.post('/api/v1/otp/sms-forwarder?token=audit-query-synthetic-token',json={'event':'HEALTH_CHECK'})
      assert query.status_code==200
      nginx=(ROOT/'infra/nginx/nginx.conf').read_text()
      assert '$request' in nginx and 'access_log /var/log/nginx/access.log json_combined' in nginx
      print(json.dumps({'case':'query_auth_reaches_unredacted_request_log_format','http_status':query.status_code,'credential_location':'query string','nginx_logs_request_line':True,'actual_nginx_runtime':'not launched; committed config trace'}))
   finally:
    await engine.dispose()
    if redis is not None: await redis.aclose()
    proc.terminate(); proc.wait(timeout=5)

asyncio.run(main())
