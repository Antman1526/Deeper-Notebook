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
import { spawn } from 'node:child_process'
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

function processGroupIsAlive(pgid) {
  if (!Number.isInteger(pgid) || pgid <= 1) return false
  try {
    process.kill(-pgid, 0)
    return true
  } catch (error) {
    return error?.code === 'EPERM'
  }
}

function run(command, args, cwd, { onSpawn, onExit, detached = true } = {}) {
  return new Promise((resolvePromise, reject) => {
    let child
    try {
      child = spawn(command, args, {
        cwd,
        env: process.env,
        stdio: 'inherit',
        detached: process.platform !== 'win32' && detached,
      })
    } catch (error) {
      reject(error)
      return
    }
    child.once('spawn', () => onSpawn?.(child))
    child.once('error', reject)
    child.once('close', (status) => {
      onExit?.(child)
      resolvePromise(status ?? 1)
    })
  })
}

async function verify(rootDir, runCommand = run) {
  return runCommand(process.execPath, [join(rootDir, verifyScriptName)], rootDir)
}

async function directBuild(rootDir, runCommand = run) {
  const canonicalRoot = realpathSync(rootDir)
  const next = join(canonicalRoot, 'node_modules', '.bin', 'next')
  const status = await runCommand(next, ['build', 'tests/build-contract'], canonicalRoot)
  return status === 0 ? verify(canonicalRoot, runCommand) : status
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
      !isSafeStagePath(value.stage) ||
      (value.child !== null &&
        (!value.child ||
          !Number.isInteger(value.child.pid) ||
          value.child.pid <= 1 ||
          !Number.isInteger(value.child.pgid) ||
          value.child.pgid <= 1))
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

function writeLock(fd, value) {
  // Keep the exclusive descriptor open for ownership, but update the named
  // lock path so a spawned child cannot invalidate the descriptor. A partial
  // write is fail-closed by readLock's strict JSON/identity validation.
  writeFileSync(lockPath, JSON.stringify(value), { mode: 0o600 })
}

function recordedOwnerAndChildAreGone(lock) {
  if (processIsAlive(lock.pid)) return false
  const child = lock.child
  if (!child) return false
  return !processIsAlive(child.pid) && !processGroupIsAlive(child.pgid)
}

function acquireLock(stage) {
  let lockFd
  try {
    lockFd = openSync(lockPath, 'wx', 0o600)
  } catch (error) {
    if (error?.code !== 'EEXIST') throw error
    const stale = readLock()
    if (!stale || !recordedOwnerAndChildAreGone(stale)) {
      throw new Error('feature build contract is already materializing shared node_modules')
    }
    // A crashed invocation leaves only its exact stage and lock. Recover both
    // after proving the recorded owner is gone; never scan or delete broadly.
    if (existsSync(stale.stage)) rmSync(stale.stage, { recursive: true, force: true })
    unlinkSync(lockPath)
    lockFd = openSync(lockPath, 'wx', 0o600)
  }
  writeLock(lockFd, {
    pid: process.pid,
    stage,
    // Until a child is spawned, the wrapper's own process group is the
    // recorded owner. This makes a parent-group crash recoverable while
    // keeping the stale-stage proof bounded to one owned group.
    child: { pid: process.pid, pgid: process.pid },
  })
  return lockFd
}

async function materializeSharedDependencies() {
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
  const stage = realpathSync(mkdtempSync(join(stageParent, stagePrefix)))
  let lockFd
  try {
    lockFd = acquireLock(stage)
  } catch (error) {
    rmSync(stage, { recursive: true, force: true })
    throw error
  }
  try {
    const ownedRun = (command, args, cwd) =>
      run(command, args, cwd, {
        detached: command !== rsync,
        onSpawn(child) {
          writeLock(lockFd, {
            pid: process.pid,
            stage,
            child: {
              pid: child.pid,
              pgid: process.platform === 'win32' || command === rsync
                ? process.pid
                : child.pid,
            },
          })
        },
        onExit() {
          writeLock(lockFd, { pid: process.pid, stage, child: null })
        },
      })
    // Build from a disposable project copy instead of renaming the caller's
    // node_modules symlink. A SIGINT/SIGTERM/SIGKILL can therefore leave only
    // this bounded stage/lock pair, which the next invocation safely recovers.
    const syncProject = await ownedRun(
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
    const syncDependencies = await ownedRun(
      rsync,
      ['-a', '--link-dest', target, `${target}/`, `${stageNodeModules}/`],
      frontendDir,
    )
    if (syncDependencies !== 0) {
      throw new Error(`rsync dependency materialization failed (${syncDependencies})`)
    }
    return await directBuild(stage, ownedRun)
  } finally {
    try {
      rmSync(stage, { recursive: true, force: true })
    } finally {
      closeSync(lockFd)
      unlinkSync(lockPath)
    }
  }
}

try {
  process.exitCode = await materializeSharedDependencies()
} catch (error) {
  console.error(error?.message || 'feature build contract failed')
  process.exitCode = 1
}
