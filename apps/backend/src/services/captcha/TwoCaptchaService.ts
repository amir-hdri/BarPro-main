import axios from 'axios';
import { env } from '../../config/env.js';
import { logger } from '../../lib/logger.js';
import { CircuitBreaker } from '../circuit-breaker.js';

export type CaptchaSolveRequest = {
  imageBase64: string;
};

export type CaptchaSolveResult = {
  token: string;
  providerRequestId: string;
};

export class TwoCaptchaService {
  private readonly breaker = new CircuitBreaker(env.CIRCUIT_BREAKER_FAILURE_THRESHOLD, env.AUTH_QUEUE_PAUSE_ON_CAPTCHA_FAILURE_MS);

  public async solve(request: CaptchaSolveRequest): Promise<CaptchaSolveResult> {
    return this.breaker.execute(async () => {
      const submit = await axios.post(`${env.TWO_CAPTCHA_BASE_URL}/in.php`, undefined, {
        params: {
          key: env.TWO_CAPTCHA_API_KEY,
          method: 'base64',
          body: request.imageBase64,
          json: 1
        },
        timeout: 10000
      });

      if (submit.data.status !== 1) {
        throw new Error(`2Captcha submit failed: ${submit.data.request}`);
      }

      const id = String(submit.data.request);
      for (let attempt = 0; attempt < 24; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 5000));
        const result = await axios.get(`${env.TWO_CAPTCHA_BASE_URL}/res.php`, {
          params: { key: env.TWO_CAPTCHA_API_KEY, action: 'get', id, json: 1 },
          timeout: 10000
        });

        if (result.data.status === 1) {
          return { token: String(result.data.request), providerRequestId: id };
        }
        if (result.data.request !== 'CAPCHA_NOT_READY') {
          throw new Error(`2Captcha poll failed: ${result.data.request}`);
        }
      }

      throw new Error('2Captcha polling timed out');
    });
  }

  public shouldPauseQueue(): boolean {
    const open = this.breaker.isOpen();
    if (open) {
      logger.warn('2Captcha circuit breaker is open');
    }
    return open;
  }
}
