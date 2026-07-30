import type { Page, Route } from "@playwright/test";

export interface KnowledgeFixtureState {
  workspace: Record<string, unknown>;
  searchRequests: Array<Record<string, unknown>>;
  embeddingAvailable: boolean;
}

export interface StrictOverlayFixtureNote {
  id: string;
  source_authority: "overlay";
  space_id: "overlay_space:default";
  projected_note_id: string;
  stable_id: string;
  kind: "daily" | "unique";
  date_key: string | null;
  relative_path: string;
  title: string;
  content_hash: string;
  revision: number;
  projection_state: "current";
  encoding: "utf-8";
  newline: "lf";
  created_at: string;
  updated_at: string;
}

interface StrictOverlayFixturePage {
  overlay: StrictOverlayFixtureNote;
  editable_markdown: string;
  note: {
    id: string;
    title: string;
    content: string;
    properties: Record<string, unknown>;
    tags: string[];
  };
  blocks: unknown[];
  tasks: unknown[];
  outgoing_links: unknown[];
  backlinks: unknown[];
  graph: { nodes: unknown[]; edges: unknown[] };
}

export interface StrictKnowledgeFixture {
  state: KnowledgeFixtureState;
  overlayNotes: StrictOverlayFixtureNote[];
  dailyRequests: string[];
  overlayMutationRequests: string[];
  externalMutationRequests: string[];
  unexpectedRequests: string[];
  injectNextSaveConflict: () => void;
}

const planFile = {
  id: "vault_file:plan",
  note_id: "note:plan",
  vault_id: "vault:fixture",
  relative_path: "pages/plan.md",
  file_kind: "markdown",
  format: "obsidian",
  content_hash: "a".repeat(64),
  size_bytes: 34,
  modified_ns: 1,
  encoding: "utf-8",
  newline: "lf",
  parse_status: "parsed",
  deleted_state: "present",
};

const evidenceFile = {
  ...planFile,
  id: "vault_file:evidence",
  note_id: "note:evidence",
  relative_path: "pages/evidence.md",
  content_hash: "b".repeat(64),
};

const files = [planFile, evidenceFile];

const planPage = {
  file: planFile,
  note: {
    id: "note:plan",
    title: "Plan",
    content: "# Plan\n\nPlan fixture content.\n\n[[Evidence]]",
    source_format: "obsidian",
    properties: { status: "active" },
    tags: ["research"],
  },
  blocks: [
    {
      markdown: "# Plan",
      plain_text: "Plan",
      heading_path: ["Plan"],
      block_kind: "heading",
    },
  ],
  tasks: [],
  outgoing_links: [
    {
      id: "note_link:plan-evidence",
      source_note_id: "note:plan",
      target_note_id: "note:evidence",
      target_note_title: "Evidence",
      target_relative_path: "pages/evidence.md",
      target_text: "Evidence",
      link_kind: "wikilink",
      resolved: true,
      source_start: 8,
      source_end: 20,
    },
  ],
  backlinks: [],
};

const evidencePage = {
  file: evidenceFile,
  note: {
    id: "note:evidence",
    title: "Evidence",
    content: "# Evidence\n\nRead-only external file",
    source_format: "obsidian",
    properties: { status: "verified" },
    tags: ["evidence"],
  },
  blocks: [
    {
      markdown: "# Evidence",
      plain_text: "Evidence",
      heading_path: ["Evidence"],
      block_kind: "heading",
    },
  ],
  tasks: [],
  outgoing_links: [],
  backlinks: [],
};

const fixturePagePaths = {
  plan: [
    "/api/deeper-notebook/vaults/vault%3Afixture/pages/note%3Aplan",
    "/api/deeper-notebook/vaults/vault:fixture/pages/note:plan",
  ],
  evidence: [
    "/api/deeper-notebook/vaults/vault%3Afixture/pages/note%3Aevidence",
    "/api/deeper-notebook/vaults/vault:fixture/pages/note:evidence",
  ],
} as const;

type FixturePageRoute = "page" | "outgoing" | "backlinks";
type FixturePageName = keyof typeof fixturePagePaths;

function matchFixturePageRoute(pathname: string): {
  name: FixturePageName;
  route: FixturePageRoute;
} | null {
  for (const [name, pagePaths] of Object.entries(fixturePagePaths) as Array<
    [FixturePageName, readonly string[]]
  >) {
    for (const pagePath of pagePaths) {
      if (pathname === pagePath) return { name, route: "page" };
      if (pathname === `${pagePath}/outgoing`)
        return { name, route: "outgoing" };
      if (pathname === `${pagePath}/backlinks`)
        return { name, route: "backlinks" };
    }
  }
  return null;
}

export function initialKnowledgeFixtureState(): KnowledgeFixtureState {
  return {
    searchRequests: [],
    embeddingAvailable: true,
    workspace: {
      version: 1,
      active_pane_id: "pane-1",
      next_id: 2,
      panes: {
        "pane-1": {
          id: "pane-1",
          active_tab_id: null,
          tabs: [],
        },
      },
      layout: { type: "pane", pane_id: "pane-1" },
    },
  };
}

async function fulfillJson(
  page: Page,
  pathname: string,
  body: unknown,
  unexpectedApiTraffic: string[],
  allowedMethods: readonly string[] = ["GET", "HEAD"],
): Promise<void> {
  await page.route(
    (url) => url.pathname === pathname,
    async (route) => {
      if (
        !(await allowRequestMethod(route, allowedMethods, unexpectedApiTraffic))
      ) {
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    },
  );
}

function requestLabel(route: Route): string {
  const request = route.request();
  return `${request.method()} ${new URL(request.url()).pathname}`;
}

async function allowRequestMethod(
  route: Route,
  allowedMethods: readonly string[],
  unexpectedApiTraffic: string[],
): Promise<boolean> {
  if (allowedMethods.includes(route.request().method())) {
    return true;
  }

  unexpectedApiTraffic.push(requestLabel(route));
  await route.fulfill({
    status: 405,
    contentType: "application/json",
    headers: { Allow: allowedMethods.join(", ") },
    body: JSON.stringify({ detail: "Method not allowed by E2E fixture" }),
  });
  return false;
}

export async function installKnowledgeShellMocks(
  page: Page,
  unexpectedApiTraffic: string[] = [],
): Promise<void> {
  await page.context().addCookies([
    {
      name: "wizard_completed",
      value: "true",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);

  await page.route("**/api/**", async (route) => {
    unexpectedApiTraffic.push(requestLabel(route));
    await route.fulfill({
      status: 501,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Unhandled API request in E2E fixture" }),
    });
  });

  await fulfillJson(page, "/config", { apiUrl: "" }, unexpectedApiTraffic);
  await fulfillJson(
    page,
    "/api/config",
    {
      version: "fixture",
      latestVersion: null,
      hasUpdate: false,
      dbStatus: "healthy",
    },
    unexpectedApiTraffic,
  );
  await fulfillJson(
    page,
    "/api/auth/status",
    { auth_required: false },
    unexpectedApiTraffic,
  );
  await fulfillJson(
    page,
    "/api/version",
    { version: "fixture" },
    unexpectedApiTraffic,
  );
  await fulfillJson(
    page,
    "/api/local-models/health",
    {
      overall: "healthy",
      models: [],
    },
    unexpectedApiTraffic,
  );
  await fulfillJson(page, "/api/notebooks", [], unexpectedApiTraffic);
  await fulfillJson(page, "/api/sources", [], unexpectedApiTraffic);
  await fulfillJson(page, "/api/episode-profiles", [], unexpectedApiTraffic);
  await fulfillJson(page, "/api/speaker-profiles", [], unexpectedApiTraffic);
  await fulfillJson(
    page,
    "/api/deeper-notebook/gmail/status",
    {
      connected: false,
      email_address: null,
      has_client_credentials: false,
    },
    unexpectedApiTraffic,
  );
  await fulfillJson(
    page,
    "/api/credentials/status",
    {
      configured: {},
      source: {},
      encryption_configured: false,
    },
    unexpectedApiTraffic,
  );
  await fulfillJson(
    page,
    "/api/credentials/env-status",
    {},
    unexpectedApiTraffic,
  );
  await fulfillJson(
    page,
    "/api/system/db-repair-needed",
    { needs_repair: false },
    unexpectedApiTraffic,
  );
  await fulfillJson(
    page,
    "/api/updates/check",
    {
      current: "fixture",
      latest: null,
      update_available: false,
      skipped: false,
      skipped_version: null,
      html_url: null,
      published_at: null,
      enabled: false,
      last_check: null,
    },
    unexpectedApiTraffic,
  );
  await fulfillJson(
    page,
    "/api/system/network-status",
    {
      status: "online",
      forced_offline: false,
      local_fallback_model: null,
      checked_epoch_ms: 0,
    },
    unexpectedApiTraffic,
  );
  await fulfillJson(page, "/api/transformations", [], unexpectedApiTraffic);
  await fulfillJson(page, "/api/settings", {}, unexpectedApiTraffic);
  await fulfillJson(
    page,
    "/healthz/deep",
    {
      status: "healthy",
      checks: {
        database: { status: "ready", ok: true, error: null },
        migrations: { status: "ready", ok: true, error: null },
        embedding_model: { status: "ready", ok: true, error: null },
        chat_model: { status: "ready", ok: true, error: null },
        command_registry: { status: "ready", ok: true, error: null },
      },
    },
    unexpectedApiTraffic,
  );
  await fulfillJson(
    page,
    "/api/healthz/deep",
    {
      status: "healthy",
      checks: {
        database: { status: "ready", ok: true, error: null },
        migrations: { status: "ready", ok: true, error: null },
        embedding_model: { status: "ready", ok: true, error: null },
        chat_model: { status: "ready", ok: true, error: null },
        command_registry: { status: "ready", ok: true, error: null },
      },
    },
    unexpectedApiTraffic,
  );
}

export async function fulfillKnowledgeRequest(
  route: Route,
  state: KnowledgeFixtureState,
  unexpectedApiTraffic: string[] = [],
): Promise<void> {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  const method = request.method();
  const pageRoute = matchFixturePageRoute(path);
  let payload: unknown;

  if (path.endsWith("/deeper-notebook/workspace/knowledge")) {
    if (
      !(await allowRequestMethod(
        route,
        ["GET", "HEAD", "PUT"],
        unexpectedApiTraffic,
      ))
    ) {
      return;
    }
    if (method === "PUT") {
      state.workspace = request.postDataJSON() as Record<string, unknown>;
    }
    payload = state.workspace;
  } else if (path.endsWith("/deeper-notebook/overlay/notes")) {
    if (
      !(await allowRequestMethod(route, ["GET", "HEAD"], unexpectedApiTraffic))
    ) {
      return;
    }
    payload = [];
  } else if (path.endsWith("/deeper-notebook/vaults")) {
    if (
      !(await allowRequestMethod(route, ["GET", "HEAD"], unexpectedApiTraffic))
    ) {
      return;
    }
    payload = [
      {
        id: "vault:fixture",
        name: "Fixture vault",
        format_mode: "obsidian",
        state: "ready-read-only",
        parent_vault_id: null,
        watch_enabled: false,
      },
    ];
  } else if (
    path.endsWith("/vaults/vault%3Afixture/files") ||
    path.endsWith("/vaults/vault:fixture/files")
  ) {
    if (
      !(await allowRequestMethod(route, ["GET", "HEAD"], unexpectedApiTraffic))
    ) {
      return;
    }
    payload = files;
  } else if (pageRoute !== null) {
    if (
      !(await allowRequestMethod(route, ["GET", "HEAD"], unexpectedApiTraffic))
    ) {
      return;
    }
    const fixturePage = pageRoute.name === "plan" ? planPage : evidencePage;
    payload =
      pageRoute.route === "outgoing"
        ? fixturePage.outgoing_links
        : pageRoute.route === "backlinks"
          ? fixturePage.backlinks
          : fixturePage;
  } else if (
    path.endsWith("/vaults/vault%3Afixture/scan") ||
    path.endsWith("/vaults/vault:fixture/scan")
  ) {
    if (!(await allowRequestMethod(route, ["POST"], unexpectedApiTraffic)))
      return;
    payload = {
      operation_id: "scan:fixture",
      state: "completed",
      observed: 2,
      parsed: 2,
      unchanged: 0,
      unsupported: 0,
      invalid: 0,
      missing: 0,
      embeddings_pending: 0,
    };
  } else if (
    path.endsWith("/vaults/vault%3Afixture/graph") ||
    path.endsWith("/vaults/vault:fixture/graph")
  ) {
    if (
      !(await allowRequestMethod(route, ["GET", "HEAD"], unexpectedApiTraffic))
    ) {
      return;
    }
    payload = {
      nodes: [
        {
          id: "note:plan",
          title: "Plan",
          source_format: "obsidian",
          external_state: "current",
        },
      ],
      edges: [],
    };
  } else {
    await route.fallback();
    return;
  }

  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(payload),
  });
}

export async function fulfillKnowledgeSearchRequest(
  route: Route,
  state: KnowledgeFixtureState,
  unexpectedApiTraffic: string[] = [],
): Promise<void> {
  if (!(await allowRequestMethod(route, ["POST"], unexpectedApiTraffic)))
    return;
  const body = route.request().postDataJSON() as Record<string, unknown>;
  state.searchRequests.push(body);
  if (body.type === "vector" && !state.embeddingAvailable) {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "Vector search requires an embedding model",
      }),
    });
    return;
  }
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      results: [
        {
          id: "note:plan",
          title: "Plan",
          parent_id: "vault:fixture",
          final_score: 1,
          created: "",
          updated: "",
          vault_provenance: {
            canonical_external: true,
            vault_id: "vault:fixture",
            relative_path: "pages/plan.md",
            source_hash: planFile.content_hash,
          },
        },
      ],
      total_count: 1,
      search_type: body.type,
    }),
  });
}

export async function installKnowledgeRoutes(
  page: Page,
  state: KnowledgeFixtureState,
  vaultWrites: string[],
  unexpectedApiTraffic: string[],
): Promise<void> {
  await page.route("**/api/deeper-notebook/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    if (
      pathname.includes("/api/deeper-notebook/vaults") &&
      !["GET", "HEAD"].includes(request.method()) &&
      !pathname.endsWith("/scan")
    )
      vaultWrites.push(requestLabel(route));
    await fulfillKnowledgeRequest(route, state, unexpectedApiTraffic);
  });
  await page.route("**/api/search", async (route) => {
    await fulfillKnowledgeSearchRequest(route, state, unexpectedApiTraffic);
  });
}

function fixtureOverlayHash(revision: number, ordinal: number): string {
  return `${revision.toString(16)}${ordinal.toString(16)}`.padStart(64, "0");
}

function strictOverlayPage(
  note: StrictOverlayFixtureNote,
  markdown: string,
): StrictOverlayFixturePage {
  return {
    overlay: note,
    editable_markdown: markdown,
    note: {
      id: note.projected_note_id,
      title: note.title,
      content: `---\ntitle: ${note.title}\ndeeper_notebook:\n  id: ${note.id}\n---\n${markdown}`,
      properties: {},
      tags: [],
    },
    blocks: [],
    tasks: [],
    outgoing_links: [],
    backlinks: [],
    graph: { nodes: [], edges: [] },
  };
}

function fulfillFixtureJson(
  route: Route,
  body: unknown,
  status = 200,
): Promise<void> {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function overlayNotePath(pathname: string): string | null {
  const prefix = "/api/deeper-notebook/overlay/notes/";
  if (!pathname.startsWith(prefix)) return null;
  const suffix = pathname.slice(prefix.length);
  if (!suffix || suffix === "unique" || suffix.includes("/")) return null;
  return decodeURIComponent(suffix);
}

export async function installStrictKnowledgeFixture(
  page: Page,
): Promise<StrictKnowledgeFixture> {
  const state = initialKnowledgeFixtureState();
  const overlayNotes: StrictOverlayFixtureNote[] = [];
  const pages = new Map<string, StrictOverlayFixturePage>();
  const dailyRequests: string[] = [];
  const overlayMutationRequests: string[] = [];
  const externalMutationRequests: string[] = [];
  const unexpectedRequests: string[] = [];
  let nextOrdinal = 1;
  let conflictNextSave = false;

  const addOverlay = (
    kind: "daily" | "unique",
    title: string,
    dateKey: string | null,
    relativePath: string,
  ): StrictOverlayFixturePage => {
    const ordinal = nextOrdinal;
    nextOrdinal += 1;
    const id = `overlay_note:fixture_${ordinal}`;
    const now = "2026-07-30T17:00:00+00:00";
    const note: StrictOverlayFixtureNote = {
      id,
      source_authority: "overlay",
      space_id: "overlay_space:default",
      projected_note_id: `note:overlay_fixture_${ordinal}`,
      stable_id: `stable-overlay-fixture-${ordinal.toString().padStart(4, "0")}`,
      kind,
      date_key: dateKey,
      relative_path: relativePath,
      title,
      content_hash: fixtureOverlayHash(1, ordinal),
      revision: 1,
      projection_state: "current",
      encoding: "utf-8",
      newline: "lf",
      created_at: now,
      updated_at: now,
    };
    const created = strictOverlayPage(note, `# ${title}\n`);
    overlayNotes.push(note);
    pages.set(id, created);
    return created;
  };

  await installKnowledgeShellMocks(page, unexpectedRequests);
  await page.route("**/api/deeper-notebook/**", async (route) => {
    const request = route.request();
    const pathname = new URL(request.url()).pathname;
    const method = request.method();
    const label = requestLabel(route);

    if (
      pathname.includes("/api/deeper-notebook/vaults") &&
      ["POST", "PUT", "PATCH", "DELETE"].includes(method)
    ) {
      externalMutationRequests.push(label);
      await fulfillFixtureJson(
        route,
        {
          detail: "External vault mutations are not installed by this fixture",
        },
        405,
      );
      return;
    }

    if (pathname === "/api/deeper-notebook/overlay") {
      if (!["GET", "HEAD"].includes(method)) {
        unexpectedRequests.push(label);
        await fulfillFixtureJson(route, { detail: "Method not allowed" }, 405);
        return;
      }
      await fulfillFixtureJson(route, {
        id: "overlay_space:default",
        source_authority: "overlay",
      });
      return;
    }

    if (pathname === "/api/deeper-notebook/overlay/notes") {
      if (!["GET", "HEAD"].includes(method)) {
        unexpectedRequests.push(label);
        await fulfillFixtureJson(route, { detail: "Method not allowed" }, 405);
        return;
      }
      await fulfillFixtureJson(route, overlayNotes);
      return;
    }

    const dailyMatch = pathname.match(
      /^\/api\/deeper-notebook\/overlay\/daily\/(\d{4}-\d{2}-\d{2})$/,
    );
    if (dailyMatch) {
      if (method !== "PUT") {
        unexpectedRequests.push(label);
        await fulfillFixtureJson(route, { detail: "Method not allowed" }, 405);
        return;
      }
      overlayMutationRequests.push(label);
      const dateKey = dailyMatch[1];
      dailyRequests.push(dateKey);
      const existing = overlayNotes.find(
        (note) => note.kind === "daily" && note.date_key === dateKey,
      );
      const created = existing
        ? pages.get(existing.id)!
        : addOverlay("daily", dateKey, dateKey, `Daily/${dateKey}.md`);
      await fulfillFixtureJson(route, created);
      return;
    }

    if (pathname === "/api/deeper-notebook/overlay/notes/unique") {
      if (method !== "POST") {
        unexpectedRequests.push(label);
        await fulfillFixtureJson(route, { detail: "Method not allowed" }, 405);
        return;
      }
      overlayMutationRequests.push(label);
      const body = request.postDataJSON() as {
        title?: string;
        idempotency_key?: string;
      };
      const title = body.title?.trim();
      if (!title || !body.idempotency_key) {
        await fulfillFixtureJson(
          route,
          { detail: { code: "overlay_request_invalid" } },
          422,
        );
        return;
      }
      const stem = `20260730-1200 ${title}`;
      const collision = overlayNotes.filter(
        (note) =>
          note.relative_path === `Unique/${stem}.md` ||
          note.relative_path.startsWith(`Unique/${stem}-`),
      ).length;
      const suffix = collision === 0 ? "" : `-${collision + 1}`;
      const created = addOverlay(
        "unique",
        title,
        null,
        `Unique/${stem}${suffix}.md`,
      );
      await fulfillFixtureJson(route, created, 201);
      return;
    }

    const noteId = overlayNotePath(pathname);
    if (noteId) {
      const overlayPage = pages.get(noteId);
      if (!overlayPage) {
        await fulfillFixtureJson(
          route,
          { detail: { code: "overlay_not_found" } },
          404,
        );
        return;
      }
      if (["GET", "HEAD"].includes(method)) {
        await fulfillFixtureJson(route, overlayPage);
        return;
      }
      if (method !== "PUT") {
        unexpectedRequests.push(label);
        await fulfillFixtureJson(route, { detail: "Method not allowed" }, 405);
        return;
      }
      overlayMutationRequests.push(label);
      const body = request.postDataJSON() as {
        title?: string;
        markdown?: string;
        expected_revision?: number;
        idempotency_key?: string;
      };
      if (
        conflictNextSave ||
        body.expected_revision !== overlayPage.overlay.revision
      ) {
        conflictNextSave = false;
        overlayPage.overlay.revision += 1;
        overlayPage.overlay.content_hash = fixtureOverlayHash(
          overlayPage.overlay.revision,
          overlayNotes.indexOf(overlayPage.overlay) + 1,
        );
        overlayPage.editable_markdown =
          `# ${overlayPage.overlay.title}\n\nServer revision\n`;
        overlayPage.note.content = [
          "---",
          `title: ${overlayPage.overlay.title}`,
          "deeper_notebook:",
          `  id: ${overlayPage.overlay.id}`,
          "---",
          overlayPage.editable_markdown,
        ].join("\n");
        await fulfillFixtureJson(
          route,
          { detail: { code: "overlay_revision_conflict" } },
          409,
        );
        return;
      }
      if (
        !body.title?.trim() ||
        typeof body.markdown !== "string" ||
        !body.idempotency_key
      ) {
        await fulfillFixtureJson(
          route,
          { detail: { code: "overlay_request_invalid" } },
          422,
        );
        return;
      }
      overlayPage.overlay.revision += 1;
      overlayPage.overlay.title = body.title.trim();
      overlayPage.overlay.content_hash = fixtureOverlayHash(
        overlayPage.overlay.revision,
        overlayNotes.indexOf(overlayPage.overlay) + 1,
      );
      overlayPage.overlay.updated_at = "2026-07-30T17:01:00+00:00";
      overlayPage.note.title = overlayPage.overlay.title;
      overlayPage.editable_markdown = body.markdown;
      overlayPage.note.content = `---\ntitle: ${overlayPage.overlay.title}\ndeeper_notebook:\n  id: ${overlayPage.overlay.id}\n---\n${body.markdown}`;
      await fulfillFixtureJson(route, overlayPage);
      return;
    }

    await fulfillKnowledgeRequest(route, state, unexpectedRequests);
  });
  await page.route("**/api/search", async (route) => {
    await fulfillKnowledgeSearchRequest(route, state, unexpectedRequests);
  });

  return {
    state,
    overlayNotes,
    dailyRequests,
    overlayMutationRequests,
    externalMutationRequests,
    unexpectedRequests,
    injectNextSaveConflict: () => {
      conflictNextSave = true;
    },
  };
}

export async function openExternalEvidenceNote(page: Page): Promise<void> {
  await page
    .getByLabel(/Mounted vaults|Mounts/)
    .selectOption("external-vault:vault:fixture");
  await page
    .getByRole("treeitem", { name: "pages/evidence.md", exact: true })
    .click();
}
