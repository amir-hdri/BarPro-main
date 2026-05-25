import { chromium } from 'playwright';
import { logger } from '../../lib/logger.js';
import { TwoCaptchaService } from '../captcha/TwoCaptchaService.js';
import { ProxyRegistry } from '../proxy/ProxyRegistry.js';
import { SessionStore, type StoredSession } from '../session/SessionStore.js';
import { env } from '../../config/env.js';

export class LegacyPortalAuthService {
  public constructor(
    private readonly captchaService: TwoCaptchaService,
    private readonly proxyRegistry: ProxyRegistry,
    private readonly sessionStore: SessionStore
  ) {}

  public async authenticate(tenantId: string, driverId: string, username: string, password: string): Promise<StoredSession> {
    const proxyUrl = await this.proxyRegistry.getTenantProxy(tenantId);
    const browser = await chromium.launch({ headless: true, proxy: { server: proxyUrl } });
    const context = await browser.newContext();
    const page = await context.newPage();

    try {
      await page.goto(env.LEGACY_LOGIN_URL, { waitUntil: 'domcontentloaded' });
      const captchaImage = await page.locator('img.captcha').screenshot();
      const captchaResult = await this.captchaService.solve({ imageBase64: captchaImage.toString('base64') });

      await page.locator('input[name="username"]').fill(username);
      await page.locator('input[name="password"]').fill(password);
      await page.locator('input[name="captcha"]').fill(captchaResult.token);
      await page.locator('button[type="submit"]').click();
      await page.waitForLoadState('networkidle');

      const cookies = await context.cookies();
      const session: StoredSession = {
        cookies: cookies.map((item: { name: string; value: string; domain?: string; path?: string }) => ({ name: item.name, value: item.value, domain: item.domain, path: item.path })),
        proxy: proxyUrl,
        lastAuthAt: new Date().toISOString(),
        sessionValid: true,
        userAgent: await page.evaluate(() => navigator.userAgent)
      };

      await this.sessionStore.set(tenantId, driverId, session);
      return session;
    } finally {
      await page.close();
      await context.close();
      await browser.close();
      logger.info({ tenantId, driverId }, 'Auth flow completed');
    }
  }
}
