import {
  closeSync,
  existsSync,
  fsyncSync,
  lstatSync,
  mkdirSync,
  openSync,
  readFileSync,
  readdirSync,
  realpathSync,
  renameSync,
  rmdirSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { createHash, randomBytes } from "node:crypto";
import { dirname, join, resolve } from "node:path";
import { execFileSync, spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptPath = fileURLToPath(import.meta.url);
const frontendDir = resolve(dirname(scriptPath), "..");
const nodeModules = join(frontendDir, "node_modules");
const verifyScriptName = join("scripts", "verify-feature-env-build.mjs");
const stageParent = resolve(process.env.TMPDIR || "/tmp");
const stagePrefix = "deeper-notebook-feature-contract-";
const frontendKey = createHash("sha256")
  .update(frontendDir)
  .digest("hex")
  .slice(0, 24);
const lockPath = join(
  stageParent,
  `deeper-notebook-feature-build-${frontendKey}.lock`,
);
const lockName = `${basename(lockPath)}`;
const lockQuarantinePrefix = `${lockName}.quarantine-`;
const lockCleanupPrefix = `${lockName}.cleanup-`;
const helperMode = process.argv[2] === "--feature-build-helper";

function basename(value) {
  return value.slice(value.lastIndexOf("/") + 1);
}

function safeLstat(path) {
  try {
    return lstatSync(path);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function processSnapshot(pid) {
  if (!Number.isInteger(pid) || pid <= 1) return null;
  try {
    const stat = execFileSync("ps", ["-o", "stat=", "-p", String(pid)], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    const startToken = execFileSync(
      "ps",
      ["-o", "lstart=", "-p", String(pid)],
      { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] },
    ).trim();
    const command = execFileSync("ps", ["-o", "command=", "-p", String(pid)], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
    const pgid = Number(
      execFileSync("ps", ["-o", "pgid=", "-p", String(pid)], {
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      }).trim(),
    );
    if (
      !stat ||
      !startToken ||
      !command ||
      !Number.isInteger(pgid) ||
      pgid <= 1
    ) {
      return null;
    }
    return {
      argvHash: createHash("sha256").update(command).digest("hex"),
      command,
      pgid,
      startToken,
      stat,
      zombie: /^Z/.test(stat),
    };
  } catch (error) {
    // EPERM is deliberately not converted to “gone”: callers must fail closed
    // when process identity cannot be inspected.
    if (error?.code === "EPERM") throw error;
    return null;
  }
}

function processIsAlive(pid) {
  const snapshot = processSnapshot(pid);
  return Boolean(snapshot && !snapshot.zombie);
}

function processGroupMembers(pgid) {
  if (!Number.isInteger(pgid) || pgid <= 1) return null;
  try {
    const output = execFileSync("ps", ["-axo", "pid=,pgid=,stat="], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    });
    const members = [];
    for (const line of output.split("\n")) {
      const match = line.trim().match(/^(\d+)\s+(\d+)\s+(\S+)/);
      if (!match) {
        if (line.trim()) return null;
        continue;
      }
      if (Number(match[2]) === pgid) {
        members.push({ pid: Number(match[1]), stat: match[3] });
      }
    }
    return members;
  } catch (error) {
    if (error?.code === "EPERM") throw error;
    return null;
  }
}

function currentProcessGroupId(pid) {
  const snapshot = processSnapshot(pid);
  return snapshot?.pgid || null;
}

function isSafeNonce(value) {
  return typeof value === "string" && /^[a-f0-9]{32}$/.test(value);
}

function isSafeStagePath(candidate) {
  if (
    typeof candidate !== "string" ||
    !candidate.startsWith(`${stageParent}/`)
  ) {
    return false;
  }
  const relative = candidate.slice(stageParent.length + 1);
  return !relative.includes("/") && relative.startsWith(stagePrefix);
}

function isSafeLockDirectory(path) {
  if (
    path !== lockPath &&
    !path.startsWith(`${stageParent}/${lockQuarantinePrefix}`) &&
    !path.startsWith(`${stageParent}/${lockCleanupPrefix}`)
  ) {
    return false;
  }
  const stat = safeLstat(path);
  return Boolean(stat && stat.isDirectory() && !stat.isSymbolicLink());
}

function stageIsSafe(stage) {
  if (!isSafeStagePath(stage)) return false;
  const stat = safeLstat(stage);
  return !stat || (stat.isDirectory() && !stat.isSymbolicLink());
}

function ownerPath(lockDirectory) {
  return join(lockDirectory, "owner.json");
}

function validateOwner(value) {
  if (
    !value ||
    value.version !== 4 ||
    !Number.isInteger(value.pid) ||
    value.pid <= 1 ||
    !Number.isInteger(value.pgid) ||
    value.pgid <= 1 ||
    !isSafeNonce(value.nonce) ||
    typeof value.startToken !== "string" ||
    value.startToken.length < 8 ||
    !/^[a-f0-9]{64}$/.test(value.argvHash || "") ||
    !isSafeStagePath(value.stage) ||
    value.stage !== join(stageParent, `${stagePrefix}${value.nonce}`) ||
    !["starting", "running"].includes(value.state) ||
    !stageIsSafe(value.stage)
  ) {
    throw new Error("invalid feature build lock owner");
  }
  return value;
}

function readOwner(lockDirectory) {
  if (!isSafeLockDirectory(lockDirectory)) {
    throw new Error("feature build lock directory is unsafe");
  }
  const path = ownerPath(lockDirectory);
  const stat = safeLstat(path);
  if (!stat) return null;
  if (!stat.isFile() || stat.isSymbolicLink()) {
    throw new Error("feature build lock owner metadata is unsafe");
  }
  try {
    return validateOwner(JSON.parse(readFileSync(path, "utf8")));
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw new Error(
      "feature build lock is malformed; remove only the exact stale lock after inspection",
    );
  }
}

function writeOwnerAtomically(lockDirectory, owner) {
  if (!isSafeLockDirectory(lockDirectory)) {
    throw new Error("feature build lock directory is unsafe");
  }
  const path = ownerPath(lockDirectory);
  const current = safeLstat(path);
  if (current && (!current.isFile() || current.isSymbolicLink())) {
    throw new Error("feature build lock owner metadata is unsafe");
  }
  const tempPath = join(
    lockDirectory,
    `.owner-${owner.nonce}-${randomBytes(8).toString("hex")}.tmp`,
  );
  const fd = openSync(tempPath, "wx", 0o600);
  try {
    writeFileSync(fd, JSON.stringify(owner), { encoding: "utf8" });
    fsyncSync(fd);
  } finally {
    closeSync(fd);
  }
  renameSync(tempPath, path);
  try {
    const directoryFd = openSync(lockDirectory, "r");
    try {
      fsyncSync(directoryFd);
    } finally {
      closeSync(directoryFd);
    }
  } catch {
    // Some platforms do not permit fsync on a directory. The file was already
    // fsynced before the atomic rename, so readers still see complete JSON.
  }
}

function sameOwner(left, right) {
  return Boolean(
    left &&
    right &&
    left.version === right.version &&
    left.nonce === right.nonce &&
    left.pid === right.pid &&
    left.pgid === right.pgid &&
    left.startToken === right.startToken &&
    left.argvHash === right.argvHash &&
    left.stage === right.stage,
  );
}

function recordedOwnerIsGone(owner) {
  let process;
  try {
    process = processSnapshot(owner.pid);
  } catch {
    return false;
  }
  if (process && process.zombie) return false;
  if (
    process &&
    process.startToken === owner.startToken &&
    process.argvHash === owner.argvHash
  ) {
    return false;
  }
  if (!process && processIsAlive(owner.pid)) return false;
  // A PID with a different start/argv identity is a safe mismatch: it is not
  // the recorded helper. The process-group proof below still has to be empty.
  let members;
  try {
    members = processGroupMembers(owner.pgid);
  } catch {
    return false;
  }
  if (!members) return false;
  return members.length === 0;
}

function removeTreeWithoutFollowingSymlinks(path) {
  const stat = safeLstat(path);
  if (!stat) return;
  if (stat.isSymbolicLink()) {
    unlinkSync(path);
    return;
  }
  if (stat.isDirectory()) {
    for (const entry of readdirSync(path)) {
      removeTreeWithoutFollowingSymlinks(join(path, entry));
    }
    rmdirSync(path);
    return;
  }
  unlinkSync(path);
}

function removeOwnedStage(stage, owner) {
  if (!stageIsSafe(stage)) {
    throw new Error("feature build stale stage is unsafe");
  }
  // The owner record binds the stage name to the nonce. Do not delete a path
  // merely because it happens to share the feature-build prefix.
  if (stage !== owner.stage || !isSafeNonce(owner.nonce)) {
    throw new Error("feature build stale stage ownership is ambiguous");
  }
  removeTreeWithoutFollowingSymlinks(stage);
}

function removeOwnedLockDirectory(lockDirectory, owner) {
  const current = readOwner(lockDirectory);
  if (!sameOwner(current, owner)) {
    throw new Error("feature build lock ownership changed during cleanup");
  }
  const path = ownerPath(lockDirectory);
  unlinkSync(path);
  rmdirSync(lockDirectory);
}

function quarantineName(owner, label = "quarantine") {
  const suffix = `${label}-${owner.nonce}-${randomBytes(8).toString("hex")}`;
  return join(stageParent, `${lockName}.${suffix}`);
}

function recoveryClaimPath(owner) {
  return join(stageParent, `${lockName}.recovery-${owner.nonce}`);
}

function claimStaleRecovery(owner) {
  const claim = recoveryClaimPath(owner);
  try {
    mkdirSync(claim, { mode: 0o700 });
    return claim;
  } catch (error) {
    if (error?.code === "EEXIST") return null;
    throw new Error(
      "feature build stale recovery claim could not be acquired safely",
    );
  }
}

function releaseRecoveryClaim(claim) {
  const stat = safeLstat(claim);
  if (!stat) return;
  if (!stat.isDirectory() || stat.isSymbolicLink()) return;
  try {
    rmdirSync(claim);
  } catch {
    // A leftover claim is safer than allowing another process to guess stale
    // ownership after a recovery failure.
  }
}

function recoverStaleLock() {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const lockStat = safeLstat(lockPath);
    if (!lockStat) return false;
    if (!lockStat.isDirectory() || lockStat.isSymbolicLink()) {
      throw new Error(
        "feature build lock is malformed; remove only the exact stale lock after inspection",
      );
    }
    const stale = readOwner(lockPath);
    if (!stale || !recordedOwnerIsGone(stale)) {
      throw new Error(
        "feature build contract is already materializing shared node_modules",
      );
    }
    const claim = claimStaleRecovery(stale);
    if (!claim) {
      let current;
      try {
        current = readOwner(lockPath);
      } catch {
        throw new Error("feature build stale recovery is already claimed");
      }
      if (sameOwner(current, stale)) {
        throw new Error("feature build stale recovery is already claimed");
      }
      continue;
    }
    const quarantine = quarantineName(stale);
    try {
      // The sibling claim is the compare-and-swap gate. Other contenders
      // cannot rename this stale lock after the claim without first losing the
      // same nonce-specific mkdir race.
      const confirmed = readOwner(lockPath);
      if (!sameOwner(confirmed, stale) || !recordedOwnerIsGone(confirmed)) {
        throw new Error(
          "feature build stale lock changed during recovery claim",
        );
      }
      renameSync(lockPath, quarantine);
    } catch (error) {
      releaseRecoveryClaim(claim);
      if (error?.code === "ENOENT" || error?.code === "EEXIST") continue;
      throw new Error(
        "feature build stale lock could not be quarantined safely",
      );
    }
    try {
      const quarantinedOwner = readOwner(quarantine);
      if (!sameOwner(quarantinedOwner, stale)) {
        throw new Error(
          "feature build stale lock ownership changed during quarantine",
        );
      }
      removeOwnedStage(quarantinedOwner.stage, quarantinedOwner);
      removeOwnedLockDirectory(quarantine, quarantinedOwner);
      releaseRecoveryClaim(claim);
      return true;
    } catch (error) {
      // Never touch a successor at lockPath. The stale directory is already
      // isolated under its nonce-specific quarantine for manual inspection.
      throw error;
    }
  }
  throw new Error(
    "feature build lock changed during stale recovery; retry refused",
  );
}

function acquireLock(stage, nonce) {
  const identity = processSnapshot(process.pid);
  if (!identity || identity.zombie) {
    throw new Error("feature build helper identity could not be established");
  }
  const group = currentProcessGroupId(process.pid);
  if (process.platform !== "win32" && group !== process.pid) {
    throw new Error(
      "feature build helper did not become its own process-group leader",
    );
  }
  const owner = {
    argvHash: identity.argvHash,
    nonce,
    pgid: group || process.pid,
    pid: process.pid,
    stage,
    startToken: identity.startToken,
    state: "starting",
    version: 4,
  };
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      mkdirSync(lockPath, { mode: 0o700 });
      writeOwnerAtomically(lockPath, owner);
      return owner;
    } catch (error) {
      if (error?.code !== "EEXIST") throw error;
      recoverStaleLock();
    }
  }
  throw new Error(
    "feature build lock changed during acquisition; retry refused",
  );
}

function releaseLock(owner) {
  const current = safeLstat(lockPath);
  if (!current) return;
  if (!current.isDirectory() || current.isSymbolicLink()) return;
  let currentOwner;
  try {
    currentOwner = readOwner(lockPath);
  } catch {
    return;
  }
  if (!sameOwner(currentOwner, owner)) return;
  let currentIdentity;
  try {
    currentIdentity = processSnapshot(process.pid);
  } catch {
    return;
  }
  if (
    !currentIdentity ||
    currentIdentity.zombie ||
    currentIdentity.startToken !== owner.startToken ||
    currentIdentity.argvHash !== owner.argvHash ||
    currentIdentity.pgid !== owner.pgid
  ) {
    return;
  }
  const quarantine = quarantineName(owner, "cleanup");
  try {
    renameSync(lockPath, quarantine);
  } catch {
    return;
  }
  try {
    const quarantinedOwner = readOwner(quarantine);
    if (!sameOwner(quarantinedOwner, owner)) return;
    removeOwnedStage(quarantinedOwner.stage, quarantinedOwner);
    removeOwnedLockDirectory(quarantine, quarantinedOwner);
  } catch {
    // Leave the nonce-specific quarantine intact for a later bounded recovery.
  }
}

function run(command, args, cwd) {
  return new Promise((resolvePromise, reject) => {
    let child;
    try {
      child = spawn(command, args, {
        cwd,
        env: process.env,
        stdio: "inherit",
        // Children inherit the helper's recorded group. Never detach a build
        // child, because the group is the recovery authority.
        detached: false,
      });
    } catch (error) {
      reject(error);
      return;
    }
    child.once("error", reject);
    child.once("close", (status) => resolvePromise(status ?? 1));
  });
}

async function verify(rootDir) {
  return run(process.execPath, [join(rootDir, verifyScriptName)], rootDir);
}

async function directBuild(rootDir) {
  const canonicalRoot = realpathSync(rootDir);
  const next = join(canonicalRoot, "node_modules", ".bin", "next");
  const status = await run(
    next,
    ["build", "tests/build-contract"],
    canonicalRoot,
  );
  return status === 0 ? verify(canonicalRoot) : status;
}

async function materializeStage(stage, target) {
  const rsync = process.env.RSYNC_BIN || "/usr/bin/rsync";
  const syncProject = await run(
    rsync,
    [
      "-a",
      "--exclude",
      "node_modules",
      "--exclude",
      ".next",
      "--exclude",
      `${stagePrefix}*`,
      `${frontendDir}/`,
      `${stage}/`,
    ],
    frontendDir,
  );
  if (syncProject !== 0)
    throw new Error(`feature build project staging failed (${syncProject})`);

  const stageNodeModules = join(stage, "node_modules");
  mkdirSync(stageNodeModules);
  const syncDependencies = await run(
    rsync,
    ["-a", "--link-dest", target, `${target}/`, `${stageNodeModules}/`],
    frontendDir,
  );
  if (syncDependencies !== 0) {
    throw new Error(
      `rsync dependency materialization failed (${syncDependencies})`,
    );
  }
  return directBuild(stage);
}

async function runHelper() {
  const [, , , requestedStageParent, target, nonce, requestedLockPath] =
    process.argv;
  if (
    requestedStageParent !== stageParent ||
    requestedLockPath !== lockPath ||
    !isSafeNonce(nonce) ||
    typeof target !== "string" ||
    !target.startsWith("/")
  ) {
    throw new Error("feature build helper arguments are invalid");
  }

  const stage = join(stageParent, `${stagePrefix}${nonce}`);
  let owner;
  try {
    owner = acquireLock(stage, nonce);
    mkdirSync(stage, { mode: 0o700 });
    owner = { ...owner, state: "running" };
    writeOwnerAtomically(lockPath, owner);
    return await materializeStage(stage, target);
  } finally {
    if (owner) releaseLock(owner);
  }
}

async function runParent() {
  if (!lstatSync(nodeModules).isSymbolicLink()) return directBuild(frontendDir);
  const target = realpathSync(nodeModules);
  if (target === frontendDir || target.startsWith(`${frontendDir}/`)) {
    return directBuild(frontendDir);
  }
  const rsync = process.env.RSYNC_BIN || "/usr/bin/rsync";
  if (!existsSync(rsync)) {
    throw new Error(
      "shared node_modules requires /usr/bin/rsync for a safe local materialization",
    );
  }
  if (!existsSync(stageParent)) {
    throw new Error("feature build temporary directory does not exist");
  }
  const nonce = randomBytes(16).toString("hex");
  const helper = spawn(
    process.execPath,
    [
      scriptPath,
      "--feature-build-helper",
      stageParent,
      target,
      nonce,
      lockPath,
    ],
    {
      cwd: frontendDir,
      env: process.env,
      stdio: "inherit",
      detached: process.platform !== "win32",
    },
  );
  if (!helper.pid)
    throw new Error("feature build helper did not receive a process identity");
  return new Promise((resolvePromise, reject) => {
    helper.once("error", reject);
    helper.once("close", (status) => resolvePromise(status ?? 1));
  });
}

try {
  process.exitCode = helperMode ? await runHelper() : await runParent();
} catch (error) {
  console.error(error?.message || "feature build contract failed");
  process.exitCode = 1;
}
