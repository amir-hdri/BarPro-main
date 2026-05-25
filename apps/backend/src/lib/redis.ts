import IORedis from 'ioredis';
import { env } from '../config/env.js';

const redisPassword = env.REDIS_PASSWORD?.trim() || undefined;

export const redisConnectionOptions = {
  maxRetriesPerRequest: null,
  enableReadyCheck: true,
  lazyConnect: false,
  ...(redisPassword ? { password: redisPassword } : {})
} as const;

export const redis = new IORedis(env.REDIS_URL, redisConnectionOptions);
