import { verify, sign } from 'jsonwebtoken';
import { env } from '../../config/env.js';

export type TenantJwtClaims = {
  sub: string;
  tenantId: string;
  email?: string;
  role?: 'owner' | 'operator' | 'viewer';
};

export class UnauthorizedError extends Error {}
export class ForbiddenError extends Error {}

export function issueTenantToken(claims: TenantJwtClaims, expiresIn = '12h'): string {
  return sign(claims, env.JWT_SECRET, {
    algorithm: 'HS256',
    issuer: env.JWT_ISSUER,
    audience: env.JWT_AUDIENCE,
    expiresIn
  });
}

export function authenticateTenantRequest(headers: Record<string, string | string[] | undefined>): TenantJwtClaims {
  const rawAuthorization = headers.authorization ?? headers.Authorization;
  const authorization = Array.isArray(rawAuthorization) ? rawAuthorization[0] : rawAuthorization;

  if (!authorization?.startsWith('Bearer ')) {
    throw new UnauthorizedError('Missing bearer token');
  }

  const token = authorization.slice('Bearer '.length).trim();
  const claims = verify(token, env.JWT_SECRET, {
    algorithms: ['HS256'],
    issuer: env.JWT_ISSUER,
    audience: env.JWT_AUDIENCE
  }) as TenantJwtClaims;

  if (!claims.tenantId) {
    throw new UnauthorizedError('Token does not include tenantId');
  }

  return claims;
}

export function assertTenantIsolation(claims: TenantJwtClaims, requestedTenantId: string): void {
  if (claims.tenantId !== requestedTenantId) {
    throw new ForbiddenError(`Tenant isolation breach prevented for tenant ${requestedTenantId}`);
  }
}

export function withTenantGuard<T>(
  headers: Record<string, string | string[] | undefined>,
  requestedTenantId: string,
  handler: (claims: TenantJwtClaims) => Promise<T>
): Promise<T> {
  const claims = authenticateTenantRequest(headers);
  assertTenantIsolation(claims, requestedTenantId);
  return handler(claims);
}
