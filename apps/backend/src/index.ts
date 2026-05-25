import { env } from './config/env.js';
import { logger } from './lib/logger.js';
import { prisma } from './lib/prisma.js';
import { redis } from './lib/redis.js';
import { FairScheduler } from './queues/fair-scheduler.js';
import { JobProducer } from './queues/job-producer.js';
import { createHealthServer } from './http/health-server.js';
import { startTehranMidnightCron } from './cron/tehran-midnight.js';
import { authWorker } from './workers/AuthWorker.js';
import { deadLetterWorker } from './workers/DeadLetterWorker.js';
import { retryWorker } from './workers/RetryWorker.js';
import { submitWorker } from './workers/SubmitWorker.js';

const producer = new JobProducer();
const scheduler = new FairScheduler(producer);

async function bootstrap(): Promise<void> {
  await prisma.$connect();
  await redis.ping();

  createHealthServer(env.PORT);
  startTehranMidnightCron(env.TEHRAN_TIMEZONE);

  setInterval(() => {
    void scheduler.dispatchPending().catch((error) => logger.error({ error }, 'Fair scheduler failed'));
  }, 1000);

  logger.info(
    {
      queues: {
        auth: env.AUTH_QUEUE_NAME,
        submit: env.SUBMIT_QUEUE_NAME,
        retry: env.RETRY_QUEUE_NAME,
        deadLetter: env.DEAD_LETTER_QUEUE_NAME
      },
      concurrency: {
        auth: env.AUTH_QUEUE_CONCURRENCY,
        submit: env.SUBMIT_QUEUE_CONCURRENCY,
        retry: env.RETRY_QUEUE_CONCURRENCY
      }
    },
    'Node.js RPA backend bootstrapped'
  );
}

void bootstrap();

for (const worker of [authWorker, submitWorker, retryWorker, deadLetterWorker]) {
  worker.on('error', (error) => logger.error({ error }, 'BullMQ worker error'));
}
