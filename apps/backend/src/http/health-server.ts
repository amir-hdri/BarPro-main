import { createServer } from 'node:http';
import { prisma } from '../lib/prisma.js';
import { metricsRegistry, queueDepth } from '../lib/metrics.js';
import { redis } from '../lib/redis.js';
import { authQueue, deadLetterQueue, retryQueue, submitQueue } from '../queues/bullmq.js';

export function createHealthServer(port: number) {
  return createServer(async (req, res) => {
    if (!req.url) {
      res.statusCode = 404;
      res.end();
      return;
    }

    if (req.url === '/metrics') {
      res.setHeader('Content-Type', metricsRegistry.contentType);
      res.end(await metricsRegistry.metrics());
      return;
    }

    if (req.url !== '/health') {
      res.statusCode = 404;
      res.end(JSON.stringify({ ok: false }));
      return;
    }

    try {
      await prisma.$queryRaw`SELECT 1`;
      await redis.ping();
      const [authCount, submitCount, retryCount, dlqCount] = await Promise.all([
        authQueue.count(),
        submitQueue.count(),
        retryQueue.count(),
        deadLetterQueue.count()
      ]);
      queueDepth.labels('auth').set(authCount);
      queueDepth.labels('submit').set(submitCount);
      queueDepth.labels('retry').set(retryCount);
      queueDepth.labels('dead-letter').set(dlqCount);

      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({
        ok: true,
        redis: 'up',
        db: 'up',
        queues: { auth: authCount, submit: submitCount, retry: retryCount, deadLetter: dlqCount }
      }));
    } catch (error) {
      res.statusCode = 503;
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ ok: false, error: String(error) }));
    }
  }).listen(port);
}
