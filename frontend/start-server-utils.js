const fs = require('fs')
const path = require('path')

function resolveTracedStandaloneServer(frontendDir) {
  try {
    const metadata = JSON.parse(
      fs.readFileSync(
        path.join(frontendDir, '.next', 'required-server-files.json'),
        'utf8'
      )
    )
    const appDir = metadata.appDir
    const tracingRoot = metadata.config?.outputFileTracingRoot
    if (
      typeof appDir !== 'string' ||
      typeof tracingRoot !== 'string' ||
      path.resolve(appDir) !== path.resolve(frontendDir)
    ) {
      return null
    }

    const appPath = path.relative(tracingRoot, appDir)
    if (
      !appPath ||
      appPath === '..' ||
      appPath.startsWith(`..${path.sep}`) ||
      path.isAbsolute(appPath)
    ) {
      return null
    }

    const server = path.join(frontendDir, '.next', 'standalone', appPath, 'server.js')
    return fs.existsSync(server) ? server : null
  } catch {
    return null
  }
}

function resolveStandaloneServer(frontendDir = __dirname) {
  const flattened = path.join(frontendDir, 'server.js')
  if (fs.existsSync(flattened)) return flattened

  const nested = path.join(frontendDir, '.next', 'standalone', 'server.js')
  if (fs.existsSync(nested)) return nested

  const traced = resolveTracedStandaloneServer(frontendDir)
  if (traced) return traced

  throw new Error(
    `Next standalone server not found. Expected ${flattened}, ${nested}, or the traced standalone path. Run npm run build first.`
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
