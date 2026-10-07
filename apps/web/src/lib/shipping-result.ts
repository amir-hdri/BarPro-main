import type { ApiResponse } from './api';

/** HTTP success alone is insufficient: the server must acknowledge the action. */
export function requireShippingResult(
  response: ApiResponse<{ status: string }>,
  action: 'start' | 'finish',
): void {
  const expected = action === 'start' ? 'started' : 'delivered';
  if (!response.success || response.data?.status !== expected) {
    throw new Error(response.error || (action === 'start'
      ? 'شروع حمل تأیید نشد؛ وضعیت مسیر را بررسی کنید.'
      : 'پایان حمل تأیید نشد؛ وضعیت مسیر را بررسی کنید.'));
  }
}
