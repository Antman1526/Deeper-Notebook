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

detach_stale_deeper_notebook_images() {
  # A left-over mounted image (common after an interrupted build, or when
  # Finder auto-mounts a previous .dmg) can leave DiskImages temporarily busy.
  for _dev in $(hdiutil info 2>/dev/null | grep -iE 'Deeper Notebook' | grep -oE '/dev/disk[0-9]+' | sort -u); do
    hdiutil detach "${_dev}" -force >/dev/null 2>&1 || true
  done
}

detach_stale_deeper_notebook_images
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

DMG_CREATE_ATTEMPTS=3
_dmg_created=false
for ((_attempt = 1; _attempt <= DMG_CREATE_ATTEMPTS; _attempt++)); do
  rm -f "${DMG_PATH}"
  if _output="$(
    hdiutil create -volname "${APP_NAME}" \
      -srcfolder "${STAGE}" \
      -ov -format UDZO "${DMG_PATH}" 2>&1
  )"; then
    printf '%s\n' "${_output}"
    _dmg_created=true
    break
  else
    _status=$?
  fi

  printf '%s\n' "${_output}" >&2
  if [[ "${_output}" != *"Resource busy"* ]] || (( _attempt == DMG_CREATE_ATTEMPTS )); then
    exit "${_status}"
  fi
  echo "DiskImages is busy; retrying DMG creation (${_attempt}/${DMG_CREATE_ATTEMPTS})." >&2
  detach_stale_deeper_notebook_images
  sleep "${_attempt}"
done

if [[ "${_dmg_created}" != true ]]; then
  echo "ERROR: DMG creation completed without an image." >&2
  exit 1
fi
hdiutil verify "${DMG_PATH}"
echo "Built ${DMG_PATH} (with /Applications drag target)"
