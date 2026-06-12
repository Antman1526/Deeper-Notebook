#!/usr/bin/env bash
# desktop/build/post_build_mac.sh — wrap dist/Open Notebook Plus.app into a .dmg
set -euo pipefail

APP_NAME="Open Notebook Plus"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="Open-Notebook-Plus"
DMG_PATH="dist/${DMG_NAME}-mac-$(uname -m).dmg"

if [[ ! -d "${APP_PATH}" ]]; then
  echo "ERROR: ${APP_PATH} not found. Run pyinstaller first." >&2
  exit 1
fi

# v0.8.67k — detach any stale mount of a prior ONP .dmg before creating a new
# one. A left-over mounted image (common after an interrupted build, or when
# the Finder auto-mounts the previous .dmg) made `hdiutil create` fail with
# "hdiutil: create failed - Resource busy", which aborted the whole build at
# the dmg step even though dist/Open Notebook Plus.app was already complete.
for _dev in $(hdiutil info 2>/dev/null | grep -iE 'Open Notebook' | grep -oE '/dev/disk[0-9]+' | sort -u); do
  hdiutil detach "${_dev}" -force >/dev/null 2>&1 || true
done

rm -f "${DMG_PATH}"
hdiutil create -volname "${APP_NAME}" \
               -srcfolder "${APP_PATH}" \
               -ov -format UDZO "${DMG_PATH}"
echo "Built ${DMG_PATH}"
