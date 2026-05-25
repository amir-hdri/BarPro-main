import { JobStatus } from '@prisma/client';
import { env } from '../config/env.js';
import { JobFailureCode } from '../domain/enums.js';
import { jobsFailedTotal, jobsProcessedTotal } from '../lib/metrics.js';
import { prisma } from '../lib/prisma.js';
import { buildWorker, queueNames, type SubmitJobData } from '../queues/bullmq.js';
import { JobProducer } from '../queues/job-producer.js';
import { TenantRateLimiter } from '../queues/tenant-rate-limiter.js';
import { logger } from '../lib/logger.js';
import { ProxyRegistry } from '../services/proxy/ProxyRegistry.js';
import { SessionStore } from '../services/session/SessionStore.js';
import { LegacyPortalSubmitService } from '../services/submit/LegacyPortalSubmitService.js';

const producer = new JobProducer();
const rateLimiter = new TenantRateLimiter();
const sessionStore = new SessionStore();
const submitService = new LegacyPortalSubmitService(sessionStore);
const proxyRegistry = new ProxyRegistry();

export const submitWorker = buildWorker<SubmitJobData>(queueNames.submit, async (job) => {
  await rateLimiter.consume(job.data.tenantId);

  const dbJob = await prisma.job.findUniqueOrThrow({ where: { id: job.data.jobId } });
  const ttl = await sessionStore.ttl(job.data.tenantId, job.data.driverId);
  if (ttl > 0 && ttl < env.SESSION_REFRESH_THRESHOLD_SECONDS) {
    await producer.enqueueAuth({
      tenantId: job.data.tenantId,
      driverId: job.data.driverId,
      correlationId: job.data.correlationId,
      attempt: 0,
      reason: 'proactive_refresh',
      jobId: job.data.jobId
    });
  }

  const result = await submitService.submit(job.data.tenantId, job.data.driverId, dbJob.payload as Record<string, unknown>);

  if (result.kind === 'success') {
    await prisma.$transaction([
      prisma.job.update({ where: { id: job.data.jobId }, data: { status: JobStatus.SUCCESS, completedAt: new Date(), lastError: null } }),
      prisma.driver.update({ where: { id: job.data.driverId }, data: { dailyAttempts: { increment: 1 }, dailySuccesses: { increment: 1 } } })
    ]);
    jobsProcessedTotal.labels('submit', 'success').inc();
    return;
  }

  await prisma.driver.update({ where: { id: job.data.driverId }, data: { dailyAttempts: { increment: 1 } } });

  if (result.kind === 'reauth') {
    await prisma.job.update({ where: { id: job.data.jobId }, data: { status: JobStatus.WAITING_AUTH, lastError: result.code } });
    await producer.enqueueAuth({
      tenantId: job.data.tenantId,
      driverId: job.data.driverId,
      correlationId: job.data.correlationId,
      attempt: 0,
      reason: 'session_refresh',
      jobId: job.data.jobId
    });
    jobsFailedTotal.labels('submit', result.code).inc();
    return;
  }

  if (result.kind === 'retry') {
    const attempts = dbJob.attempts + 1;
    const isDead = attempts >= dbJob.maxAttempts;
    await prisma.job.update({
      where: { id: job.data.jobId },
      data: {
        attempts,
        status: isDead ? JobStatus.DEAD : JobStatus.RETRY_SCHEDULED,
        lastError: result.detail,
        queueName: isDead ? 'dead-letter' : 'retry'
      }
    });

    if (result.code === JobFailureCode.PROXY_BANNED) {
      await sessionStore.delete(job.data.tenantId, job.data.driverId);
      await proxyRegistry.rotateProxy(job.data.tenantId, `http://rotated-${Date.now()}.proxy.local:8080`);
      await producer.enqueueAuth({
        tenantId: job.data.tenantId,
        driverId: job.data.driverId,
        correlationId: job.data.correlationId,
        attempt: 0,
        reason: 'session_refresh',
        jobId: job.data.jobId
      });
    }

    if (isDead) {
      await producer.moveToDeadLetter({
        tenantId: job.data.tenantId,
        driverId: job.data.driverId,
        jobId: job.data.jobId,
        correlationId: job.data.correlationId,
        code: result.code,
        detail: result.detail
      });
    } else {
      await producer.enqueueRetry({
        target: 'submit',
        tenantId: job.data.tenantId,
        driverId: job.data.driverId,
        correlationId: job.data.correlationId,
        payload: job.data
      }, env.SUBMIT_RETRY_DELAY_MS);
    }
    jobsFailedTotal.labels('submit', result.code).inc();
    return;
  }

  await prisma.job.update({
    where: { id: job.data.jobId },
    data: { status: JobStatus.FAILED, attempts: { increment: 1 }, lastError: result.detail }
  });
  jobsFailedTotal.labels('submit', result.code).inc();
  if (dbJob.attempts + 1 >= dbJob.maxAttempts) {
    await producer.moveToDeadLetter({
      tenantId: job.data.tenantId,
      driverId: job.data.driverId,
      jobId: job.data.jobId,
      correlationId: job.data.correlationId,
      code: result.code,
      detail: result.detail
    });
  }
}, env.SUBMIT_QUEUE_CONCURRENCY);

submitWorker.on('completed', () => logger.info('Submit worker job completed'));
submitWorker.on('failed', (_job, error) => logger.error({ error }, 'Submit worker job failed'));
