import { mkdir } from 'node:fs/promises'
import { writeFile } from 'node:fs/promises'
import path from 'node:path'
import { createRequire } from 'node:module'
import { createServer } from 'node:http'

function requirePlaywright() {
  const candidates = [
    createRequire(import.meta.url),
    createRequire(path.join(process.cwd(), 'package.json')),
    createRequire(path.join(process.cwd(), 'frontend', 'package.json')),
  ]
  for (const candidate of candidates) {
    try {
      return candidate('playwright')
    } catch (error) {
      if (error?.code !== 'MODULE_NOT_FOUND') throw error
    }
  }
  throw new Error(
    'Playwright is not installed. Run `cd frontend && npm install --no-save playwright` before this smoke test.',
  )
}

const { chromium } = requirePlaywright()

const baseUrl = process.env.ONP_BASE_URL || 'http://127.0.0.1:3100'
const outputDir = path.resolve('output/playwright')
const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const fixtureApiPort = Number(process.env.ONP_FIXTURE_API_PORT || 5055)
const consoleIssues = []
const pageErrors = []
const missingApiRequests = []
const apiRequests = []
const apiFulfilled = []

const now = '2026-06-23T12:00:00.000Z'
const notebookId = 'notebook:alpha'

const notebook = {
  id: notebookId,
  name: 'BrainPulse competitive research',
  description: 'NotebookLM parity workbench with local-first model routing.',
  archived: false,
  created: now,
  updated: now,
  source_count: 2,
  note_count: 1,
}

const dynamicSources = [
  {
    id: 'source-retry-smoke',
    title: 'Browser smoke failed source',
    asset: { url: 'https://example.com/retry-source' },
    embedded: false,
    embedded_chunks: 0,
    insights_count: 0,
    created: now,
    updated: now,
    file_available: false,
    command_id: 'command:retry-smoke',
    status: 'failed',
    processing_info: { error: 'Fixture retry failure' },
  },
  {
    id: 'source-local-models',
    title: 'Local model fleet manifest',
    asset: { file_path: '/Users/Antman/Desktop/AI_Models/manifests/model_inventory.md' },
    embedded: true,
    embedded_chunks: 48,
    insights_count: 7,
    created: now,
    updated: now,
    file_available: true,
    status: 'completed',
  },
  {
    id: 'source-roadmap',
    title: 'NotebookLM competitive roadmap',
    asset: { file_path: '/Users/Antman/BrainPulseKnowledge/open-notebook-plus-imports/2026-06-23-open-notebook-plus-competitive-enhancement-plan-source-pack.md' },
    embedded: true,
    embedded_chunks: 31,
    insights_count: 5,
    created: now,
    updated: now,
    file_available: true,
    status: 'completed',
  },
]
const sourceCreateBodies = []
const retryRequests = []
const artifactCreateBodies = []
const artifactGenerateRequests = []
const workflowRunRequests = []
let createdSourceCounter = 0
let createdArtifactCounter = 0
let createdWorkflowRunCounter = 0

const notes = [
  {
    id: 'note-north-star',
    title: 'North Star',
    content: 'A local-first research studio with citation-backed artifacts and intelligent local model routing.',
    note_type: 'ai',
    created: now,
    updated: now,
  },
]

const artifact = {
  id: 'artifact-briefing',
  notebook_id: notebookId,
  artifact_type: 'briefing',
  title: 'Local-first research briefing',
  status: 'completed',
  source_ids: ['source-local-models', 'source-roadmap'],
  prompt: 'Create a concise, citation-backed briefing for the next implementation slice.',
  model_id: 'mlx-community/Qwen2.5-7B-Instruct-4bit',
  provider: 'local-mlx',
  output_format: 'markdown',
  output_payload: {
    content: [
      '# Local-first research briefing',
      '',
      'Open Notebook Plus can compete by combining grounded source work with private local model routing.',
      '',
      '- Keep citations visible from summary to export.',
      '- Route quick synthesis to MLX and endpoint checks to Ollama/OpenAI-compatible sidecars.',
      '- Make Evidence Studio the repeatable artifact surface for briefings, FAQs, study guides, and timelines.',
    ].join('\n'),
  },
  citations: [
    {
      source_id: 'source-local-models',
      title: 'Local model fleet manifest',
      preview: 'The local fleet includes MLX, GGUF, Transformers, and experimental model assets.',
      quote: 'MLX, GGUF, Transformers, and experimental model assets.',
      locator: '/Users/Antman/Desktop/AI_Models/manifests/model_inventory.md',
    },
    {
      source_id: 'source-roadmap',
      title: 'NotebookLM competitive roadmap',
      preview: 'Evidence Studio should save citation-backed artifacts that can be exported and revisited.',
      quote: 'Save citation-backed artifacts that can be exported and revisited.',
      locator: 'BrainPulseKnowledge source pack',
    },
  ],
  export_paths: {
    markdown: '/Users/Antman/BrainPulseKnowledge/open-notebook-plus-imports/local-first-research-briefing.md',
    json: '/Users/Antman/BrainPulseKnowledge/codex-project-scans/local-first-research-briefing.json',
  },
  revision_of_id: null,
  created: now,
  updated: now,
}
const dynamicArtifacts = [artifact]
const dynamicWorkflowRuns = []

function workflowRunFromCreateBody(artifactId, body) {
  createdWorkflowRunCounter += 1
  let payload = {}
  try {
    payload = JSON.parse(body || '{}')
  } catch {
    payload = {}
  }
  const artifactRecord = dynamicArtifacts.find(row => row.id === artifactId)
  return {
    id: `workflow-browser-smoke-${createdWorkflowRunCounter}`,
    artifact_id: artifactId,
    notebook_id: artifactRecord?.notebook_id || notebookId,
    title: payload.title || `Generate ${artifactRecord?.title || 'Artifact'}`,
    status: payload.approval_required === false ? 'queued' : 'awaiting_approval',
    source_ids: Array.isArray(payload.source_ids) ? payload.source_ids : [],
    approval_required: payload.approval_required !== false,
    steps: [
      { id: 'context', label: 'Context built', status: 'completed' },
      {
        id: 'privacy_gate',
        label: 'Privacy gate',
        status: payload.approval_required === false ? 'completed' : 'pending',
      },
    ],
    command_id: null,
    created: now,
    updated: now,
  }
}

const inventoryModels = [
  {
    name: 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
    path: '/Users/Antman/Desktop/AI_Models/GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
    launcher_model_ref: '/Users/Antman/Desktop/AI_Models/GGUF/Qwen2.5-7B-Instruct-Q4_K_M.gguf',
    runtime: 'gguf',
    runnable: true,
    activation_supported: true,
    runtime_status: 'ready',
    runtime_note: 'Runnable through the local llama.cpp-compatible sidecar.',
    setup_href: null,
    setup_label: null,
    architecture: 'qwen2',
    context_length: 32768,
    quant: 'Q4_K_M',
    parameter_count_b: 7,
    file_size_bytes: 4_700_000_000,
  },
  {
    name: 'North-Mini-Code-1.0-6bit',
    path: '/Users/Antman/Desktop/AI_Models/MLX/North-Mini-Code-1.0-6bit',
    launcher_model_ref: 'mlx-community/North-Mini-Code-1.0-6bit',
    runtime: 'mlx',
    runnable: true,
    activation_supported: false,
    runtime_status: 'ready',
    runtime_note: 'Runnable through MLX on Apple Silicon.',
    setup_href: null,
    setup_label: null,
    architecture: 'llama',
    context_length: 65536,
    quant: '6bit',
    parameter_count_b: 8,
    file_size_bytes: 6_900_000_000,
  },
  {
    name: 'FableVibes-GGUF',
    path: '/Users/Antman/Desktop/AI_Models/Transformers/FableVibes-GGUF',
    launcher_model_ref: null,
    runtime: 'transformers',
    runnable: false,
    activation_supported: false,
    runtime_status: 'inventory_only',
    runtime_note: 'Transformers assets are indexed, but need a runnable provider before chat activation.',
    setup_href: '/settings/launcher-prefs',
    setup_label: 'Open launcher preferences',
    architecture: 'mistral',
    context_length: 8192,
    quant: null,
    parameter_count_b: 7,
    file_size_bytes: 13_100_000_000,
  },
]

function jsonResponse(body, status = 200) {
  return {
    status,
    headers: {
      'content-type': 'application/json',
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
      'access-control-allow-headers': 'authorization,content-type,x-skip-error-toast',
    },
    body: JSON.stringify(body),
  }
}

function readRequestBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = []
    req.on('data', chunk => chunks.push(chunk))
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')))
    req.on('error', reject)
  })
}

function multipartField(body, name) {
  const pattern = new RegExp(`name="${name}"\\r\\n\\r\\n([\\s\\S]*?)\\r\\n--`)
  return pattern.exec(body)?.[1]?.trim() || null
}

function multipartFilename(body, name) {
  const pattern = new RegExp(`name="${name}"; filename="([^"]+)"`)
  return pattern.exec(body)?.[1] || null
}

function sourceFromCreateBody(body) {
  createdSourceCounter += 1
  const type = multipartField(body, 'type') || 'link'
  const title = multipartField(body, 'title')
  const urlField = multipartField(body, 'url')
  const filename = multipartFilename(body, 'file')
  const id = `source-browser-smoke-${createdSourceCounter}`

  if (type === 'text') {
    return {
      id,
      title: title || 'Browser smoke text source',
      asset: null,
      full_text: multipartField(body, 'content') || '',
      embedded: false,
      embedded_chunks: 0,
      insights_count: 0,
      created: now,
      updated: now,
      file_available: false,
      command_id: `command:browser-smoke-${createdSourceCounter}`,
      status: 'new',
      processing_info: { async: true, queued: true },
    }
  }

  if (type === 'upload') {
    return {
      id,
      title: title || filename || 'Browser smoke uploaded file',
      asset: { file_path: `/tmp/${filename || 'browser-smoke-upload.md'}` },
      full_text: null,
      embedded: false,
      embedded_chunks: 0,
      insights_count: 0,
      created: now,
      updated: now,
      file_available: true,
      command_id: `command:browser-smoke-${createdSourceCounter}`,
      status: 'new',
      processing_info: { async: true, queued: true },
    }
  }

  return {
    id,
    title: title || 'Browser smoke queued source',
    asset: { url: urlField || 'https://example.com/browser-smoke-source' },
    full_text: null,
    embedded: false,
    embedded_chunks: 0,
    insights_count: 0,
    created: now,
    updated: now,
    file_available: false,
    command_id: `command:browser-smoke-${createdSourceCounter}`,
    status: 'new',
    processing_info: { async: true, queued: true },
  }
}

function artifactFromCreateBody(body) {
  createdArtifactCounter += 1
  let payload = {}
  try {
    payload = JSON.parse(body || '{}')
  } catch {
    payload = {}
  }
  return {
    id: `artifact-browser-smoke-${createdArtifactCounter}`,
    notebook_id: payload.notebook_id || notebookId,
    artifact_type: payload.artifact_type || 'report',
    title: payload.title || 'Browser smoke artifact',
    status: 'pending',
    source_ids: Array.isArray(payload.source_ids) ? payload.source_ids : [],
    prompt: payload.prompt || null,
    model_id: null,
    provider: null,
    output_format: null,
    output_payload: {},
    citations: [],
    export_paths: {},
    revision_of_id: null,
    created: now,
    updated: now,
  }
}

function generatedArtifact(artifactRecord) {
  const sourceIds = artifactRecord.source_ids.length > 0
    ? artifactRecord.source_ids
    : ['source-local-models', 'source-roadmap']
  const citations = sourceIds.map((sourceId, index) => {
    const source = dynamicSources.find(row => row.id === sourceId)
    return {
      source_id: sourceId,
      title: source?.title || sourceId,
      marker: `[S${index + 1}]`,
      preview: index === 0
        ? 'Generated report cites the local model fleet manifest.'
        : 'Generated report cites the competitive roadmap source pack.',
      quote: index === 0
        ? 'local model fleet manifest'
        : 'competitive roadmap source pack',
      locator: source?.asset?.file_path || source?.asset?.url || sourceId,
    }
  })
  const content = artifactRecord.artifact_type === 'course_pack'
    ? [
        '# Course Pack',
        '',
        '## Audience',
        'Workspace admins learning local-first source-grounded workflows. [S1]',
        '',
        '## Module 1: Local Model Orientation',
        'Duration: 20 minutes',
        'Browser smoke generated this artifact from selected ready sources. [S1]',
        '',
        '### Hands-on exercise',
        'Compare the local model fleet manifest with the competitive roadmap. [S1] [S2]',
        '',
        '### Knowledge check',
        'Which source proves local model routing is available? [S1]',
        '',
        '### Facilitator notes',
        'Use the local model settings page as the live demo surface.',
        '',
        '## Module 2: Source-Grounded Export',
        'Duration: 15 minutes',
        'Learners inspect citations and export Markdown plus JSON sidecars. [S2]',
      ].join('\n')
    : [
        `# ${artifactRecord.title}`,
        '',
        'Browser smoke generated this artifact from selected ready sources. [S1]',
        '',
        '- The report stayed grounded in the local model fleet manifest. [S1]',
        '- The report preserved roadmap context for NotebookLM competition. [S2]',
      ].join('\n')
  const exportStem = `/Users/Antman/BrainPulseKnowledge/open-notebook-plus-imports/evidence-studio/${artifactRecord.id}`
  const exportPaths = {
    markdown: `${exportStem}.md`,
    json: `${exportStem}.json`,
  }
  if (artifactRecord.artifact_type === 'course_pack') {
    exportPaths.instructor_guide = `${exportStem}-instructor-guide.md`
    exportPaths.learner_handout = `${exportStem}-learner-handout.md`
    exportPaths.module_checklist = `${exportStem}-module-checklist.json`
    exportPaths.assessment = `${exportStem}-assessment.md`
    exportPaths.scorm_package = `${exportStem}-scorm.zip`
    exportPaths.xapi_package = `${exportStem}-xapi.zip`
  }

  return {
    ...artifactRecord,
    status: 'completed',
    model_id: 'mlx-community/North-Mini-Code-1.0-6bit',
    provider: 'local-mlx',
    output_format: 'markdown',
    output_payload: {
      content,
    },
    citations,
    export_paths: exportPaths,
    updated: now,
  }
}

async function startFixtureApiServer() {
  const server = createServer(async (req, res) => {
    const method = req.method || 'GET'
    const url = new URL(req.url || '/', `http://127.0.0.1:${fixtureApiPort}`)
    apiRequests.push(`${method} ${url.pathname}`)

    const headers = {
      'content-type': 'application/json',
      'access-control-allow-origin': '*',
      'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
      'access-control-allow-headers': 'authorization,content-type,x-skip-error-toast',
    }
    for (const [key, value] of Object.entries(headers)) {
      res.setHeader(key, value)
    }

    if (method === 'OPTIONS') {
      apiFulfilled.push(`${method} ${url.pathname}`)
      res.writeHead(200)
      res.end('{}')
      return
    }

    const body = ['POST', 'PUT', 'PATCH'].includes(method)
      ? await readRequestBody(req)
      : ''
    const fixture = apiFixture(url.toString(), method, body)
    if (fixture === null) {
      missingApiRequests.push(`${method} ${url.pathname}`)
      res.writeHead(200)
      res.end('{}')
      return
    }

    apiFulfilled.push(`${method} ${url.pathname}`)
    if (fixture && typeof fixture === 'object' && '__fixtureStatus' in fixture) {
      res.writeHead(fixture.__fixtureStatus)
      res.end(JSON.stringify(fixture.body ?? {}))
      return
    }
    res.writeHead(200)
    res.end(JSON.stringify(fixture))
  })

  await new Promise((resolve, reject) => {
    server.once('error', reject)
    server.listen(fixtureApiPort, '127.0.0.1', resolve)
  })
  return server
}

function apiFixture(url, method, body = '') {
  const { pathname, searchParams } = new URL(url)
  const decodedPathname = decodeURIComponent(pathname)
  if (method === 'OPTIONS') return {}
  if (pathname === '/config') return { apiUrl: '' }
  if (pathname === '/api/config') {
    return {
      version: '0.8.69-smoke',
      latestVersion: null,
      hasUpdate: false,
      dbStatus: 'ok',
    }
  }
  if (pathname === '/api/auth/status') return { auth_enabled: false }
  if (pathname === '/api/notebooks') return [notebook]
  if (decodedPathname === `/api/notebooks/${notebookId}`) {
    return notebook
  }
  if (decodedPathname === '/api/sources/source-retry-smoke/status') {
    const source = dynamicSources.find(row => row.id === 'source-retry-smoke')
    return {
      status: source?.status || 'unknown',
      message: source?.status === 'queued'
        ? 'Source processing queued'
        : 'Source processing failed',
      command_id: source?.command_id || 'command:retry-smoke',
      processing_info: source?.processing_info || null,
    }
  }
  if (/^\/api\/sources\/source-browser-smoke-\d+\/status$/.test(decodedPathname)) {
    const sourceId = decodedPathname.split('/')[3]
    const source = dynamicSources.find(row => row.id === sourceId)
    return {
      status: source?.status || 'new',
      message: source?.status === 'failed'
        ? 'Source processing failed'
        : 'Source processing queued',
      command_id: source?.command_id || null,
      processing_info: source?.processing_info || { async: true, queued: true },
    }
  }
  if (decodedPathname === '/api/sources/source-retry-smoke/retry' && method === 'POST') {
    retryRequests.push(`${method} ${decodedPathname}`)
    const source = dynamicSources.find(row => row.id === 'source-retry-smoke')
    if (source) {
      source.status = 'queued'
      source.command_id = 'command:retry-smoke-requeued'
      source.processing_info = { async: true, queued: true }
      source.updated = now
    }
    return {
      ...(source || {}),
      status: 'queued',
      command_id: 'command:retry-smoke-requeued',
      processing_info: { async: true, queued: true },
    }
  }
  if (pathname === '/api/sources') {
    if (method === 'POST') {
      sourceCreateBodies.push(body)
      if ((multipartField(body, 'url') || '').includes('browser-smoke-partial-fail')) {
        return {
          __fixtureStatus: 502,
          body: { detail: 'Fixture partial batch failure' },
        }
      }
      if (multipartFilename(body, 'file') === 'source-upload-too-large.md') {
        return {
          __fixtureStatus: 413,
          body: { detail: 'Upload exceeds size limit (3 bytes); aborted after writing 0 bytes' },
        }
      }
      const createdSource = sourceFromCreateBody(body)
      if (!dynamicSources.some(source => source.id === createdSource.id)) {
        dynamicSources.unshift(createdSource)
      }
      return createdSource
    }
    return searchParams.get('notebook_id') === notebookId || searchParams.has('notebook_id')
      ? dynamicSources
      : dynamicSources
  }
  if (pathname === '/api/notes') return notes
  if (decodedPathname === `/api/studio/notebooks/${notebookId}/artifacts`) return dynamicArtifacts
  const workflowRunsMatch = decodedPathname.match(/^\/api\/studio\/artifacts\/(.+)\/workflow-runs$/)
  if (workflowRunsMatch && method === 'GET') {
    const artifactId = workflowRunsMatch[1]
    return dynamicWorkflowRuns.filter(run => run.artifact_id === artifactId)
  }
  if (workflowRunsMatch && method === 'POST') {
    const artifactId = workflowRunsMatch[1]
    workflowRunRequests.push(`${method} ${decodedPathname}`)
    const run = workflowRunFromCreateBody(artifactId, body)
    dynamicWorkflowRuns.unshift(run)
    return run
  }
  const workflowApproveMatch = decodedPathname.match(/^\/api\/studio\/workflow-runs\/(.+)\/approve$/)
  if (workflowApproveMatch && method === 'POST') {
    const runId = workflowApproveMatch[1]
    workflowRunRequests.push(`${method} ${decodedPathname}`)
    const index = dynamicWorkflowRuns.findIndex(run => run.id === runId)
    if (index === -1) {
      return {
        __fixtureStatus: 404,
        body: { detail: 'Studio workflow run not found' },
      }
    }
    dynamicWorkflowRuns[index] = {
      ...dynamicWorkflowRuns[index],
      status: 'queued',
      approval_required: false,
      steps: dynamicWorkflowRuns[index].steps.map(step => (
        step.id === 'privacy_gate' ? { ...step, status: 'completed' } : step
      )),
      updated: now,
    }
    return dynamicWorkflowRuns[index]
  }
  if (pathname === '/api/studio/artifacts' && method === 'POST') {
    artifactCreateBodies.push(body)
    const createdArtifact = artifactFromCreateBody(body)
    dynamicArtifacts.unshift(createdArtifact)
    return createdArtifact
  }
  const artifactGenerateMatch = decodedPathname.match(/^\/api\/studio\/artifacts\/([^/]+)\/generate$/)
  if (artifactGenerateMatch && method === 'POST') {
    const artifactId = artifactGenerateMatch[1]
    artifactGenerateRequests.push(`${method} ${decodedPathname}`)
    const index = dynamicArtifacts.findIndex(row => row.id === artifactId)
    if (index === -1) {
      return {
        __fixtureStatus: 404,
        body: { detail: 'Studio artifact not found' },
      }
    }
    dynamicArtifacts[index] = generatedArtifact(dynamicArtifacts[index])
    return dynamicArtifacts[index]
  }
  const revisionsMatch = decodedPathname.match(/^\/api\/studio\/artifacts\/([^/]+)\/revisions$/)
  if (revisionsMatch) {
    const artifactId = revisionsMatch[1]
    if (artifactId === artifact.id) {
      return [{ ...artifact, id: 'artifact-briefing-rev-1', title: 'Local-first research briefing revision', revision_of_id: artifact.id }]
    }
    return []
  }
  if (pathname === '/api/local-models/inventory') {
    return {
      model_dir: '/Users/Antman/Desktop/AI_Models',
      available: true,
      launcher_config: {
        available: true,
        path: '/Users/Antman/.open-notebook-plus/config.toml',
        provider: 'local',
        default_model: 'mlx-community/North-Mini-Code-1.0-6bit',
        model_dir: '/Users/Antman/Desktop/AI_Models',
        model_dir_matches_inventory: true,
      },
      models: inventoryModels,
    }
  }
  if (pathname === '/api/local-models/health') {
    return {
      overall: 'healthy',
      models: [
        {
          name: 'OpenAI-compatible sidecar',
          status: 'healthy',
          detail: '3 local models exposed through /v1/models',
          latency_ms: 12,
          runtime: 'openai-compatible',
          endpoint: 'http://127.0.0.1:8080',
          probe_path: '/v1/models',
        },
        {
          name: 'Ollama',
          status: 'healthy',
          detail: 'qwen2.5:7b, nomic-embed-text available',
          latency_ms: 18,
          runtime: 'ollama',
          endpoint: 'http://127.0.0.1:11434',
          probe_path: '/api/tags',
        },
      ],
    }
  }
  if (pathname === '/api/local-models/role-routing') {
    return {
      model_dir: '/Users/Antman/Desktop/AI_Models',
      available: true,
      routes: [
        {
          role: 'source_synthesis',
          label: 'Source synthesis',
          confidence: 0.91,
          reason: 'Long context and MLX runtime make this the best local synthesis choice.',
          model: inventoryModels[1],
        },
        {
          role: 'coding_research',
          label: 'Coding research',
          confidence: 0.86,
          reason: 'Code-tuned local asset with fast Apple Silicon startup.',
          model: inventoryModels[1],
        },
      ],
    }
  }
  if (pathname === '/api/local-models/benchmarks') {
    return {
      benchmarks: [
        {
          job_id: 'benchmark-smoke',
          roles: ['chat', 'source_synthesis'],
          status: 'completed',
          results: [
            {
              role: 'source_synthesis',
              label: 'Source synthesis',
              status: 'completed',
              model_name: 'North-Mini-Code-1.0-6bit',
              model_runtime: 'mlx',
              model_id: 'mlx-community/North-Mini-Code-1.0-6bit',
              provider: 'local-mlx',
              latency_ms: 530,
              tokens_per_second: 42,
              score: 0.91,
              error: null,
            },
          ],
          error: null,
          created_at: 1782230400,
          completed_at: 1782230401,
        },
      ],
    }
  }
  if (pathname === '/api/local-models/recommendations') {
    return {
      recommendations: [
        {
          id: 'qwen25-7b',
          label: 'Qwen2.5 7B Instruct',
          description: 'Balanced local research model for first installs.',
          repo_id: 'bartowski/Qwen2.5-7B-Instruct-GGUF',
          filename: 'Qwen2.5-7B-Instruct-Q4_K_M.gguf',
          approx_size_gb: 4.7,
          tags: ['recommended', 'gguf'],
          context_length: 32768,
        },
      ],
    }
  }
  if (pathname === '/api/local-models/downloads') return { downloads: [] }
  if (pathname === '/api/local-models/snapshot-installs') return { installs: [] }
  if (pathname === '/api/settings/launcher-prefs') return {}
  if (pathname === '/api/settings') return {}
  if (pathname === '/api/system/db-repair-needed') return { repair_needed: false }
  if (pathname === '/api/system/network-status') return { online: true, offline_mode: false }
  if (pathname === '/api/healthz/deep') {
    return {
      status: 'healthy',
      checks: {
        api: { status: 'healthy' },
        database: { status: 'healthy' },
        storage: { status: 'healthy' },
      },
    }
  }
  if (pathname === '/api/health') return { status: 'ok' }
  if (pathname === '/api/onp/gmail/status') return { connected: false, configured: false }
  if (pathname === '/api/credentials/status') {
    return {
      configured: {},
      source: {},
      encryption_configured: true,
    }
  }
  if (pathname === '/api/credentials/env-status') return {}
  if (pathname === '/api/transformations') return []
  if (pathname === '/api/episode-profiles') return []
  if (pathname === '/api/models') return []
  if (pathname === '/api/models/defaults') return {}
  if (pathname === '/api/mcp') return []
  if (pathname === '/api/mcp/web-search') return { enabled: false }
  if (pathname === '/api/chat/sessions') return []
  if (pathname === '/api/chat/context') return { messages: [] }
  return null
}

async function installRoutes(page, missingApiRequests) {
  await page.route('**/*', async route => {
    const request = route.request()
    const url = request.url()
    const parsed = new URL(url)
    if (request.method() === 'OPTIONS') {
      await route.fulfill(jsonResponse({}))
      return
    }
    if (parsed.pathname === '/config' || parsed.pathname.startsWith('/api/')) {
      apiRequests.push(`${request.method()} ${parsed.pathname}`)
      const fixture = apiFixture(url, request.method())
      if (fixture === null) {
        missingApiRequests.push(`${request.method()} ${parsed.pathname}`)
        await route.fulfill(jsonResponse({}))
        return
      }
      await route.fulfill(jsonResponse(fixture))
      apiFulfilled.push(`${request.method()} ${parsed.pathname}`)
      return
    }
    await route.continue()
  })
}

async function assertNoHorizontalOverflow(page, label) {
  const overflow = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body.scrollWidth,
  }))
  if (overflow.scrollWidth > overflow.width + 2 || overflow.bodyScrollWidth > overflow.width + 2) {
    throw new Error(`${label} has horizontal overflow: ${JSON.stringify(overflow)}`)
  }
}

async function waitForReady(page, text) {
  try {
    await page.getByText(text, { exact: false }).first().waitFor({ timeout: 20_000 })
  } catch (error) {
    const safeName = text.replace(/[^A-Za-z0-9]+/g, '-').replace(/^-+|-+$/g, '').toLowerCase()
    const screenshotPath = path.join(outputDir, `failure-waiting-for-${safeName || 'text'}.png`)
    await page.screenshot({ path: screenshotPath, fullPage: true })
    const visibleText = await page.locator('body').innerText({ timeout: 2_000 }).catch(() => '')
    const html = await page.content().catch(() => '')
    const htmlPath = path.join(outputDir, `failure-waiting-for-${safeName || 'text'}.html`)
    await writeFile(htmlPath, html)
    const readyState = await page.evaluate(() => document.readyState).catch(() => 'unknown')
    throw new Error([
      `Timed out waiting for "${text}"`,
      `URL: ${page.url()}`,
      `Screenshot: ${screenshotPath}`,
      `HTML: ${htmlPath}`,
      `Ready state: ${readyState}`,
      `HTML length: ${html.length}`,
      `Visible text: ${visibleText.slice(0, 2000)}`,
      `Console issues: ${consoleIssues.slice(-12).join('\n') || '(none)'}`,
      `Page errors: ${pageErrors.slice(-12).join('\n') || '(none)'}`,
      `Missing API requests: ${[...new Set(missingApiRequests)].join(', ') || '(none)'}`,
      `API requests: ${apiRequests.slice(-40).join('\n') || '(none)'}`,
      `API fulfilled: ${apiFulfilled.slice(-40).join('\n') || '(none)'}`,
      error instanceof Error ? error.message : String(error),
    ].join('\n'))
  }
}

async function waitForCondition(label, predicate, timeoutMs = 5000) {
  const startedAt = Date.now()
  while (Date.now() - startedAt < timeoutMs) {
    if (predicate()) return
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  throw new Error(`Timed out waiting for ${label}`)
}

async function main() {
  await mkdir(outputDir, { recursive: true })
  const uploadFixturePath = path.join(outputDir, 'source-upload-smoke.md')
  const tooLargeUploadFixturePath = path.join(outputDir, 'source-upload-too-large.md')
  await writeFile(
    uploadFixturePath,
    '# Browser smoke upload\n\nThis local markdown file verifies the upload source ingestion path.\n'
  )
  await writeFile(
    tooLargeUploadFixturePath,
    '# Browser smoke oversized upload\n\nThe fixture API rejects this filename with HTTP 413.\n'
  )
  const fixtureServer = await startFixtureApiServer()
  const browser = await chromium.launch({
    headless: true,
    executablePath: chromePath,
  })

  async function newPage(viewport) {
    const context = await browser.newContext({
      baseURL: baseUrl,
      viewport,
      deviceScaleFactor: 1,
    })
    await context.addCookies([
      {
        name: 'wizard_completed',
        value: '1',
        domain: new URL(baseUrl).hostname,
        path: '/',
        httpOnly: false,
        secure: false,
        sameSite: 'Lax',
      },
    ])
    const page = await context.newPage()
    page.on('console', message => {
      if (['error', 'warning'].includes(message.type())) {
        const text = message.text()
        if (!text.includes('[Config]')) consoleIssues.push(`${message.type()}: ${text}`)
      }
    })
    page.on('pageerror', error => pageErrors.push(error.message))
    await page.route('**/config', async route => {
      if (new URL(route.request().url()).pathname === '/config') {
        await route.fulfill(jsonResponse({ apiUrl: '' }))
        return
      }
      await route.continue()
    })
    return { context, page }
  }

  try {
    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto('/settings/local-models', { waitUntil: 'networkidle' })
      const inventoryProbe = await page.evaluate(async () => {
        const response = await fetch('/api/local-models/inventory')
        return { ok: response.ok, status: response.status, text: await response.text() }
      })
      if (!inventoryProbe.ok || !inventoryProbe.text.includes('Qwen2.5-7B')) {
        throw new Error(`Inventory probe failed: ${JSON.stringify(inventoryProbe).slice(0, 2000)}`)
      }
      await waitForReady(page, 'Connection checks')
      await waitForReady(page, 'Ollama')
      await waitForReady(page, '/api/tags')
      await waitForReady(page, 'Model fleet')
      await assertNoHorizontalOverflow(page, 'Local Models desktop')
      await page.screenshot({ path: path.join(outputDir, 'local-models-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 390, height: 844 })
      await page.goto('/settings/local-models', { waitUntil: 'networkidle' })
      await waitForReady(page, 'Connection checks')
      await waitForReady(page, 'Ollama')
      await assertNoHorizontalOverflow(page, 'Local Models mobile')
      await page.screenshot({ path: path.join(outputDir, 'local-models-mobile.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto(`/notebooks/${encodeURIComponent(notebookId)}`, { waitUntil: 'networkidle' })
      await waitForReady(page, 'Evidence Studio')
      await waitForReady(page, 'Local-first research briefing')
      await waitForReady(page, '2 citations')
      await page.getByRole('button', { name: /Open Local-first research briefing/i }).click()
      await waitForReady(page, 'Saved exports')
      await waitForReady(page, 'local-mlx')
      await page.waitForTimeout(400)
      await assertNoHorizontalOverflow(page, 'Evidence Studio desktop')
      await page.screenshot({ path: path.join(outputDir, 'evidence-studio-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto(`/notebooks/${encodeURIComponent(notebookId)}`, { waitUntil: 'networkidle' })
      await waitForReady(page, 'Evidence Studio')
      await page.getByRole('button', { name: /Artifact sources: All sources/i }).click()
      await page.getByLabel('Local model fleet manifest').check()
      await page.getByLabel('NotebookLM competitive roadmap').check()
      await page.keyboard.press('Escape')
      await waitForReady(page, '2 sources selected')
      await page.getByRole('button', { name: /^Course Pack$/i }).click()
      await waitForCondition(
        'artifact create endpoint call',
        () => artifactCreateBodies.some(body => body.includes('"artifact_type":"course_pack"'))
      )
      await waitForCondition(
        'workflow run create endpoint call',
        () => workflowRunRequests.some(request => request.includes('/workflow-runs'))
      )
      await waitForReady(page, 'Course Pack')
      await waitForReady(page, 'Workflow runs')
      await page.getByRole('button', { name: /Approve Generate Course Pack/i }).click()
      await waitForCondition(
        'artifact generate endpoint call',
        () => artifactGenerateRequests.some(request => request.includes('/generate'))
      )
      await page.getByRole('button', { name: /Open Course Pack/i }).click()
      await waitForReady(page, 'Course Pack workspace')
      await waitForReady(page, 'Module checklist')
      await waitForReady(page, 'Local Model Orientation')
      await waitForReady(page, 'Browser smoke generated this artifact')
      await waitForReady(page, 'Saved exports')
      await waitForReady(page, 'local-mlx')
      await page.getByRole('button', { name: /Inspect evidence for Local model fleet manifest/i }).click()
      await waitForReady(page, 'Citation evidence')
      await waitForReady(page, 'Generated report cites the local model fleet manifest.')
      await waitForReady(page, 'Open source record')
      await assertNoHorizontalOverflow(page, 'Evidence Studio artifact generation and citation drawer desktop')
      await page.screenshot({ path: path.join(outputDir, 'evidence-studio-generate-citation-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 390, height: 844 })
      await page.goto(`/notebooks/${encodeURIComponent(notebookId)}`, { waitUntil: 'networkidle' })
      await waitForReady(page, 'Evidence Studio')
      await waitForReady(page, 'Local-first research briefing')
      await assertNoHorizontalOverflow(page, 'Evidence Studio mobile')
      await page.screenshot({ path: path.join(outputDir, 'evidence-studio-mobile.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto('/sources', { waitUntil: 'networkidle' })
      await waitForReady(page, 'All Sources')
      await page.getByRole('button', { name: /Add New Source/i }).click()
      await waitForReady(page, 'URL(s)')
      await page.getByRole('tab', { name: /Add URL/i }).click()
      await page.locator('#url').fill('https://example.com/browser-smoke-source')
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByLabel(/BrainPulse competitive research/i).check()
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByRole('button', { name: /^Done$/i }).click()
      await waitForReady(page, 'Source Queued')
      await waitForReady(page, 'Browser smoke queued source')
      await waitForReady(page, 'https://example.com/browser-smoke-source')
      const sourceCreateBody = sourceCreateBodies.at(-1) || ''
      for (const expected of [
        'name="url"',
        'https://example.com/browser-smoke-source',
        'name="notebooks"',
        'notebook:alpha',
        'name="embed"',
        'true',
        'name="async_processing"',
      ]) {
        if (!sourceCreateBody.includes(expected)) {
          throw new Error(`Source create payload missing ${expected}: ${sourceCreateBody.slice(0, 2000)}`)
        }
      }
      await assertNoHorizontalOverflow(page, 'Sources ingestion desktop')
      await page.screenshot({ path: path.join(outputDir, 'source-ingestion-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto('/sources', { waitUntil: 'networkidle' })
      await waitForReady(page, 'All Sources')
      await page.getByRole('button', { name: /Add New Source/i }).click()
      await waitForReady(page, 'URL(s)')
      await page.getByRole('tab', { name: /Enter Text/i }).click()
      await page.locator('#source-title').fill('Browser smoke text source')
      await page.locator('#content').fill('This text source verifies pasted/manual source ingestion from the browser smoke.')
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByLabel(/BrainPulse competitive research/i).check()
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByRole('button', { name: /^Done$/i }).click()
      await waitForReady(page, 'Source Queued')
      await waitForReady(page, 'Browser smoke text source')
      const textCreateBody = sourceCreateBodies.at(-1) || ''
      for (const expected of [
        'name="type"',
        'text',
        'name="title"',
        'Browser smoke text source',
        'name="content"',
        'manual source ingestion',
        'name="notebooks"',
        'notebook:alpha',
        'name="embed"',
        'true',
      ]) {
        if (!textCreateBody.includes(expected)) {
          throw new Error(`Text source payload missing ${expected}: ${textCreateBody.slice(0, 2000)}`)
        }
      }
      await assertNoHorizontalOverflow(page, 'Text source ingestion desktop')
      await page.screenshot({ path: path.join(outputDir, 'source-ingestion-text-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto('/sources', { waitUntil: 'networkidle' })
      await waitForReady(page, 'All Sources')
      await page.getByRole('button', { name: /Add New Source/i }).click()
      await waitForReady(page, 'URL(s)')
      await page.getByRole('tab', { name: /Upload File/i }).click()
      await page.locator('#file').setInputFiles(uploadFixturePath)
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByLabel(/BrainPulse competitive research/i).check()
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByRole('button', { name: /^Done$/i }).click()
      await waitForReady(page, 'Source Queued')
      await waitForReady(page, 'source-upload-smoke.md')
      const uploadCreateBody = sourceCreateBodies.at(-1) || ''
      for (const expected of [
        'name="type"',
        'upload',
        'name="file"; filename="source-upload-smoke.md"',
        'name="notebooks"',
        'notebook:alpha',
        'name="embed"',
        'true',
      ]) {
        if (!uploadCreateBody.includes(expected)) {
          throw new Error(`Upload source payload missing ${expected}: ${uploadCreateBody.slice(0, 2000)}`)
        }
      }
      await assertNoHorizontalOverflow(page, 'File source ingestion desktop')
      await page.screenshot({ path: path.join(outputDir, 'source-ingestion-file-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto('/sources', { waitUntil: 'networkidle' })
      await waitForReady(page, 'All Sources')
      const createCountBefore = sourceCreateBodies.length
      await page.getByRole('button', { name: /Add New Source/i }).click()
      await waitForReady(page, 'URL(s)')
      await page.getByRole('tab', { name: /Upload File/i }).click()
      await page.locator('#file').setInputFiles(tooLargeUploadFixturePath)
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByLabel(/BrainPulse competitive research/i).check()
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByRole('button', { name: /^Done$/i }).click()
      await waitForReady(page, 'File is too large for the current upload limit.')
      await waitForReady(page, 'Error')
      const oversizedBodies = sourceCreateBodies.slice(createCountBefore)
      if (oversizedBodies.length !== 1 || !oversizedBodies[0].includes('source-upload-too-large.md')) {
        throw new Error(`Oversized upload should submit exactly one rejected request: ${oversizedBodies.length}`)
      }
      const visibleText = await page.locator('body').innerText({ timeout: 2_000 })
      if (visibleText.includes('source-upload-too-large.md')) {
        throw new Error('Oversized upload should not appear as a created source')
      }
      await assertNoHorizontalOverflow(page, 'Oversized file upload guard desktop')
      await page.screenshot({ path: path.join(outputDir, 'source-ingestion-oversized-file-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto('/sources', { waitUntil: 'networkidle' })
      await waitForReady(page, 'All Sources')
      const createCountBefore = sourceCreateBodies.length
      await page.getByRole('button', { name: /Add New Source/i }).click()
      await waitForReady(page, 'URL(s)')
      await page.getByRole('tab', { name: /Add URL/i }).click()
      await page.locator('#url').fill([
        'https://example.com/browser-smoke-batch-one',
        'https://example.com/browser-smoke-batch-two',
      ].join('\n'))
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByLabel(/BrainPulse competitive research/i).check()
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByRole('button', { name: /^Done$/i }).click()
      await waitForReady(page, 'https://example.com/browser-smoke-batch-one')
      await waitForReady(page, 'https://example.com/browser-smoke-batch-two')
      const batchBodies = sourceCreateBodies.slice(createCountBefore)
      if (batchBodies.length !== 2) {
        throw new Error(`Expected 2 batch source POSTs, got ${batchBodies.length}`)
      }
      for (const [index, expectedUrl] of [
        'https://example.com/browser-smoke-batch-one',
        'https://example.com/browser-smoke-batch-two',
      ].entries()) {
        const body = batchBodies[index] || ''
        for (const expected of [
          'name="type"',
          'link',
          'name="url"',
          expectedUrl,
          'name="notebooks"',
          'notebook:alpha',
          'name="embed"',
          'true',
        ]) {
          if (!body.includes(expected)) {
            throw new Error(`Batch source payload missing ${expected}: ${body.slice(0, 2000)}`)
          }
        }
      }
      await assertNoHorizontalOverflow(page, 'Batch source ingestion desktop')
      await page.screenshot({ path: path.join(outputDir, 'source-ingestion-batch-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto('/sources', { waitUntil: 'networkidle' })
      await waitForReady(page, 'All Sources')
      const createCountBefore = sourceCreateBodies.length
      await page.getByRole('button', { name: /Add New Source/i }).click()
      await waitForReady(page, 'URL(s)')
      await page.getByRole('tab', { name: /Add URL/i }).click()
      await page.locator('#url').fill([
        'https://example.com/browser-smoke-valid-url',
        'not-a-valid-url',
      ].join('\n'))
      await page.getByRole('button', { name: /^Next$/i }).click()
      await waitForReady(page, 'Invalid URLs detected')
      await waitForReady(page, 'Line 2')
      await waitForReady(page, 'not-a-valid-url')
      if (sourceCreateBodies.length !== createCountBefore) {
        throw new Error('Invalid URL batch should not submit source creation requests')
      }
      await assertNoHorizontalOverflow(page, 'Invalid URL batch guard desktop')
      await page.screenshot({ path: path.join(outputDir, 'source-ingestion-invalid-url-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto('/sources', { waitUntil: 'networkidle' })
      await waitForReady(page, 'All Sources')
      const createCountBefore = sourceCreateBodies.length
      await page.getByRole('button', { name: /Add New Source/i }).click()
      await waitForReady(page, 'URL(s)')
      await page.getByRole('tab', { name: /Add URL/i }).click()
      await page.locator('#url').fill([
        'https://example.com/browser-smoke-partial-success',
        'https://example.com/browser-smoke-partial-fail',
      ].join('\n'))
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByLabel(/BrainPulse competitive research/i).check()
      await page.getByRole('button', { name: /^Next$/i }).click()
      await page.getByRole('button', { name: /^Done$/i }).click()
      await waitForReady(page, '1 succeeded, 1 failed')
      await waitForReady(page, 'https://example.com/browser-smoke-partial-success')
      const visibleText = await page.locator('body').innerText({ timeout: 2_000 })
      if (visibleText.includes('https://example.com/browser-smoke-partial-fail')) {
        throw new Error('Partial batch failure URL should not appear as a created source')
      }
      const partialBodies = sourceCreateBodies.slice(createCountBefore)
      for (const expectedUrl of [
        'https://example.com/browser-smoke-partial-success',
        'https://example.com/browser-smoke-partial-fail',
      ]) {
        if (!partialBodies.some(body => body.includes(expectedUrl))) {
          throw new Error(`Partial batch did not attempt ${expectedUrl}`)
        }
      }
      await assertNoHorizontalOverflow(page, 'Partial batch source ingestion desktop')
      await page.screenshot({ path: path.join(outputDir, 'source-ingestion-partial-batch-desktop.png'), fullPage: true })
      await context.close()
    }

    {
      const { context, page } = await newPage({ width: 1440, height: 1100 })
      await page.goto(`/notebooks/${encodeURIComponent(notebookId)}`, { waitUntil: 'networkidle' })
      await waitForReady(page, 'Browser smoke failed source')
      await waitForReady(page, 'Failed')
      await page.getByRole('button', { name: /^Retry$/i }).click()
      await waitForCondition(
        'retry endpoint call',
        () => retryRequests.includes('POST /api/sources/source-retry-smoke/retry')
      )
      await waitForReady(page, 'Queued')
      await assertNoHorizontalOverflow(page, 'Source retry desktop')
      await page.screenshot({ path: path.join(outputDir, 'source-retry-desktop.png'), fullPage: true })
      await context.close()
    }
  } finally {
    await browser.close()
    await new Promise(resolve => fixtureServer.close(resolve))
  }

  if (missingApiRequests.length > 0) {
    throw new Error(`Unhandled API requests: ${[...new Set(missingApiRequests)].join(', ')}`)
  }
  if (pageErrors.length > 0) {
    throw new Error(`Page errors:\n${pageErrors.join('\n')}`)
  }
  const filteredConsoleIssues = consoleIssues.filter(issue => {
    const expectedPartialBatchFailure = sourceCreateBodies.some(
      body => body.includes('browser-smoke-partial-fail')
    )
    const expectedOversizedUploadFailure = sourceCreateBodies.some(
      body => body.includes('source-upload-too-large.md')
    )
    return !issue.includes('Download the React DevTools')
      && !issue.includes('Failed to load resource: the server responded with a status of 404')
      && !(expectedPartialBatchFailure && issue.includes('Failed to load resource: the server responded with a status of 502'))
      && !(expectedPartialBatchFailure && issue.includes('Error creating source for https://example.com/browser-smoke-partial-fail'))
      && !(expectedOversizedUploadFailure && issue.includes('Failed to load resource: the server responded with a status of 413'))
      && !(expectedOversizedUploadFailure && issue.includes('Error creating source:'))
  })
  if (filteredConsoleIssues.length > 0) {
    throw new Error(`Console issues:\n${filteredConsoleIssues.join('\n')}`)
  }

  console.log(`Visual smoke passed. Screenshots saved to ${outputDir}`)
}

main().catch(error => {
  console.error(error)
  process.exit(1)
})
