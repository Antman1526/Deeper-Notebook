#!/usr/bin/env bash
#
# scripts/create-signing-identity.sh — v0.8.67k
#
# Create a STABLE self-signed code-signing identity so the desktop app is
# re-signed with the SAME identity on every rebuild:
#
#     bash scripts/create-signing-identity.sh
#     make build-mac ONP_CODESIGN_IDENTITY="Open Notebook Plus Local"
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
# ad-hoc) unless you pass ONP_CODESIGN_IDENTITY.
#
# This is a LOCAL-DEV convenience, NOT notarization — the app is still not
# Apple-notarized; first launch may still need right-click → Open.
set -euo pipefail

IDENTITY="${1:-Open Notebook Plus Local}"
KEYCHAIN="${HOME}/Library/Keychains/login.keychain-db"

if security find-identity -v -p codesigning "$KEYCHAIN" 2>/dev/null | grep -qF "$IDENTITY"; then
  echo "✅ Code-signing identity '$IDENTITY' already exists. Nothing to do."
  echo "   Build with:  make build-mac ONP_CODESIGN_IDENTITY=\"$IDENTITY\""
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

echo "🔑 Generating self-signed code-signing cert '$IDENTITY' (valid 10 years)…"
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout "$TMP/key.pem" -out "$TMP/cert.pem" -config "$CONF" >/dev/null 2>&1
openssl pkcs12 -export -inkey "$TMP/key.pem" -in "$TMP/cert.pem" \
  -name "$IDENTITY" -out "$TMP/identity.p12" -passout pass: >/dev/null 2>&1

echo "📥 Importing into login keychain…"
security import "$TMP/identity.p12" -k "$KEYCHAIN" -P "" \
  -T /usr/bin/codesign -T /usr/bin/security >/dev/null 2>&1

# Trust for code signing (best-effort; may prompt for your login password).
security add-trusted-cert -d -r trustAsRoot -p codeSign -k "$KEYCHAIN" "$TMP/cert.pem" >/dev/null 2>&1 || \
  echo "   (could not auto-trust; codesign still works with the imported key)"

# Allow codesign to use the key without an interactive prompt each build
# (best-effort; assumes the login keychain is unlocked).
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "" "$KEYCHAIN" >/dev/null 2>&1 || true

if security find-identity -v -p codesigning "$KEYCHAIN" 2>/dev/null | grep -qF "$IDENTITY"; then
  echo "✅ Created '$IDENTITY'."
  echo "   Build with:  make build-mac ONP_CODESIGN_IDENTITY=\"$IDENTITY\""
else
  echo "❌ Identity not found after import — see any errors above." >&2
  exit 1
fi
