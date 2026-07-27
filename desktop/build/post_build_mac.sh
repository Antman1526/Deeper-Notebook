#!/usr/bin/env bash
# desktop/build/post_build_mac.sh — wrap dist/Deeper Notebook.app into a .dmg
set -euo pipefail

APP_NAME="Deeper Notebook"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="Deeper-Notebook"
DMG_PATH="dist/${DMG_NAME}-mac-$(uname -m).dmg"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "ERROR: ${APP_PATH} not found. Run pyinstaller first." >&2
  exit 1
fi

# Detach any stale mount of a prior Deeper Notebook .dmg before creating a new
# one. A left-over mounted image (common after an interrupted build, or when
# the Finder auto-mounts the previous .dmg) made `hdiutil create` fail with
# "hdiutil: create failed - Resource busy", which aborted the whole build at
# the dmg step even though dist/Deeper Notebook.app was already complete.
for _dev in $(hdiutil info 2>/dev/null | grep -iE 'Deeper Notebook' | grep -oE '/dev/disk[0-9]+' | sort -u); do
  hdiutil detach "${_dev}" -force >/dev/null 2>&1 || true
done

rm -f "${DMG_PATH}"

# v0.8.70 — stage the .app alongside an /Applications symlink so the mounted
# DMG shows a "drag to Applications" target. Previously the DMG contained ONLY
# the .app, so users double-clicked it IN PLACE and ran it off the read-only,
# compressed UDZO mount — markedly slower to launch (every bundled dylib/python
# file decompresses on read) and re-triggers a Gatekeeper scan of the unsigned
# bundle each time. Guiding installation to /Applications (local SSD, cached
# Gatekeeper assessment) is the fix. No external tool needed — `create-dmg`
# isn't required for the functional symlink affordance.
STAGE="$(mktemp -d)"
trap 'rm -rf "${STAGE}"' EXIT
cp -R "${APP_PATH}" "${STAGE}/"
ln -s /Applications "${STAGE}/Applications"

hdiutil create -volname "${APP_NAME}" \
               -srcfolder "${STAGE}" \
               -ov -format UDZO "${DMG_PATH}"
echo "Built ${DMG_PATH} (with /Applications drag target)"
