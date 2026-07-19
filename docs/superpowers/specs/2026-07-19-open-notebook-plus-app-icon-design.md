# Open Notebook Plus App Icon Design

Date: 2026-07-19
Status: Selected design awaiting final production asset approval

## Direction

Use the selected Premium Dimensional notebook concept as the new Open Notebook
Plus identity. The icon is an open white notebook on a deep ink-blue cloth
cover, with a coral bookmark, mint and gold tabs, and a subtle embossed network
of knowledge points. It should feel tactile, private, capable, and polished
without resembling a generic chat or sparkle icon.

The approved concept render is:

`/Users/Antman/.codex/generated_images/019ef365-d194-7d13-8e57-217ec2642247/exec-2a3f651a-05b8-4518-b5b8-05eadea4999b.png`

## Production Treatment

- Preserve the notebook, bookmark, tabs, cloth texture, page depth, and
  knowledge-network embossing from the selected render.
- Remove the rendered checkerboard completely and create a genuine transparent
  alpha channel outside the notebook silhouette.
- Center the notebook on a 1024 x 1024 canvas with enough breathing room for
  macOS masking and Windows taskbar rendering.
- Keep the open-book silhouette and coral bookmark recognizable at 16, 24, 32,
  and 48 pixels. Fine paper texture may simplify naturally at small sizes, but
  the silhouette and color accents must remain intact.
- Include no text, initials, watermark, extra objects, or decorative backdrop.

## Asset Pipeline

The transparent 1024 x 1024 PNG is the single source of truth. The repository's
icon generator will consume that master rather than redrawing the previous blue
icon. It will produce:

- `desktop/resources/icon.png`: 1024 x 1024 RGBA master.
- `desktop/resources/icon.icns`: macOS iconset containing 16 through 1024 pixel
  representations.
- `desktop/resources/icon.ico`: Windows multi-resolution icon containing 16,
  32, 48, 64, 128, and 256 pixel representations.
- `frontend/src/app/favicon.ico`: browser favicon derived from the same master.

The generated source image remains outside the repository as provenance. The
final normalized master and platform derivatives are committed with the app.

## Validation

- Confirm the master is exactly 1024 x 1024 RGBA and contains transparent
  pixels outside the notebook.
- Render contact sheets at 16, 32, 64, 128, 256, 512, and 1024 pixels to inspect
  silhouette, centering, edge quality, and color retention.
- Validate `icon.icns` with `iconutil` and inspect its representation list.
- Validate `icon.ico` and favicon frame sizes with Pillow.
- Build the macOS application and confirm Finder, Dock, launch splash, and DMG
  presentation use the new icon without clipping or stale caches.
- Preserve the existing application name and bundle identifiers.

## Scope

This change replaces visual icon assets and the deterministic asset-generation
path only. It does not change application behavior, branding text, interface
colors, startup logic, or installer identifiers.
