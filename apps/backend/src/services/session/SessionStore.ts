import { env } from '../../config/env.js';
import { activeSessions } from '../../lib/metrics.js';
import { redis } from '../../lib/redis.js';

export type StoredSession = {
  cookies: Array<{ name: string; value: string; domain?: string; path?: string }>;
  proxy: string;
  lastAuthAt: string;
  sessionValid: boolean;
  userAgent: string;
};

export class SessionStore {
  private key(tenantId: string, driverId: string): string {
    return `session:${tenantId}:${driverId}`;
  }

  public async get(tenantId: string, driverId: string): Promise<StoredSession | null> {
    const raw = await redis.get(this.key(tenantId, driverId));
    return raw ? (JSON.parse(raw) as StoredSession) : null;
  }

  public async set(tenantId: string, driverId: string, session: StoredSession): Promise<void> {
    await redis.set(this.key(tenantId, driverId), JSON.stringify(session), 'EX', env.SESSION_TTL_SECONDS);
    activeSessions.labels(tenantId).inc();
  }

  public async extend(tenantId: string, driverId: string): Promise<void> {
    await redis.expire(this.key(tenantId, driverId), env.SESSION_TTL_SECONDS);
  }

  public async ttl(tenantId: string, driverId: string): Promise<number> {
    return redis.ttl(this.key(tenantId, driverId));
  }

  public async delete(tenantId: string, driverId: string): Promise<void> {
    await redis.del(this.key(tenantId, driverId));
    activeSessions.labels(tenantId).dec();
  }
}
