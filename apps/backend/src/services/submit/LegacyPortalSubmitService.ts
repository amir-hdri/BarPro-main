import axios from 'axios';
import { env } from '../../config/env.js';
import { JobFailureCode } from '../../domain/enums.js';
import { SessionStore } from '../session/SessionStore.js';

export type SubmitResult =
  | { kind: 'success' }
  | { kind: 'reauth'; code: JobFailureCode.SESSION_EXPIRED | JobFailureCode.SESSION_MISSING }
  | { kind: 'retry'; code: JobFailureCode.LEGACY_RATE_LIMITED | JobFailureCode.LEGACY_SERVER_ERROR | JobFailureCode.PROXY_BANNED | JobFailureCode.UNKNOWN; detail: string }
  | { kind: 'fail'; code: JobFailureCode.LEGACY_VALIDATION_FAILED | JobFailureCode.UNKNOWN; detail: string };

export class LegacyPortalSubmitService {
  public constructor(private readonly sessionStore: SessionStore) {}

  public async submit(tenantId: string, driverId: string, payload: Record<string, unknown>): Promise<SubmitResult> {
    const session = await this.sessionStore.get(tenantId, driverId);
    if (!session || !session.sessionValid) {
      return { kind: 'reauth', code: JobFailureCode.SESSION_MISSING };
    }

    const cookieHeader = session.cookies.map((item) => `${item.name}=${item.value}`).join('; ');
    try {
      const response = await axios.post(env.LEGACY_SUBMIT_URL, payload, {
        headers: {
          Cookie: cookieHeader,
          'User-Agent': session.userAgent
        },
        timeout: 30000,
        proxy: false
      });

      await this.sessionStore.extend(tenantId, driverId);
      if (response.status >= 200 && response.status < 300) {
        return { kind: 'success' };
      }
      return { kind: 'fail', code: JobFailureCode.UNKNOWN, detail: `Unexpected status ${response.status}` };
    } catch (error: unknown) {
      if (axios.isAxiosError(error)) {
        const axiosError = error as any;
        const status = axiosError.response?.status as number | undefined;
        const responseData = axiosError.response?.data;
        const body = typeof responseData === 'string' ? responseData : JSON.stringify(responseData ?? {});
        if (status === 401 || status === 403) {
          return { kind: 'reauth', code: JobFailureCode.SESSION_EXPIRED };
        }
        if (status === 429 || body.includes('rate limit')) {
          return { kind: 'retry', code: JobFailureCode.PROXY_BANNED, detail: body };
        }
        if (status && status >= 500) {
          return { kind: 'retry', code: JobFailureCode.LEGACY_SERVER_ERROR, detail: body };
        }
        if (status && status >= 400) {
          return { kind: 'fail', code: JobFailureCode.LEGACY_VALIDATION_FAILED, detail: body };
        }
      }
      return { kind: 'retry', code: JobFailureCode.UNKNOWN, detail: String(error) };
    }
  }
}
