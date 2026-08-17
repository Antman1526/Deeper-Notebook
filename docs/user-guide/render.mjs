import { chromium } from '@playwright/test'
const g = process.env.GUIDE_DIR
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
    '<div style="width:100%;font-family:Helvetica,Arial,sans-serif;font-size:7.5pt;color:#8aa09e;padding:0 16mm;display:flex;justify-content:space-between;">' +
    '<span>Deeper Notebook — User Guide · 0.8.95</span><span class="pageNumber"></span></div>',
  margin: { top: '18mm', bottom: '20mm', left: '16mm', right: '16mm' },
})
await browser.close()
console.log('ok')
