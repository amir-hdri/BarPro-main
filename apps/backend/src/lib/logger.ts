import pino from 'pino';
import { env } from '../config/env.js';

export const logger = pino({
  level: env.NODE_ENV === 'production' ? 'info' : 'debug',
  base: { service: 'utcms-rpa-backend' },
  redact: ['req.headers.authorization', 'password', 'token'],
  timestamp: pino.stdTimeFunctions.isoTime
});
