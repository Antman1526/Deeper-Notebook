const path = require('node:path')

const EXPECTED_FEATURES = Object.freeze({
  evidenceStudio: true,
  modelFleet: true,
  researchRuns: true,
  sourceVisuals: true,
  studyWorkbench: true,
  visualRefresh: true,
})

function parseArgs(argv) {
  const values = {}
  for (let index = 2; index < argv.length; index += 2) {
    const key = argv[index]
    const value = argv[index + 1]
    if (!key?.startsWith('--') || value === undefined) {
      throw new Error('arguments must use --key value pairs')
    }
    const name = key.slice(2)
    if (!['mode', 'frontend-url', 'api-url', 'playwright-module'].includes(name)) {
      throw new Error(`unknown argument: ${key}`)
    }
    if (values[name] !== undefined) throw new Error(`duplicate argument: ${key}`)
    values[name] = value
  }
  if (!['default', 'off'].includes(values.mode)) throw new Error('mode must be default or off')
  for (const key of ['frontend-url', 'api-url', 'playwright-module']) {
    if (!values[key]) throw new Error(`missing --${key}`)
  }
  return values
}

function parseLoopbackUrl(value, name) {
  let url
  try {
    url = new URL(value)
  } catch (error) {
    throw new Error(`${name} must be a valid HTTP(S) URL`)
  }
  if (!['http:', 'https:'].includes(url.protocol) || url.hostname !== '127.0.0.1') {
    throw new Error(`${name} must use the 127.0.0.1 loopback host`)
  }
  if (url.username || url.password || url.search || url.hash || !url.port) {
    throw new Error(`${name} must not contain credentials, query, or fragment`)
  }
  return url
}

function featureResults(actual, expected) {
  return Object.fromEntries(Object.entries(expected).map(([name, value]) => [name, {
    expected: value,
    actual: actual?.[name],
    passed: actual?.[name] === value,
  }]))
}

async function main() {
  const args = parseArgs(process.argv)
  const frontend = parseLoopbackUrl(args['frontend-url'], 'frontend-url')
  const api = parseLoopbackUrl(args['api-url'], 'api-url')
  if (frontend.hostname !== '127.0.0.1' || api.hostname !== '127.0.0.1') {
    throw new Error('only 127.0.0.1 loopback origins are allowed')
  }
  const allowedOrigins = new Set([frontend.origin, api.origin])
  const { chromium } = require(path.resolve(args['playwright-module']))
  const observed = []
  const responses = []
  const blocked = []
  let browser = null
  try {
    browser = await chromium.launch({ headless: true })
    const context = await browser.newContext({ locale: 'en-US', colorScheme: 'dark' })
    await context.addCookies([{
      name: 'wizard_completed',
      value: '1',
      url: frontend.origin,
    }])
    const page = await context.newPage()
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (url.protocol === 'http:' || url.protocol === 'https:') {
        observed.push({ method: request.method(), url: url.href, path: url.pathname })
      }
    })
    page.on('response', (response) => {
      const url = new URL(response.url())
      if (url.protocol === 'http:' || url.protocol === 'https:') {
        responses.push({ status: response.status(), url: url.href, path: url.pathname })
      }
    })
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url())
      if ((url.protocol === 'http:' || url.protocol === 'https:') && !allowedOrigins.has(url.origin)) {
        blocked.push(url.href)
        await route.abort()
        return
      }
      await route.fallback()
    })

    const route = args.mode === 'default' ? '/' : '/sources'
    await page.goto(new URL(route, frontend).href, { waitUntil: 'domcontentloaded', timeout: 120000 })
    await page.waitForTimeout(750)
    const features = await page.evaluate(async () => {
      const response = await fetch('/api/features')
      return { status: response.status, body: await response.json() }
    })
    const actualFeatures = features?.body?.features
    const expectedFeatures = {
      ...EXPECTED_FEATURES,
      ...(args.mode === 'off' ? { sourceVisuals: false } : {}),
    }
    const featureChecks = featureResults(actualFeatures, expectedFeatures)
    const visualMutationRequest = observed.some((entry) => (
      entry.path.includes('/visual') && entry.method !== 'GET'
    ))
    const nonGetRequests = observed.filter((entry) => entry.method !== 'GET')
    const result = {
      status: 'passed',
      mode: args.mode,
      frontend_url: frontend.href,
      api_url: api.href,
      feature_response: features,
      feature_checks: featureChecks,
      observed_requests: observed,
      observed_responses: responses,
      blocked_requests: blocked,
      http_methods: [...new Set(observed.map((entry) => entry.method))].sort(),
      non_get_requests: nonGetRequests,
      visual_mutation_request_observed: visualMutationRequest,
    }

    if (blocked.length) throw new Error(`blocked non-loopback request: ${blocked[0]}`)
    if (visualMutationRequest) throw new Error('browser emitted a visual mutation request')
    if (nonGetRequests.length) throw new Error(`browser emitted non-GET request: ${nonGetRequests[0].method} ${nonGetRequests[0].path}`)
    if (features.status !== 200 || !actualFeatures || Object.values(featureChecks).some((check) => !check.passed)) {
      throw new Error('browser feature authority did not match the expected mode')
    }

    if (args.mode === 'default') {
      await page.locator('[data-testid="visual-system-v2-shell"]').waitFor({ state: 'visible', timeout: 60000 })
      const theme = await page.locator('html').getAttribute('data-theme')
      result.theme = theme
      result.visual_system_v2_shell_visible = await page.locator('[data-testid="visual-system-v2-shell"]').isVisible()
      if (!String(theme).startsWith('gemini-forward-')) throw new Error(`expected Gemini Forward theme, received ${theme}`)
      if (!result.visual_system_v2_shell_visible) throw new Error('Gemini Forward workspace shell was not visible')
    } else {
      await page.getByRole('heading', { name: 'Sources', exact: true }).waitFor({ state: 'visible', timeout: 60000 })
      const mainVisible = await page.locator('main').first().isVisible()
      const sourceHeadingVisible = await page.getByRole('heading', { name: 'Sources', exact: true }).isVisible()
      const sourceListRequest = observed.some((entry) => entry.method === 'GET' && entry.path === '/api/sources')
      result.sources_main_visible = mainVisible
      result.sources_heading_visible = sourceHeadingVisible
      result.source_list_get_observed = sourceListRequest
      if (!mainVisible || !sourceHeadingVisible || !sourceListRequest) throw new Error('Sources route was not usable')
    }
    console.log(JSON.stringify(result))
  } finally {
    if (browser) await browser.close()
  }
}

main().catch((error) => {
  const payload = { status: 'failed', error: error instanceof Error ? error.message : String(error) }
  console.log(JSON.stringify(payload))
  process.exitCode = 1
})
