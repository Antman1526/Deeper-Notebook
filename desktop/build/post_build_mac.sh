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

rm -f "${DMG_PATH}"
hdiutil create -volname "${APP_NAME}" \
               -srcfolder "${APP_PATH}" \
               -ov -format UDZO "${DMG_PATH}"
echo "Built ${DMG_PATH}"
