import { JobStatus } from '@prisma/client';
import { env } from '../config/env.js';
import { authLatencySeconds, jobsFailedTotal, jobsProcessedTotal } from '../lib/metrics.js';
import { prisma } from '../lib/prisma.js';
import { buildWorker, queueNames, type AuthJobData } from '../queues/bullmq.js';
import { JobProducer } from '../queues/job-producer.js';
import { TwoCaptchaService } from '../services/captcha/TwoCaptchaService.js';
import { LegacyPortalAuthService } from '../services/auth/LegacyPortalAuthService.js';
import { ProxyRegistry } from '../services/proxy/ProxyRegistry.js';
import { SessionStore } from '../services/session/SessionStore.js';
import { logger } from '../lib/logger.js';

const producer = new JobProducer();
const captchaService = new TwoCaptchaService();
const authService = new LegacyPortalAuthService(captchaService, new ProxyRegistry(), new SessionStore());

function exponentialBackoff(attempt: number): number {
  const base = env.AUTH_RETRY_BASE_MS * 2 ** Math.max(0, attempt - 1);
  const capped = Math.min(base, env.AUTH_RETRY_MAX_MS);
  const jitter = Math.round(Math.random() * 1000);
  return capped + jitter;
}

export const authWorker = buildWorker<AuthJobData>(
  queueNames.auth,
  async (job) => {
    if (captchaService.shouldPauseQueue()) {
      await authWorker.pause();
      setTimeout(() => void authWorker.resume(), env.AUTH_QUEUE_PAUSE_ON_CAPTCHA_FAILURE_MS);
      throw new Error('Auth queue paused due to CAPTCHA circuit breaker');
    }

    const histogram = authLatencySeconds.startTimer();
    try {
      const driver = await prisma.driver.findUniqueOrThrow({ where: { id: job.data.driverId }, include: { tenant: true } });
      await authService.authenticate(driver.tenantId, driver.id, driver.username, driver.passwordEncrypted);
      await prisma.driver.update({
        where: { id: driver.id },
        data: {
          sessionValid: true,
          lastSessionAt: new Date(),
          lastAuthAt: new Date(),
          proxyAssigned: driver.tenant.proxyUrl
        }
      });

      if (job.data.jobId) {
        await prisma.job.update({ where: { id: job.data.jobId }, data: { status: JobStatus.PROCESSING, queueName: 'submit' } });
        await producer.enqueueSubmit({
          tenantId: job.data.tenantId,
          driverId: job.data.driverId,
          jobId: job.data.jobId,
          correlationId: job.data.correlationId,
          idempotencyKey: job.data.jobId
        });
      }

      jobsProcessedTotal.labels('auth', 'success').inc();
    } catch (error) {
      const attempt = job.data.attempt + 1;
      jobsFailedTotal.labels('auth', 'AUTH_FAILURE').inc();
      if (attempt >= env.AUTH_RETRY_MAX_ATTEMPTS) {
        await producer.moveToDeadLetter({
          tenantId: job.data.tenantId,
          driverId: job.data.driverId,
          correlationId: job.data.correlationId,
          code: 'AUTH_FAILURE',
          detail: String(error),
          ...(job.data.jobId ? { jobId: job.data.jobId } : {})
        });
      } else {
        await producer.enqueueRetry(
          {
            target: 'auth',
            tenantId: job.data.tenantId,
            driverId: job.data.driverId,
            correlationId: job.data.correlationId,
            payload: { ...job.data, attempt }
          },
          exponentialBackoff(attempt)
        );
      }
      throw error;
    } finally {
      histogram();
    }
  },
  env.AUTH_QUEUE_CONCURRENCY,
  {
    max: env.AUTH_QUEUE_RATE_LIMIT_MAX,
    duration: env.AUTH_QUEUE_RATE_LIMIT_DURATION_MS
  }
);

authWorker.on('completed', () => logger.info('Auth worker job completed'));
authWorker.on('failed', (_job, error) => logger.error({ error }, 'Auth worker job failed'));
