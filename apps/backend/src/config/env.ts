import { config as loadEnv } from 'dotenv';
import { z } from 'zod';

loadEnv();

const envSchema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().positive().default(3001),
  DATABASE_URL: z.string().min(1),
  REDIS_URL: z.string().min(1),
  REDIS_PASSWORD: z.string().default(''),
  JWT_SECRET: z.string().min(32).default('change-me-super-secret-jwt-key-32-bytes'),
  JWT_ISSUER: z.string().default('utcms-rpa'),
  JWT_AUDIENCE: z.string().default('utcms-tenants'),
  AUTH_QUEUE_NAME: z.string().default('auth'),
  SUBMIT_QUEUE_NAME: z.string().default('submit'),
  RETRY_QUEUE_NAME: z.string().default('retry'),
  DEAD_LETTER_QUEUE_NAME: z.string().default('dead-letter'),
  TEHRAN_TIMEZONE: z.string().default('Asia/Tehran'),
  AUTH_QUEUE_CONCURRENCY: z.coerce.number().int().positive().default(4),
  SUBMIT_QUEUE_CONCURRENCY: z.coerce.number().int().positive().default(80),
  RETRY_QUEUE_CONCURRENCY: z.coerce.number().int().positive().default(10),
  AUTH_QUEUE_RATE_LIMIT_MAX: z.coerce.number().int().positive().default(5),
  AUTH_QUEUE_RATE_LIMIT_DURATION_MS: z.coerce.number().int().positive().default(1000),
  TENANT_MAX_RPS: z.coerce.number().int().positive().default(5),
  SESSION_TTL_SECONDS: z.coerce.number().int().positive().default(7200),
  SESSION_REFRESH_THRESHOLD_SECONDS: z.coerce.number().int().positive().default(900),
  SUBMIT_RETRY_DELAY_MS: z.coerce.number().int().positive().default(1800000),
  AUTH_RETRY_BASE_MS: z.coerce.number().int().positive().default(3000),
  AUTH_RETRY_MAX_MS: z.coerce.number().int().positive().default(300000),
  AUTH_RETRY_MAX_ATTEMPTS: z.coerce.number().int().positive().default(5),
  AUTH_QUEUE_PAUSE_ON_CAPTCHA_FAILURE_MS: z.coerce.number().int().positive().default(300000),
  CIRCUIT_BREAKER_FAILURE_THRESHOLD: z.coerce.number().int().positive().default(5),
  TWO_CAPTCHA_API_KEY: z.string().default(''),
  TWO_CAPTCHA_BASE_URL: z.string().default('https://2captcha.com'),
  LEGACY_LOGIN_URL: z.string().url(),
  LEGACY_SUBMIT_URL: z.string().url(),
  HEALTHCHECK_URL: z.string().url(),
  WEBHOOK_URL: z.string().optional()
});

export const env = envSchema.parse(process.env);
