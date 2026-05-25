import { buildWorker, queueNames, type AuthJobData, type RetryJobData, type SubmitJobData } from '../queues/bullmq.js';
import { JobProducer } from '../queues/job-producer.js';
import { logger } from '../lib/logger.js';
import { env } from '../config/env.js';

const producer = new JobProducer();

export const retryWorker = buildWorker<RetryJobData>(queueNames.retry, async (job) => {
  if (job.data.target === 'auth') {
    await producer.enqueueAuth(job.data.payload as AuthJobData);
    return;
  }
  await producer.enqueueSubmit(job.data.payload as SubmitJobData);
}, env.RETRY_QUEUE_CONCURRENCY);

retryWorker.on('completed', () => logger.info('Retry worker job completed'));
retryWorker.on('failed', (_job, error) => logger.error({ error }, 'Retry worker job failed'));
