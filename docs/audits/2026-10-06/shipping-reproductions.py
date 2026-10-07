"""Read-only functional audit: real shipping selector, mocked database transport."""
import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.update(ENVIRONMENT='test', JWT_SECRET='ci-only-jwt-secret-not-for-production-32-chars', MASTER_ADMIN_PASSWORD='audit-only-no-login', DRIVER_ENCRYPTION_KEY='CQVgdhGECQA3DfLOcuHbmFI-IzFspWiCkVfiz3NkUS4=', DATABASE_URL='sqlite+aiosqlite:///:memory:', REDIS_URL='redis://127.0.0.1:6398/0', ALLOW_LIVE_SUBMIT='false')
from app.automation import gps_shipping_manager as gps
from sqlalchemy.dialects import postgresql

async def main():
    now=datetime(2026,10,6,9,tzinfo=UTC)
    rows=[]
    for n in range(51):
        state=gps.ShippingState(job_id=f'audit-shipping-{n}',status='in_transit',estimated_end_at=(now+timedelta(days=1) if n<50 else now-timedelta(hours=1)).isoformat())
        rows.append(SimpleNamespace(job_id=state.job_id,result_json={'_shipping_state':state.to_dict()}))
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): return None
        async def exec(self,query):
            self.last_sql=str(query.compile(dialect=postgresql.dialect(),compile_kwargs={'literal_binds':True}))
            return SimpleNamespace(all=lambda:rows[:query._limit_clause.value])
    session=Session()
    with patch.object(gps,'_get_redis',AsyncMock(return_value=None)), patch('app.core.database.async_session_factory',return_value=session):
        first=await gps.get_due_in_transit_jobs(now)
        second=await gps.get_due_in_transit_jobs(now)
        actual_sql=session.last_sql
        with patch.object(gps,'DUE_SCAN_DB_LIMIT',51):
            control=await gps.get_due_in_transit_jobs(now)
    assert first==second==[]
    assert [s.job_id for s in control]==['audit-shipping-50']
    print(json.dumps({'case':'DB fallback starvation','available_in_transit':51,'due_rows':1,'normal_tick_1':len(first),'normal_tick_2':len(second),'control_limit_51':[s.job_id for s in control],'database_transport':'mock honors actual SQL limit; PostgreSQL server unavailable'},indent=2))
    print(actual_sql[actual_sql.index('FROM '):])

asyncio.run(main())
