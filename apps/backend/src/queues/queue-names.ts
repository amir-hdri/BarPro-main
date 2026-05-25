import { env } from '../config/env.js';

export const queueNames = {
  auth: env.AUTH_QUEUE_NAME,
  submit: env.SUBMIT_QUEUE_NAME,
  retry: env.RETRY_QUEUE_NAME,
  deadLetter: env.DEAD_LETTER_QUEUE_NAME
} as const;
