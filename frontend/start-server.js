#!/usr/bin/env node

const {
  ensureStandaloneAssets,
  resolveStandaloneServer,
} = require('./start-server-utils')

// Set default PORT if not already set
if (!process.env.PORT) {
  process.env.PORT = '8502';
}

// Start the Next.js standalone server. Packaged desktop builds flatten
// `.next/standalone` into `frontend/server.js`; local builds keep the
// nested Next output. Support both so `npm run start` is a faithful
// production smoke path after `npm run build`.
ensureStandaloneAssets(__dirname)
require(resolveStandaloneServer(__dirname));
