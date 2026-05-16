import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

// v0.7.29 — root / no longer redirects. (dashboard)/page.tsx is now
// the Command Center landing page rather than a stub redirect to
// /notebooks. The proxy stays in place for future routing logic;
// the matcher still excludes API + Next internals.
export function proxy(_request: NextRequest) {
  return NextResponse.next()
}

export const config = {
  matcher: [
    '/((?!api|_next/static|_next/image|favicon.ico).*)',
  ],
}
