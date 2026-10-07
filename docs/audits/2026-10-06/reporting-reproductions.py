"""Verify two previously tracked reporting gaps using synthetic data only."""
import asyncio, os, json
from datetime import datetime, UTC
from unittest.mock import AsyncMock, patch
os.environ.update(ENVIRONMENT='test', JWT_SECRET='ci-only-jwt-secret-not-for-production-32-chars', MASTER_ADMIN_PASSWORD='audit-only-no-login', DRIVER_ENCRYPTION_KEY='CQVgdhGECQA3DfLOcuHbmFI-IzFspWiCkVfiz3NkUS4=', DATABASE_URL='sqlite+aiosqlite:////tmp/barpro-audit-unused.db', REDIS_URL='redis://127.0.0.1:6398/0', ALLOW_LIVE_SUBMIT='false')
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession
from app.api.routes import admin_reporting
from app.models_multitenant import Client, WaybillJob
from app.services.user_reporting_service import user_reporting_service
from app.core.jalali import tehran_day_start_utc, tehran_day_end_utc

async def main():
    app=FastAPI(); app.include_router(admin_reporting.router)
    app.dependency_overrides[admin_reporting.get_current_admin]=lambda:{'role':'master_admin'}
    app.dependency_overrides[admin_reporting.get_session]=lambda:AsyncMock()
    with patch('app.services.admin_reporting_service.async_session_factory',return_value=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://audit.local') as client:
            response=await client.get('/api/v1/admin/reports/failure-analysis',params={'date_from':'invalid-date'})
    assert response.status_code==500
    print(json.dumps({'case':'O5 invalid admin reporting date','http_status':response.status_code,'body':response.text}))
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    async with engine.begin() as conn: await conn.run_sync(SQLModel.metadata.create_all)
    factory=sessionmaker(engine,class_=AsyncSession,expire_on_commit=False)
    async with factory() as session:
        tenant=Client(client_code='AUDIT_REPORTING',name='Audit tenant',email='audit@example.invalid',hashed_password='unused',username='audit',full_name='Audit tenant')
        session.add(tenant); await session.flush()
        job=WaybillJob(job_id='audit-tehran-day',idempotency_key='audit-tehran-day',client_id=tenant.id,payload_json={},status='success',created_at=datetime(2026,10,5,21))
        session.add(job); await session.commit()
        class FrozenDateTime(datetime):
            @classmethod
            def now(cls,tz=None): return datetime(2026,10,6,1,tzinfo=UTC)
        with patch('app.services.user_reporting_service.datetime',FrozenDateTime):
            actual=await user_reporting_service.dashboard_stats(tenant,session)
        expected=(await session.exec(select(WaybillJob).where(WaybillJob.created_at>=tehran_day_start_utc('2026-10-06'),WaybillJob.created_at<tehran_day_end_utc('2026-10-06')))).all()
        assert actual['today_jobs']==0 and len(expected)==1
        print(json.dumps({'case':'O6 Tehran dashboard boundary','job_utc':'2026-10-05T21:00:00Z','job_tehran':'2026-10-06T00:30:00+03:30','dashboard_today_jobs':actual['today_jobs'],'tehran_day_jobs':len(expected),'transport':'real in-memory SQLite'}))
    await engine.dispose()

asyncio.run(main())
