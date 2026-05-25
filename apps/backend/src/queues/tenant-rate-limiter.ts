import { env } from '../config/env.js';
import { redis } from '../lib/redis.js';

export class TenantRateLimiter {
  public async consume(tenantId: string): Promise<void> {
    const key = `tenant:${tenantId}:rate`;
    const current = await redis.incr(key);
    if (current === 1) {
      await redis.pexpire(key, 1000);
    }
    if (current > env.TENANT_MAX_RPS) {
      throw new Error(`Tenant ${tenantId} exceeded ${env.TENANT_MAX_RPS} rps`);
    }
  }
}
