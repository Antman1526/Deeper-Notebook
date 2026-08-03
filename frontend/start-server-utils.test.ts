import { mkdtempSync, rmSync, writeFileSync, mkdirSync, existsSync, lstatSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { createRequire } from 'node:module'
import { afterEach, describe, expect, it } from 'vitest'

const require = createRequire(import.meta.url)

const tempRoots: string[] = []

afterEach(() => {
  for (const root of tempRoots.splice(0)) {
    rmSync(root, { recursive: true, force: true })
  }
})

function tempFrontend(): string {
  const root = mkdtempSync(join(tmpdir(), 'onp-frontend-start-'))
  tempRoots.push(root)
  return root
}

describe('standalone frontend startup helpers', () => {
  it('uses flattened packaged server.js when present', () => {
    const root = tempFrontend()
    writeFileSync(join(root, 'server.js'), '')
    mkdirSync(join(root, '.next', 'standalone'), { recursive: true })
    writeFileSync(join(root, '.next', 'standalone', 'server.js'), '')

    const { resolveStandaloneServer } = require('./start-server-utils.js')

    expect(resolveStandaloneServer(root)).toBe(join(root, 'server.js'))
  })

  it('uses the standalone server nested under its output tracing root', () => {
    const checkout = tempFrontend()
    const root = join(checkout, '.worktrees', 'phase-1', 'frontend')
    const server = join(
      root,
      '.next',
      'standalone',
      '.worktrees',
      'phase-1',
      'frontend',
      'server.js',
    )
    mkdirSync(join(root, '.next'), { recursive: true })
    mkdirSync(join(root, '.next', 'standalone', '.worktrees', 'phase-1', 'frontend'), {
      recursive: true,
    })
    writeFileSync(server, '')
    writeFileSync(
      join(root, '.next', 'required-server-files.json'),
      JSON.stringify({
        appDir: root,
        config: { outputFileTracingRoot: checkout },
      }),
    )

    const { resolveStandaloneServer } = require('./start-server-utils.js')

    expect(resolveStandaloneServer(root)).toBe(server)
  })

  it('links build static assets beside the nested standalone server', () => {
    const root = tempFrontend()
    mkdirSync(join(root, '.next', 'standalone'), { recursive: true })
    mkdirSync(join(root, '.next', 'static', 'chunks'), { recursive: true })
    mkdirSync(join(root, 'public'), { recursive: true })
    writeFileSync(join(root, '.next', 'standalone', 'server.js'), '')
    writeFileSync(join(root, '.next', 'static', 'chunks', 'app.js'), 'console.log("ok")')
    writeFileSync(join(root, 'public', 'logo.svg'), '<svg />')

    const { ensureStandaloneAssets } = require('./start-server-utils.js')

    ensureStandaloneAssets(root)

    const linkedStatic = join(root, '.next', 'standalone', '.next', 'static')
    const linkedPublic = join(root, '.next', 'standalone', 'public')
    expect(existsSync(join(linkedStatic, 'chunks', 'app.js'))).toBe(true)
    expect(existsSync(join(linkedPublic, 'logo.svg'))).toBe(true)
    expect(lstatSync(linkedStatic).isSymbolicLink()).toBe(true)
    expect(lstatSync(linkedPublic).isSymbolicLink()).toBe(true)
  })
})
