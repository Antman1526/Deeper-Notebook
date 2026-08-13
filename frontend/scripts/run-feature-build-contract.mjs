import {
  closeSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  readFileSync,
  realpathSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs'
import { createHash } from 'node:crypto'
import { dirname, join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const nodeModules = join(frontendDir, 'node_modules')
const verifyScriptName = join('scripts', 'verify-feature-env-build.mjs')
const stageParent = resolve(process.env.TMPDIR || '/tmp')
const stagePrefix = 'deeper-notebook-feature-contract-'
const frontendKey = createHash('sha256').update(frontendDir).digest('hex').slice(0, 24)
const lockPath = join(
  stageParent,
  `deeper-notebook-feature-build-${frontendKey}.lock`,
)

function run(command, args, cwd) {
  const result = spawnSync(command, args, {
    cwd,
    env: process.env,
    stdio: 'inherit',
  })
  if (result.error) throw result.error
  return result.status ?? 1
}

function verify(rootDir) {
  return run(process.execPath, [join(rootDir, verifyScriptName)], rootDir)
}

function directBuild(rootDir) {
  const next = join(rootDir, 'node_modules', '.bin', 'next')
  const status = run(next, ['build', 'tests/build-contract'], rootDir)
  return status === 0 ? verify(rootDir) : status
}

function isSafeStagePath(candidate) {
  return (
    candidate.startsWith(`${stageParent}/`) &&
    candidate.split('/').length === stageParent.split('/').length + 1 &&
    candidate.slice(stageParent.length + 1).startsWith(stagePrefix)
  )
}

function readLock() {
  try {
    const raw = readFileSync(lockPath, 'utf8')
    const value = JSON.parse(raw)
    if (
      !value ||
      !Number.isInteger(value.pid) ||
      value.pid <= 1 ||
      typeof value.stage !== 'string' ||
      !isSafeStagePath(value.stage)
    ) {
      throw new Error('invalid feature build lock')
    }
    return value
  } catch (error) {
    if (error?.code === 'ENOENT') return null
    throw new Error('feature build lock is malformed; remove only the exact stale lock after inspection')
  }
}

function processIsAlive(pid) {
  try {
    process.kill(pid, 0)
    return true
  } catch (error) {
    return error?.code === 'EPERM'
  }
}

function acquireLock(stage) {
  let lockFd
  try {
    lockFd = openSync(lockPath, 'wx', 0o600)
  } catch (error) {
    if (error?.code !== 'EEXIST') throw error
    const stale = readLock()
    if (!stale || processIsAlive(stale.pid)) {
      throw new Error('feature build contract is already materializing shared node_modules')
    }
    // A crashed invocation leaves only its exact stage and lock. Recover both
    // after proving the recorded owner is gone; never scan or delete broadly.
    if (existsSync(stale.stage)) rmSync(stale.stage, { recursive: true, force: true })
    unlinkSync(lockPath)
    lockFd = openSync(lockPath, 'wx', 0o600)
  }
  writeFileSync(lockFd, JSON.stringify({ pid: process.pid, stage }), 'utf8')
  return lockFd
}

function materializeSharedDependencies() {
  if (!lstatSync(nodeModules).isSymbolicLink()) return directBuild(frontendDir)
  const target = realpathSync(nodeModules)
  if (target === frontendDir || target.startsWith(`${frontendDir}/`)) {
    return directBuild(frontendDir)
  }

  const rsync = process.env.RSYNC_BIN || '/usr/bin/rsync'
  if (!existsSync(rsync)) {
    throw new Error('shared node_modules requires /usr/bin/rsync for a safe local materialization')
  }

  if (!existsSync(stageParent)) {
    throw new Error('feature build temporary directory does not exist')
  }
  const stage = mkdtempSync(join(stageParent, stagePrefix))
  let lockFd
  try {
    lockFd = acquireLock(stage)
  } catch (error) {
    rmSync(stage, { recursive: true, force: true })
    throw error
  }
  try {
    // Build from a disposable project copy instead of renaming the caller's
    // node_modules symlink. A SIGINT/SIGTERM/SIGKILL can therefore leave only
    // this bounded stage/lock pair, which the next invocation safely recovers.
    const syncProject = run(
      rsync,
      [
        '-a',
        '--exclude',
        'node_modules',
        '--exclude',
        '.next',
        '--exclude',
        `${stagePrefix}*`,
        `${frontendDir}/`,
        `${stage}/`,
      ],
      frontendDir,
    )
    if (syncProject !== 0) throw new Error(`feature build project staging failed (${syncProject})`)

    const stageNodeModules = join(stage, 'node_modules')
    mkdirSync(stageNodeModules)
    const syncDependencies = run(
      rsync,
      ['-a', '--link-dest', target, `${target}/`, `${stageNodeModules}/`],
      frontendDir,
    )
    if (syncDependencies !== 0) {
      throw new Error(`rsync dependency materialization failed (${syncDependencies})`)
    }
    return directBuild(stage)
  } finally {
    try {
      rmSync(stage, { recursive: true, force: true })
    } finally {
      closeSync(lockFd)
      unlinkSync(lockPath)
    }
  }
}

const status = materializeSharedDependencies()
process.exitCode = status
