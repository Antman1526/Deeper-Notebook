#!/usr/bin/env bash
#
# scripts/create-signing-identity.sh — v0.8.67k
#
# Create a STABLE self-signed code-signing identity so the desktop app is
# re-signed with the SAME identity on every rebuild:
#
#     bash scripts/create-signing-identity.sh
#     make build-mac DEEPER_NOTEBOOK_CODESIGN_IDENTITY="Deeper Notebook Local"
#
# Why: the default build re-seals with an ad-hoc signature (`codesign --sign -`),
# which gives the app a NEW cryptographic identity every rebuild. macOS ties
# TCC (Files & Folders / Automation) permissions to that identity, so every
# ad-hoc rebuild RESETS those grants — the root cause of the iCloud/Desktop
# `os.scandir` boot-wedge seen in the field. A stable identity keeps the grants
# across rebuilds (and reduces Gatekeeper friction).
#
# SAFE + idempotent: only ADDS a self-signed cert to YOUR login keychain. It
# does not touch the app build, network, or any secrets. Re-running is a no-op
# if the identity already exists. Default `make build-mac` is UNCHANGED (still
# ad-hoc) unless you pass DEEPER_NOTEBOOK_CODESIGN_IDENTITY.
#
# This is a LOCAL-DEV convenience, NOT notarization — the app is still not
# Apple-notarized; first launch may still need right-click → Open.
set -euo pipefail

IDENTITY="${1:-Deeper Notebook Local}"
KEYCHAIN="${HOME}/Library/Keychains/login.keychain-db"

# v0.8.85 — check WITHOUT -v: an imported-but-untrusted identity is invisible
# to `find-identity -v`, which made this script re-import duplicates and then
# report failure even though the identity existed (seen live on macOS 15+).
if security find-identity -p codesigning "$KEYCHAIN" 2>/dev/null | grep -qF "$IDENTITY"; then
  echo "✅ Code-signing identity '$IDENTITY' already exists. Nothing to do."
  echo "   Build with:  make build-mac DEEPER_NOTEBOOK_CODESIGN_IDENTITY=\"$IDENTITY\""
  exit 0
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
CONF="$TMP/openssl.cnf"
cat > "$CONF" <<EOF
[ req ]
distinguished_name = dn
x509_extensions = ext
prompt = no
[ dn ]
CN = $IDENTITY
[ ext ]
keyUsage = critical, digitalSignature
extendedKeyUsage = critical, codeSigning
basicConstraints = critical, CA:false
EOF

# v0.8.70 — use the SYSTEM openssl (/usr/bin/openssl = LibreSSL), not whatever
# `openssl` resolves to on PATH. Homebrew's OpenSSL 3 exports a PKCS#12 whose
# MAC algorithm Apple's `security import` can't verify ("MAC verification failed
# during PKCS12 import"), so the import silently failed and no identity was
# created. LibreSSL produces a macOS-importable p12 with no extra flags.
OPENSSL="/usr/bin/openssl"
[ -x "$OPENSSL" ] || OPENSSL="openssl"  # fall back to PATH if system one is gone

echo "🔑 Generating self-signed code-signing cert '$IDENTITY' (valid 10 years)…"
"$OPENSSL" req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout "$TMP/key.pem" -out "$TMP/cert.pem" -config "$CONF" >/dev/null 2>&1
# v0.8.70 — the p12 MUST carry a non-empty password. An empty-password p12
# fails `security import` with "MAC verification failed" (the importer can't
# verify the MAC over an empty passphrase). It's a throwaway that only protects
# this transient temp file, so a fixed constant is fine.
P12_PASS="onp-local-signing"
"$OPENSSL" pkcs12 -export -inkey "$TMP/key.pem" -in "$TMP/cert.pem" \
  -name "$IDENTITY" -out "$TMP/identity.p12" -passout "pass:${P12_PASS}" >/dev/null 2>&1

echo "📥 Importing into login keychain…"
security import "$TMP/identity.p12" -k "$KEYCHAIN" -P "${P12_PASS}" \
  -T /usr/bin/codesign -T /usr/bin/security >/dev/null 2>&1

# Trust for code signing. v0.8.85 — a SELF-SIGNED cert is its own root, so the
# result type must be trustRoot; trustAsRoot is rejected with "parameters not
# valid" on current macOS, which left the identity CSSMERR_TP_NOT_TRUSTED and
# codesign unable to use it. User trust domain (no -d): no admin prompt needed.
security add-trusted-cert -r trustRoot -p codeSign -k "$KEYCHAIN" "$TMP/cert.pem" || \
  echo "   ⚠️  could not trust the cert; codesign will reject the identity" >&2

# Allow codesign to use the key without an interactive prompt each build
# (best-effort; assumes the login keychain is unlocked).
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "" "$KEYCHAIN" >/dev/null 2>&1 || true

if security find-identity -v -p codesigning "$KEYCHAIN" 2>/dev/null | grep -qF "$IDENTITY"; then
  echo "✅ Created '$IDENTITY' (valid for codesigning)."
  echo "   Build with:  make build-mac DEEPER_NOTEBOOK_CODESIGN_IDENTITY=\"$IDENTITY\""
else
  echo "❌ Identity not found after import — see any errors above." >&2
  exit 1
fi
