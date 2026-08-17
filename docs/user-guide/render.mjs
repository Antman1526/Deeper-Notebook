// Renders guide.html to Deeper-Notebook-User-Guide.pdf with Chromium's print path.
//
// ESM resolves bare specifiers from THIS file's location, not the working
// directory, so `@playwright/test` is imported through the frontend workspace
// explicitly. That makes the script runnable from anywhere:
//
//   node docs/user-guide/render.mjs
//
// GUIDE_DIR is optional and defaults to this directory.
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const playwright = resolve(here, '../../frontend/node_modules/@playwright/test/index.mjs')
const { chromium } = await import(playwright)

const g = process.env.GUIDE_DIR ?? here

const browser = await chromium.launch()
const page = await browser.newPage()
await page.goto(`file://${g}/guide.html`, { waitUntil: 'networkidle' })
await page.emulateMedia({ media: 'print' })
await page.pdf({
  path: `${g}/Deeper-Notebook-User-Guide.pdf`,
  format: 'A4',
  printBackground: true,
  displayHeaderFooter: true,
  headerTemplate: '<div></div>',
  footerTemplate:
    '<div style="width:100%;font-family:Helvetica,Arial,sans-serif;font-size:7.5pt;color:#8aa09e;padding:0 16mm;display:flex;justify-content:space-between;">'
    + '<span>Deeper Notebook — User Guide · 0.8.96</span><span class="pageNumber"></span></div>',
  margin: { top: '18mm', bottom: '20mm', left: '16mm', right: '16mm' },
})
await browser.close()
console.log(`wrote ${g}/Deeper-Notebook-User-Guide.pdf`)
