import { JobStatus } from '@prisma/client';
import { prisma } from '../lib/prisma.js';
import { logger } from '../lib/logger.js';
import { JobProducer } from './job-producer.js';

export class FairScheduler {
  public constructor(private readonly producer: JobProducer) {}

  public async dispatchPending(limit = 500): Promise<number> {
    const pending = await prisma.job.findMany({
      where: { status: JobStatus.PENDING },
      include: { driver: true },
      orderBy: [{ createdAt: 'asc' }],
      take: limit
    });

    const byTenant = new Map<string, typeof pending>();
    for (const job of pending) {
      const existing = byTenant.get(job.tenantId) ?? [];
      existing.push(job);
      byTenant.set(job.tenantId, existing);
    }

    let dispatched = 0;
    let madeProgress = true;

    while (madeProgress) {
      madeProgress = false;
      for (const [tenantId, jobs] of byTenant) {
        const next = jobs.shift();
        if (!next) {
          continue;
        }
        madeProgress = true;
        dispatched += 1;
        await prisma.job.update({ where: { id: next.id }, data: { status: JobStatus.PROCESSING, queueName: 'submit' } });
        await this.producer.enqueueSubmit({
          tenantId,
          driverId: next.driverId,
          jobId: next.id,
          correlationId: next.id,
          idempotencyKey: next.idempotencyKey
        });
      }
    }

    logger.info({ dispatched }, 'Fair scheduler dispatched pending jobs');
    return dispatched;
  }
}
