import { Counter, Gauge, Histogram, Registry, collectDefaultMetrics } from 'prom-client';

export const metricsRegistry = new Registry();
collectDefaultMetrics({ register: metricsRegistry });

export const jobsProcessedTotal = new Counter({
  name: 'jobs_processed_total',
  help: 'Total processed jobs by queue and result',
  labelNames: ['queue', 'result'],
  registers: [metricsRegistry]
});

export const jobsFailedTotal = new Counter({
  name: 'jobs_failed_total',
  help: 'Total failed jobs by queue and code',
  labelNames: ['queue', 'code'],
  registers: [metricsRegistry]
});

export const authLatencySeconds = new Histogram({
  name: 'auth_latency_seconds',
  help: 'Authentication latency in seconds',
  buckets: [1, 2, 5, 10, 20, 30, 60],
  registers: [metricsRegistry]
});

export const queueDepth = new Gauge({
  name: 'queue_depth',
  help: 'Queue depth by queue name',
  labelNames: ['queue'],
  registers: [metricsRegistry]
});

export const activeSessions = new Gauge({
  name: 'active_sessions',
  help: 'Active sessions stored in Redis',
  labelNames: ['tenantId'],
  registers: [metricsRegistry]
});
