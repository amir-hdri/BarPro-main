import axios from 'axios';
import { env } from '../config/env.js';
import { logger } from '../lib/logger.js';

export class WebhookNotifier {
  public async notify(event: string, payload: Record<string, unknown>): Promise<void> {
    if (!env.WEBHOOK_URL) {
      return;
    }
    try {
      await axios.post(env.WEBHOOK_URL, { event, payload }, { timeout: 10000 });
    } catch (error) {
      logger.error({ error, event }, 'Webhook notification failed');
    }
  }
}
