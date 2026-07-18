const fs = require('fs')
const path = require('path')

function resolveStandaloneServer(frontendDir = __dirname) {
  const flattened = path.join(frontendDir, 'server.js')
  if (fs.existsSync(flattened)) return flattened

  const nested = path.join(frontendDir, '.next', 'standalone', 'server.js')
  if (fs.existsSync(nested)) return nested

  throw new Error(
    `Next standalone server not found. Expected ${flattened} or ${nested}. Run npm run build first.`
  )
}

function linkOrCopyDirectory(source, destination) {
  if (!fs.existsSync(source) || fs.existsSync(destination)) return

  fs.mkdirSync(path.dirname(destination), { recursive: true })
  try {
    fs.symlinkSync(source, destination, 'dir')
  } catch {
    fs.cpSync(source, destination, { recursive: true })
  }
}

function ensureStandaloneAssets(frontendDir = __dirname) {
  const server = resolveStandaloneServer(frontendDir)
  const serverDir = path.dirname(server)

  if (serverDir === frontendDir) return

  linkOrCopyDirectory(
    path.join(frontendDir, '.next', 'static'),
    path.join(serverDir, '.next', 'static')
  )
  linkOrCopyDirectory(
    path.join(frontendDir, 'public'),
    path.join(serverDir, 'public')
  )
}

module.exports = {
  ensureStandaloneAssets,
  resolveStandaloneServer,
}
