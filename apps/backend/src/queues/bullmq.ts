import { Queue, QueueEvents, Worker, type JobsOptions, type Processor } from 'bullmq';
import IORedis from 'ioredis';

import { env } from '../config/env.js';
import { redisConnectionOptions } from '../lib/redis.js';
import { queueNames } from './queue-names.js';

export { queueNames } from './queue-names.js';

export type AuthJobData = {
  tenantId: string;
  driverId: string;
  correlationId: string;
  attempt: number;
  reason: 'initial_auth' | 'session_refresh' | 'proactive_refresh';
  jobId?: string;
};

export type SubmitJobData = {
  tenantId: string;
  driverId: string;
  jobId: string;
  correlationId: string;
  idempotencyKey: string;
};

export type RetryJobData = {
  target: 'auth' | 'submit';
  tenantId: string;
  driverId: string;
  correlationId: string;
  payload: AuthJobData | SubmitJobData;
};

export type DeadLetterJobData = {
  tenantId: string;
  driverId: string;
  jobId?: string;
  correlationId: string;
  code: string;
  detail: string;
};

const connection = new IORedis(env.REDIS_URL, redisConnectionOptions);

const defaultJobOptions: JobsOptions = {
  removeOnComplete: 1000,
  removeOnFail: 1000,
  attempts: 1
};

export const authQueue = new Queue<AuthJobData>(queueNames.auth, {
  connection,
  defaultJobOptions
});

export const submitQueue = new Queue<SubmitJobData>(queueNames.submit, {
  connection,
  defaultJobOptions
});

export const retryQueue = new Queue<RetryJobData>(queueNames.retry, {
  connection,
  defaultJobOptions
});

export const deadLetterQueue = new Queue<DeadLetterJobData>(queueNames.deadLetter, {
  connection,
  defaultJobOptions
});

export const queueEvents = {
  auth: new QueueEvents(queueNames.auth, { connection }),
  submit: new QueueEvents(queueNames.submit, { connection }),
  retry: new QueueEvents(queueNames.retry, { connection }),
  deadLetter: new QueueEvents(queueNames.deadLetter, { connection })
};

export function buildWorker<T>(
  name: string,
  processor: Processor<T>,
  concurrency: number,
  limiter?: { max: number; duration: number }
): Worker<T> {
  return new Worker<T>(name, processor, {
    connection,
    concurrency,
    limiter,
    lockDuration: 120000,
    stalledInterval: 30000
  });
}

export const bullmqConfig = {
  authWorker: {
    concurrency: env.AUTH_QUEUE_CONCURRENCY,
    limiter: {
      max: env.AUTH_QUEUE_RATE_LIMIT_MAX,
      duration: env.AUTH_QUEUE_RATE_LIMIT_DURATION_MS
    }
  },
  submitWorker: {
    concurrency: env.SUBMIT_QUEUE_CONCURRENCY
  },
  retryWorker: {
    concurrency: env.RETRY_QUEUE_CONCURRENCY
  }
} as const;
