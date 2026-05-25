import axios from 'axios';
import { prisma } from '../../lib/prisma.js';
import { redis } from '../../lib/redis.js';

export class ProxyRegistry {
  public async getTenantProxy(tenantId: string): Promise<string> {
    const tenant = await prisma.tenant.findUniqueOrThrow({ where: { id: tenantId } });
    const scoreKey = 'proxy:last_used';
    await redis.zadd(scoreKey, Date.now(), `${tenantId}:${tenant.proxyUrl}`);
    return tenant.proxyUrl;
  }

  public async rotateProxy(tenantId: string, replacementProxy: string): Promise<void> {
    await prisma.tenant.update({ where: { id: tenantId }, data: { proxyUrl: replacementProxy } });
    await redis.zadd('proxy:last_used', Date.now(), `${tenantId}:${replacementProxy}`);
  }

  public async healthCheck(): Promise<void> {
    const tenants = await prisma.tenant.findMany({ where: { isActive: true } });
    await Promise.all(
      tenants.map(async (tenant: { id: string; proxyUrl: string }) => {
        try {
          await axios.get('https://example.com', {
            proxy: false,
            headers: { 'x-tenant-proxy': tenant.proxyUrl },
            timeout: 5000
          });
          await redis.hset('proxy:health', tenant.id, 'healthy');
        } catch {
          await redis.hset('proxy:health', tenant.id, 'unhealthy');
        }
      })
    );
  }
}
