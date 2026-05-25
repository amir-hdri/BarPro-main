import { buildWorker, queueNames, type DeadLetterJobData } from '../queues/bullmq.js';
import { logger } from '../lib/logger.js';
import { WebhookNotifier } from '../services/webhook-notifier.js';

const notifier = new WebhookNotifier();

export const deadLetterWorker = buildWorker<DeadLetterJobData>(queueNames.deadLetter, async (job) => {
  logger.error({ deadLetter: job.data }, 'Job moved to DLQ');
  await notifier.notify('job.dead_lettered', job.data);
}, 5);
