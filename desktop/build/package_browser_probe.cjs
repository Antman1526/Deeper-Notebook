const path = require('node:path')

const MAX_OBSERVED_REQUEST_ENTRIES = 64
const MAX_OBSERVED_RESPONSE_ENTRIES = 64
const MAX_BLOCKED_REQUEST_ENTRIES = 64
const MAX_RECEIPT_BYTES = 65536
const MAX_CAPTURED_STRING_BYTES = 4096

const EXPECTED_FEATURES = Object.freeze({
  evidenceStudio: true,
  modelFleet: true,
  researchRuns: true,
  sourceVisuals: true,
  studyWorkbench: true,
  visualRefresh: true,
})

function hasBoundedString(value) {
  return typeof value === 'string' && Buffer.byteLength(value, 'utf8') <= MAX_CAPTURED_STRING_BYTES
}

function requireBoundedString(value, name) {
  if (!hasBoundedString(value)) throw new Error(`${name} exceeded the receipt string limit`)
  return value
}

function emitReceipt(payload) {
  const serialized = JSON.stringify(payload)
  if (Buffer.byteLength(serialized, 'utf8') > MAX_RECEIPT_BYTES) {
    throw new Error('browser receipt exceeded its byte limit')
  }
  console.log(serialized)
}

function boundedErrorMessage(error) {
  let message = 'browser probe failed'
  try {
    message = error instanceof Error ? error.message : String(error)
  } catch (_) {
    return message
  }
  return hasBoundedString(message) ? message : 'browser probe omitted an oversized error'
}

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
    values[name] = requireBoundedString(value, name)
  }
  if (!['default', 'off'].includes(values.mode)) throw new Error('mode must be default or off')
  for (const key of ['frontend-url', 'api-url', 'playwright-module']) {
    if (!values[key]) throw new Error(`missing --${key}`)
  }
  return values
}

function parseLoopbackUrl(value, name) {
  requireBoundedString(value, name)
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

function hasExactExpectedFeatures(actual, expected) {
  if (!actual || typeof actual !== 'object' || Array.isArray(actual)) return false
  const expectedNames = Object.keys(expected)
  const actualNames = Object.keys(actual)
  return actualNames.length === expectedNames.length
    && actualNames.every((name) => Object.prototype.hasOwnProperty.call(expected, name))
    && expectedNames.every((name) => actual[name] === expected[name])
}

function hasExactFeatureResponse(response, expected) {
  if (!response || typeof response !== 'object' || Array.isArray(response)) return false
  if (Object.keys(response).length !== 2 || !Object.prototype.hasOwnProperty.call(response, 'status') || !Object.prototype.hasOwnProperty.call(response, 'body')) return false
  const body = response.body
  return response.status === 200
    && body
    && typeof body === 'object'
    && !Array.isArray(body)
    && Object.keys(body).length === 1
    && Object.prototype.hasOwnProperty.call(body, 'features')
    && hasExactExpectedFeatures(body.features, expected)
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
  const requestedDocumentUrl = new URL(
    args.mode === 'default' ? '/' : '/sources',
    frontend,
  ).href
  const retainsEvidence = (url) => (
    url.origin === api.origin
    || (url.origin === frontend.origin && url.href === requestedDocumentUrl)
  )
  const observed = []
  const responses = []
  const observedRequestKeys = new Set()
  const observedResponseKeys = new Set()
  const blocked = []
  let requestEvidenceOverflow = false
  let responseEvidenceOverflow = false
  let blockedEvidenceOverflow = false
  let requestEvidenceInvalid = false
  let responseEvidenceInvalid = false
  let blockedEvidenceInvalid = false
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
        const method = request.method()
        if (!hasBoundedString(method) || !hasBoundedString(url.href) || !hasBoundedString(url.pathname)) {
          requestEvidenceInvalid = true
          return
        }
        if (!retainsEvidence(url)) return
        const evidenceKey = `${method}\u0000${url.href}`
        if (observedRequestKeys.has(evidenceKey)) return
        if (observed.length >= MAX_OBSERVED_REQUEST_ENTRIES) {
          requestEvidenceOverflow = true
          return
        }
        observedRequestKeys.add(evidenceKey)
        observed.push({ method, url: url.href, path: url.pathname })
      }
    })
    page.on('response', (response) => {
      const url = new URL(response.url())
      if (url.protocol === 'http:' || url.protocol === 'https:') {
        const status = response.status()
        if (!Number.isInteger(status) || status < 200 || status > 299 || !hasBoundedString(url.href) || !hasBoundedString(url.pathname)) {
          responseEvidenceInvalid = true
          return
        }
        if (!allowedOrigins.has(url.origin)) {
          responseEvidenceInvalid = true
          return
        }
        if (!retainsEvidence(url)) return
        const evidenceKey = `${status}\u0000${url.href}`
        if (observedResponseKeys.has(evidenceKey)) return
        if (responses.length >= MAX_OBSERVED_RESPONSE_ENTRIES) {
          responseEvidenceOverflow = true
          return
        }
        observedResponseKeys.add(evidenceKey)
        responses.push({ status, url: url.href, path: url.pathname })
      }
    })
    await page.route('**/*', async (route) => {
      const request = route.request()
      const url = new URL(request.url())
      const isHttpRequest = url.protocol === 'http:' || url.protocol === 'https:'
      if (isHttpRequest && (!allowedOrigins.has(url.origin) || request.method() !== 'GET')) {
        if (blocked.length >= MAX_BLOCKED_REQUEST_ENTRIES) blockedEvidenceOverflow = true
        else if (hasBoundedString(url.href)) blocked.push(url.href)
        else blockedEvidenceInvalid = true
        await route.abort()
        return
      }
      await route.fallback()
    })

    const route = args.mode === 'default' ? '/' : '/sources'
    await page.goto(new URL(route, frontend).href, { waitUntil: 'domcontentloaded', timeout: 120000 })
    await page.waitForTimeout(750)
    const featureAuthorityUrl = new URL('/api/features', api.origin).href
    const features = await page.evaluate(async (featureAuthorityUrl) => {
      const response = await fetch(featureAuthorityUrl)
      return { status: response.status, body: await response.json() }
    }, featureAuthorityUrl)
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

    if (requestEvidenceOverflow || responseEvidenceOverflow || blockedEvidenceOverflow || requestEvidenceInvalid || responseEvidenceInvalid || blockedEvidenceInvalid) {
      throw new Error('browser evidence exceeded bounded receipt limits')
    }
    if (blocked.length) throw new Error(`blocked non-loopback request: ${blocked[0]}`)
    if (visualMutationRequest) throw new Error('browser emitted a visual mutation request')
    if (nonGetRequests.length) throw new Error(`browser emitted non-GET request: ${nonGetRequests[0].method} ${nonGetRequests[0].path}`)
    if (!hasExactFeatureResponse(features, expectedFeatures) || Object.values(featureChecks).some((check) => !check.passed)) {
      throw new Error('browser feature authority did not match the expected mode')
    }

    let modeProof
    if (args.mode === 'default') {
      await page.locator('[data-testid="visual-system-v2-shell"]').waitFor({ state: 'visible', timeout: 60000 })
      const theme = await page.locator('html').getAttribute('data-theme')
      const shellVisible = await page.locator('[data-testid="visual-system-v2-shell"]').isVisible()
      if (!hasBoundedString(theme) || !theme.startsWith('gemini-forward-')) throw new Error('expected a bounded Gemini Forward theme')
      if (!shellVisible) throw new Error('Gemini Forward workspace shell was not visible')
      modeProof = {
        theme,
        visual_system_v2_shell_visible: shellVisible,
      }
    } else {
      await page.getByRole('heading', { name: 'Sources', exact: true }).waitFor({ state: 'visible', timeout: 60000 })
      const mainVisible = await page.locator('main').first().isVisible()
      const sourceHeadingVisible = await page.getByRole('heading', { name: 'Sources', exact: true }).isVisible()
      const sourceListRequest = observed.some((entry) => entry.method === 'GET' && entry.path === '/api/sources')
      if (!mainVisible || !sourceHeadingVisible || !sourceListRequest) throw new Error('Sources route was not usable')
      modeProof = {
        sources_main_visible: mainVisible,
        sources_heading_visible: sourceHeadingVisible,
        source_list_get_observed: sourceListRequest,
      }
    }
    emitReceipt({
      status: 'passed',
      mode: args.mode,
      frontend_url: args['frontend-url'],
      api_url: args['api-url'],
      feature_response: features,
      feature_checks: featureChecks,
      observed_requests: observed,
      observed_responses: responses,
      blocked_requests: blocked,
      http_methods: [...new Set(observed.map((entry) => entry.method))].sort(),
      non_get_requests: nonGetRequests,
      visual_mutation_request_observed: visualMutationRequest,
      ...modeProof,
    })
  } finally {
    if (browser) await browser.close()
  }
}

main().catch((error) => {
  emitReceipt({ status: 'failed', error: boundedErrorMessage(error) })
  process.exitCode = 1
})
