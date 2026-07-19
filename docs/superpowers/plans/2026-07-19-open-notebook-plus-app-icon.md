# Open Notebook Plus App Icon Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current blue Open Notebook Plus icon with the approved Premium Dimensional notebook across macOS, Windows, and the frontend favicon.

**Architecture:** A normalized 1024 x 1024 RGBA PNG remains the single source of truth in `desktop/resources/icon.png`. The existing Pillow-based generator is simplified to validate that master and derive ICNS, Windows ICO, and browser favicon assets without redrawing or mutating the master.

**Tech Stack:** OpenAI image generation/editing, Pillow, macOS `iconutil`, Python `unittest`/pytest, PyInstaller, `codesign`, `hdiutil`.

## Global Constraints

- Preserve the approved ink-blue cloth notebook, white pages, coral bookmark, mint and gold tabs, and embossed knowledge network.
- The master must be exactly 1024 x 1024 RGBA with genuine transparent pixels outside the notebook silhouette.
- Keep the icon recognizable at 16, 24, 32, and 48 pixels.
- Include no text, initials, watermark, extra objects, or decorative backdrop.
- Preserve the application name, bundle identifiers, and runtime behavior.

---

### Task 1: Normalize the Approved Master

**Files:**
- Input: `/Users/Antman/.codex/generated_images/019ef365-d194-7d13-8e57-217ec2642247/exec-2a3f651a-05b8-4518-b5b8-05eadea4999b.png`
- Modify: `desktop/resources/icon.png`

**Interfaces:**
- Consumes: approved Premium Dimensional render.
- Produces: `desktop/resources/icon.png`, a 1024 x 1024 RGBA master with true alpha.

- [ ] **Step 1: Remove the rendered checkerboard with an image edit**

Use the approved render as the sole reference. Request a precise background extraction: remove only the gray/white checkerboard, preserve all notebook geometry, textures, colors, shadows, tabs, bookmark, and embossing, and return true transparency.

- [ ] **Step 2: Inspect the edited output before repository use**

Run:

```bash
sips -g pixelWidth -g pixelHeight -g hasAlpha /absolute/path/to/edited-output.png
```

Expected: a square image with `hasAlpha: yes` and no checkerboard pixels visible outside the notebook.

- [ ] **Step 3: Normalize the canvas with Pillow**

Use Pillow to resize proportionally with `Image.Resampling.LANCZOS`, fit the notebook inside an 880 x 880 bounding area, and center it on a transparent 1024 x 1024 RGBA canvas. Preserve soft edge alpha and do not add a background or macOS squircle.

- [ ] **Step 4: Verify alpha and margins**

Run:

```bash
python3 - <<'PY'
from PIL import Image
path = "desktop/resources/icon.png"
image = Image.open(path)
alpha = image.getchannel("A")
assert image.size == (1024, 1024)
assert image.mode == "RGBA"
assert alpha.getextrema() == (0, 255)
assert all(image.getpixel(point)[3] == 0 for point in ((0, 0), (1023, 0), (0, 1023), (1023, 1023)))
print("master icon: valid RGBA with transparent corners")
PY
```

Expected: `master icon: valid RGBA with transparent corners`.

### Task 2: Make Platform Asset Generation Deterministic

**Files:**
- Modify: `desktop/resources/make_icon.py`
- Create: `desktop/tests/test_icon_assets.py`

**Interfaces:**
- Consumes: `desktop/resources/icon.png`.
- Produces: `load_master() -> Image.Image`, `write_mac_icns(master)`, `write_win_ico(master)`, and `write_favicon(master)`.

- [ ] **Step 1: Write failing asset-pipeline tests**

Create `desktop/tests/test_icon_assets.py`:

```python
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).parents[1] / "resources"


def test_master_icon_is_transparent_rgba():
    image = Image.open(ROOT / "icon.png")
    assert image.mode == "RGBA"
    assert image.size == (1024, 1024)
    assert image.getchannel("A").getextrema() == (0, 255)
    assert all(
        image.getpixel(point)[3] == 0
        for point in ((0, 0), (1023, 0), (0, 1023), (1023, 1023))
    )


def test_generator_preserves_master_and_writes_ico_sets():
    master = ROOT / "icon.png"
    before = hashlib.sha256(master.read_bytes()).digest()
    subprocess.run([sys.executable, str(ROOT / "make_icon.py")], check=True)
    assert hashlib.sha256(master.read_bytes()).digest() == before

    with Image.open(ROOT / "icon.ico") as icon:
        assert icon.ico.sizes() == {
            (16, 16), (32, 32), (48, 48),
            (64, 64), (128, 128), (256, 256),
        }
    with Image.open(Path(__file__).parents[2] / "frontend/src/app/favicon.ico") as favicon:
        assert favicon.ico.sizes() == {(16, 16), (32, 32), (48, 48)}
```

- [ ] **Step 2: Run tests and confirm the generator mutates the master**

Run:

```bash
.build-venv/bin/python -m pytest desktop/tests/test_icon_assets.py -q
```

Expected: failure because the current generator redraws `icon.png` and does not write the frontend favicon.

- [ ] **Step 3: Replace procedural drawing with master validation**

In `desktop/resources/make_icon.py`, remove the gradient and book drawing functions. Add:

```python
MASTER_PATH = ROOT / "icon.png"
FAVICON_PATH = ROOT.parents[1] / "frontend" / "src" / "app" / "favicon.ico"


def load_master() -> Image.Image:
    master = Image.open(MASTER_PATH).convert("RGBA")
    if master.size != (SIZE, SIZE):
        raise ValueError(f"icon.png must be {SIZE}x{SIZE}; got {master.size}")
    if master.getchannel("A").getextrema()[0] != 0:
        raise ValueError("icon.png must contain transparent background pixels")
    return master


def write_favicon(master: Image.Image) -> None:
    FAVICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    master.save(
        FAVICON_PATH,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
    )
```

Update `main()` to call `load_master()`, `write_mac_icns()` on macOS, `write_win_ico()`, and `write_favicon()` without saving over `MASTER_PATH`.

- [ ] **Step 4: Run the focused tests**

Run:

```bash
.build-venv/bin/python -m pytest desktop/tests/test_icon_assets.py -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit the deterministic pipeline**

```bash
git add desktop/resources/icon.png desktop/resources/make_icon.py desktop/resources/icon.icns desktop/resources/icon.ico frontend/src/app/favicon.ico desktop/tests/test_icon_assets.py
git commit -m "feat: add premium notebook app icon"
```

### Task 3: Inspect Every Rendered Size

**Files:**
- Verify: `desktop/resources/icon.png`
- Verify: `desktop/resources/icon.icns`
- Verify: `desktop/resources/icon.ico`
- Verify: `frontend/src/app/favicon.ico`

**Interfaces:**
- Consumes: platform assets generated in Task 2.
- Produces: visual and metadata evidence that no platform size is clipped or illegible.

- [ ] **Step 1: Regenerate all icon assets**

Run:

```bash
.build-venv/bin/python desktop/resources/make_icon.py
```

Expected: the master remains unchanged and ICNS, ICO, and favicon files are rewritten successfully.

- [ ] **Step 2: Validate the macOS representation set**

Run:

```bash
TMP_ICONSET=$(mktemp -d)/OpenNotebookPlus.iconset
iconutil -c iconset desktop/resources/icon.icns -o "$TMP_ICONSET"
find "$TMP_ICONSET" -type f -name '*.png' -print | sort
```

Expected: 16, 32, 128, 256, 512, and Retina representations through 1024 pixels.

- [ ] **Step 3: Build and inspect a size contact sheet**

Create a temporary contact sheet with Pillow containing 16, 32, 64, 128, 256, 512, and 1024 pixel renders on both light and dark neutral backgrounds. Inspect it with the image viewer and confirm the notebook silhouette, coral bookmark, and tabs remain identifiable at 16 and 32 pixels.

- [ ] **Step 4: Run relevant test suites**

Run:

```bash
.build-venv/bin/python -m pytest desktop/tests/test_icon_assets.py desktop/tests/test_launcher.py -q
```

Expected: all selected tests pass.

### Task 4: Rebuild and Verify the macOS Installer

**Files:**
- Build: `dist/Open Notebook Plus.app`
- Build: `dist/Open-Notebook-Plus-mac-arm64.dmg`
- Copy: `/Users/Antman/Downloads/Open-Notebook-Plus-mac-arm64.dmg`

**Interfaces:**
- Consumes: committed app icon assets.
- Produces: installed and verified macOS application using the new icon.

- [ ] **Step 1: Build the macOS release**

Run:

```bash
make build-mac BUILD_PYTHON=/opt/homebrew/bin/python3.12
```

Expected: desktop tests, backend tests, frontend build, PyInstaller bundle, and DMG creation all succeed.

- [ ] **Step 2: Verify the bundle and DMG**

Run:

```bash
codesign --verify --deep --strict "dist/Open Notebook Plus.app"
hdiutil verify "dist/Open-Notebook-Plus-mac-arm64.dmg"
```

Expected: the app satisfies its designated requirement and the DMG checksum is valid.

- [ ] **Step 3: Install and launch the application**

Run:

```bash
make build-mac-install
open "/Applications/Open Notebook Plus.app"
```

Expected: the application reaches its `ready` progress event and remains open.

- [ ] **Step 4: Confirm the installed icon surfaces**

Inspect the installed app in Finder and the running icon in the Dock. Confirm the notebook is centered, unclipped, and visibly distinct from the previous blue icon. Account for normal macOS icon caching before treating a stale Finder thumbnail as a packaging failure.

- [ ] **Step 5: Publish the verified installer**

Copy the DMG and checksum to Downloads, verify identical SHA-256 values, commit any final generated-asset changes, and push `desktop-app` to `origin`.
