import { NextResponse, type NextRequest } from 'next/server';

const AUTH_COOKIE_NAME = process.env.AUTH_COOKIE_NAME || 'utcms_auth_token';

const publicPaths = ['/auth'];

function isPublicPath(pathname: string): boolean {
  return publicPaths.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

const STATIC_EXT_REGEX = /\.(ico|png|jpg|jpeg|svg|css|js|woff2?|map|json|webp|avif|ttf|eot|webmanifest|txt)$/i;

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const authCookie = request.cookies.get(AUTH_COOKIE_NAME);
  const hasAuthCookie = Boolean(authCookie);

  // Skip assets, API rewrites and static data
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname.startsWith('/readyz') ||
    pathname.startsWith('/browser-pool') ||
    pathname.startsWith('/workers') ||
    pathname.startsWith('/proxies') ||
    pathname.startsWith('/captcha') ||
    pathname.startsWith('/circuit-breaker') ||
    STATIC_EXT_REGEX.test(pathname)
  ) {
    return NextResponse.next();
  }

  if (isPublicPath(pathname)) {
    if (hasAuthCookie) {
      const url = request.nextUrl.clone();
      url.pathname = '/';
      url.search = '';
      return NextResponse.redirect(url);
    }
    return NextResponse.next();
  }

  if (!hasAuthCookie) {
    const url = request.nextUrl.clone();
    url.pathname = '/auth';
    url.search = `?from=${encodeURIComponent(request.nextUrl.pathname + request.nextUrl.search)}`;
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};