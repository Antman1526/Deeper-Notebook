import { expect, test } from '@playwright/test'

import { installLuminousFolioFixture } from './fixtures/luminous-folio'

type Server = {
  id: string
  name: string
  url: string
  enabled: boolean
  priority: number
}

test('MCP settings supports add, persistent toggle, isolated test failure, and keyboard/mobile layout', async ({ page }) => {
  const consoleErrors: string[] = []
  const mcpRequests: string[] = []
  const servers: Server[] = [
    {
      id: 'srv-alpha',
      name: 'Alpha',
      url: 'https://alpha.example.com/mcp',
      enabled: true,
      priority: 100,
    },
  ]

  page.on('console', message => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  page.on('request', request => {
    const pathname = new URL(request.url()).pathname
    if (pathname.startsWith('/api/mcp')) mcpRequests.push(`${request.method()} ${pathname}`)
  })

  await installLuminousFolioFixture(page, { theme: 'archive-paper' })
  await page.route('**/api/mcp/recommendations', async route => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ recommendations: [] }),
    })
  })
  await page.route('**/api/mcp/**', async route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname.endsWith('/recommendations')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ recommendations: [] }),
      })
      return
    }
    if (pathname.endsWith('/test')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ ok: false, error: 'fixture server is offline' }),
      })
      return
    }
    if (route.request().method() === 'PATCH') {
      const id = pathname.split('/').at(-1)
      const patch = route.request().postDataJSON() as { enabled?: boolean; priority?: number }
      const server = servers.find(item => item.id === id)
      if (!server) {
        await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
        return
      }
      Object.assign(server, patch)
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(server) })
      return
    }
    await route.fulfill({ contentType: 'application/json', body: '{}' })
  })
  await page.route('**/api/mcp', async route => {
    if (route.request().method() === 'GET') {
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(servers) })
      return
    }
    if (route.request().method() === 'POST') {
      const input = route.request().postDataJSON() as { name: string; url: string; enabled?: boolean }
      const created: Server = {
        id: 'srv-created',
        name: input.name,
        url: input.url,
        enabled: input.enabled ?? true,
        priority: 110,
      }
      servers.push(created)
      await route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(created) })
      return
    }
    await route.fulfill({ status: 405, contentType: 'application/json', body: '{}' })
  })

  await page.setViewportSize({ width: 320, height: 740 })
  await page.goto('/settings/mcp')

  await expect(page.getByRole('heading', { name: 'MCP Servers', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Disable Alpha' })).toBeVisible()

  // Keyboard path: the persistent switch is a native button and Enter invokes
  // the existing PATCH mutation with no unrelated request.
  const toggle = page.getByRole('button', { name: 'Disable Alpha' })
  await toggle.focus()
  await expect(toggle).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('button', { name: 'Enable Alpha' })).toBeVisible()

  // A failed Test request must not disable or remove the row controls.
  await page.getByRole('button', { name: 'Test' }).click()
  await expect(page.getByRole('button', { name: 'Delete' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Enable Alpha' })).toBeEnabled()

  // Add remains available after the isolated test failure.
  await page.getByLabel('Server name').fill('Beta')
  await page.getByLabel('https://example.com/mcp').fill('https://beta.example.com/mcp')
  await page.getByRole('button', { name: 'Add server' }).click()
  await expect(page.getByText('Beta', { exact: true })).toBeVisible()

  const rows = page.getByRole('listitem')
  await expect(rows).toHaveCount(2)
  for (const row of await rows.all()) {
    const box = await row.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(320)
  }

  expect(mcpRequests).toEqual([
    'GET /api/mcp',
    'GET /api/mcp/recommendations',
    'PATCH /api/mcp/srv-alpha',
    'GET /api/mcp',
    'POST /api/mcp/srv-alpha/test',
    'POST /api/mcp',
    'GET /api/mcp',
  ])
  expect(consoleErrors).toEqual([])
})
