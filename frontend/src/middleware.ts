// v0.7.117 — first-launch Setup Wizard redirect.
//
// The middleware can't reasonably fetch /healthz/deep on every request
// (it'd add a round-trip to every navigation and middleware runs on
// the edge with no shared client state). Instead, we use a sentinel
// cookie: if `wizard_completed` is missing, the user has never been
// past the wizard, and we send them there. The wizard itself reads
// /healthz/deep and either auto-advances (healthy) or lets the user
// fix subsystems and click "Continue anyway" (degraded). Either way
// the wizard sets the cookie before sending the user on.
//
// This satisfies the "first launch" half of the requirement (status
// check + redirect happen *in the wizard*) without paying a per-nav
// edge fetch cost or coupling the middleware to a backend env var.

import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const WIZARD_COMPLETED_COOKIE = 'wizard_completed'
const WIZARD_PATH = '/setup-wizard'

// Routes that should never trigger a wizard redirect: the wizard
// itself, login, and the API/_next prefixes which middleware already
// excludes via matcher but we double-check here as a safety net.
const EXEMPT_PREFIXES = [
  WIZARD_PATH,
  '/login',
  '/api',
  '/_next',
]

export function middleware(req: NextRequest) {
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
  // Apply to all paths except Next.js internals and static files.
  // The function above does fine-grained exemption.
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:png|jpg|jpeg|gif|svg|webp|ico|css|js|map)$).*)',
  ],
}
