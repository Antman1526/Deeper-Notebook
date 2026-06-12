// v0.7.117 — first-launch Setup Wizard redirect.
//
// v0.7.129i — Migrated from middleware.ts to proxy.ts for Next.js 16.
// Next 16 renamed `middleware` → `proxy`: same NextResponse API,
// same matcher shape, only the file name + exported function name
// changed. Both files coexisting caused a hard build failure:
//   "Both middleware file ./src/middleware.ts and proxy file
//    ./src/proxy.ts are detected."
// The previous proxy.ts was a no-op stub (v0.7.29) that pre-dated the
// Setup Wizard work; we replace it with the wizard logic verbatim
// (renamed function only).
//
// The proxy can't reasonably fetch /healthz/deep on every request:
// that'd add a round-trip to every navigation and the proxy runs on
// the edge with no shared client state. Instead, we use a sentinel
// cookie: if `wizard_completed` is missing, the user has never been
// past the wizard, so we send them there. The wizard itself reads
// /healthz/deep and either auto-advances (healthy) or lets the user
// fix subsystems and click "Continue anyway" (degraded). Either way
// the wizard sets the cookie before sending the user on.

import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const WIZARD_COMPLETED_COOKIE = 'wizard_completed'
const WIZARD_PATH = '/setup-wizard'

// Routes that should never trigger a wizard redirect: the wizard
// itself, login, and the API/_next prefixes (the matcher excludes
// _next already; double-checking here is a cheap safety net).
const EXEMPT_PREFIXES = [
  WIZARD_PATH,
  '/login',
  '/api',
  '/_next',
]

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl

  for (const prefix of EXEMPT_PREFIXES) {
    if (pathname === prefix || pathname.startsWith(prefix + '/')) {
      return NextResponse.next()
    }
  }

  const completed = req.cookies.get(WIZARD_COMPLETED_COOKIE)?.value
  if (completed) {
    return NextResponse.next()
  }

  const url = req.nextUrl.clone()
  url.pathname = WIZARD_PATH
  return NextResponse.redirect(url)
}

export const config = {
  // Apply to all paths except Next.js internals and static assets.
  // The function above does fine-grained route exemption.
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|gif|svg|webp|ico|css|js|map)$).*)',
  ],
}
