import {
  closeSync,
  existsSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  realpathSync,
  rmSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs'
import { createHash, randomBytes } from 'node:crypto'
import { dirname, join, resolve } from 'node:path'
import { execFileSync, spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const scriptPath = fileURLToPath(import.meta.url)
const frontendDir = resolve(dirname(scriptPath), '..')
const nodeModules = join(frontendDir, 'node_modules')
const verifyScriptName = join('scripts', 'verify-feature-env-build.mjs')
const stageParent = resolve(process.env.TMPDIR || '/tmp')
const stagePrefix = 'deeper-notebook-feature-contract-'
const frontendKey = createHash('sha256').update(frontendDir).digest('hex').slice(0, 24)
const lockPath = join(
  stageParent,
  `deeper-notebook-feature-build-${frontendKey}.lock`,
)
const helperMode = process.argv[2] === '--feature-build-helper'

function processIsAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 1) return false
  try {
    process.kill(pid, 0)
    return true
  } catch (error) {
    return error?.code === 'EPERM'
  }
}

function processGroupIsAlive(pgid) {
  if (!Number.isInteger(pgid) || pgid <= 1) return false
  try {
    process.kill(-pgid, 0)
    return true
  } catch (error) {
    // EPERM means that the group exists but is not inspectable by this user.
    return error?.code === 'EPERM'
  }
}

function currentProcessGroupId(pid) {
  try {
    const value = execFileSync(
      'ps',
      ['-o', 'pgid=', '-p', String(pid)],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] },
    ).trim()
    const pgid = Number(value)
    return Number.isInteger(pgid) && pgid > 1 ? pgid : null
  } catch {
    return null
  }
}

function isSafeStagePath(candidate) {
  if (typeof candidate !== 'string' || !candidate.startsWith(`${stageParent}/`)) {
    return false
  }
  const relative = candidate.slice(stageParent.length + 1)
  return !relative.includes('/') && relative.startsWith(stagePrefix)
}

function isSafeNonce(value) {
  return typeof value === 'string' && /^[a-f0-9]{32}$/.test(value)
}

function stageIsSafe(stage) {
  if (!existsSync(stage)) return true
  try {
    return !lstatSync(stage).isSymbolicLink()
  } catch {
    return false
  }
}

function readLock() {
  try {
    const value = JSON.parse(readFileSync(lockPath, 'utf8'))
    if (
      !value ||
      value.version !== 3 ||
      !Number.isInteger(value.pid) ||
      value.pid <= 1 ||
      !Number.isInteger(value.pgid) ||
      value.pgid <= 1 ||
      !isSafeNonce(value.nonce) ||
      !isSafeStagePath(value.stage) ||
      !['starting', 'running'].includes(value.state) ||
      !stageIsSafe(value.stage)
    ) {
      throw new Error('invalid feature build lock')
    }
    return value
  } catch (error) {
    if (error?.code === 'ENOENT') return null
    throw new Error(
      'feature build lock is malformed; remove only the exact stale lock after inspection',
    )
  }
}

function recordedHelperIsGone(lock) {
  // The helper is the process-group leader and every staging/build child is
  // launched without detaching, so group absence covers unregistered children.
  return !processIsAlive(lock.pid) && !processGroupIsAlive(lock.pgid)
}

function writeLock(fd, value) {
  // Keep the descriptor open while the helper owns the exact stage. The record
  // is intentionally stable: it never substitutes child:null for group proof.
  writeFileSync(lockPath, JSON.stringify(value), { mode: 0o600 })
}

function acquireLock(stage, nonce) {
  let fd
  try {
    fd = openSync(lockPath, 'wx', 0o600)
  } catch (error) {
    if (error?.code !== 'EEXIST') throw error
    const stale = readLock()
    if (!stale || !recordedHelperIsGone(stale)) {
      throw new Error('feature build contract is already materializing shared node_modules')
    }
    if (existsSync(stale.stage)) rmSync(stale.stage, { recursive: true, force: true })
    unlinkSync(lockPath)
    fd = openSync(lockPath, 'wx', 0o600)
  }
  const group = currentProcessGroupId(process.pid)
  if (process.platform !== 'win32' && group !== process.pid) {
    closeSync(fd)
    unlinkSync(lockPath)
    throw new Error('feature build helper did not become its own process-group leader')
  }
  writeLock(fd, {
    version: 3,
    pid: process.pid,
    pgid: group || process.pid,
    nonce,
    stage,
    state: 'starting',
  })
  return fd
}

function run(command, args, cwd) {
  return new Promise((resolvePromise, reject) => {
    let child
    try {
      child = spawn(command, args, {
        cwd,
        env: process.env,
        stdio: 'inherit',
        // Children inherit the helper's recorded group. Never detach a build
        // child, because the group is the recovery authority.
        detached: false,
      })
    } catch (error) {
      reject(error)
      return
    }
    child.once('error', reject)
    child.once('close', status => resolvePromise(status ?? 1))
  })
}

async function verify(rootDir) {
  return run(process.execPath, [join(rootDir, verifyScriptName)], rootDir)
}

async function directBuild(rootDir) {
  const canonicalRoot = realpathSync(rootDir)
  const next = join(canonicalRoot, 'node_modules', '.bin', 'next')
  const status = await run(next, ['build', 'tests/build-contract'], canonicalRoot)
  return status === 0 ? verify(canonicalRoot) : status
}

async function materializeStage(stage, target) {
  const rsync = process.env.RSYNC_BIN || '/usr/bin/rsync'
  const syncProject = await run(
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
  const syncDependencies = await run(
    rsync,
    ['-a', '--link-dest', target, `${target}/`, `${stageNodeModules}/`],
    frontendDir,
  )
  if (syncDependencies !== 0) {
    throw new Error(`rsync dependency materialization failed (${syncDependencies})`)
  }
  return directBuild(stage)
}

async function runHelper() {
  const [, , , requestedStageParent, target, nonce, requestedLockPath] = process.argv
  if (
    requestedStageParent !== stageParent ||
    requestedLockPath !== lockPath ||
    !isSafeNonce(nonce) ||
    typeof target !== 'string' ||
    !target.startsWith('/')
  ) {
    throw new Error('feature build helper arguments are invalid')
  }

  const stage = join(stageParent, `${stagePrefix}${nonce}`)
  let lockFd
  try {
    lockFd = acquireLock(stage, nonce)
    mkdirSync(stage, { mode: 0o700 })
    writeLock(lockFd, {
      version: 3,
      pid: process.pid,
      pgid: currentProcessGroupId(process.pid) || process.pid,
      nonce,
      stage,
      state: 'running',
    })
    return await materializeStage(stage, target)
  } finally {
    try {
      if (stageIsSafe(stage) && existsSync(stage)) {
        rmSync(stage, { recursive: true, force: true })
      }
    } finally {
      if (lockFd) {
        closeSync(lockFd)
        if (existsSync(lockPath)) unlinkSync(lockPath)
      }
    }
  }
}

async function runParent() {
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
  const nonce = randomBytes(16).toString('hex')
  const helper = spawn(
    process.execPath,
    [scriptPath, '--feature-build-helper', stageParent, target, nonce, lockPath],
    {
      cwd: frontendDir,
      env: process.env,
      stdio: 'inherit',
      detached: process.platform !== 'win32',
    },
  )
  if (!helper.pid) throw new Error('feature build helper did not receive a process identity')
  return new Promise((resolvePromise, reject) => {
    helper.once('error', reject)
    helper.once('close', status => resolvePromise(status ?? 1))
  })
}

try {
  process.exitCode = helperMode ? await runHelper() : await runParent()
} catch (error) {
  console.error(error?.message || 'feature build contract failed')
  process.exitCode = 1
}
