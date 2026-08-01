import type { Page, Route } from "@playwright/test";

export interface KnowledgeFixtureState {
  workspace: Record<string, unknown>;
  searchRequests: Array<Record<string, unknown>>;
  embeddingAvailable: boolean;
  bookmarks: Array<Record<string, unknown>>;
  namedWorkspaces: Array<Record<string, unknown>>;
  operationReceipts: Array<Record<string, unknown>>;
  randomSelections: string[];
  restorePlan: Record<string, unknown> | null;
  conflictWorkspaceUpdate: boolean;
  workspaceListReads: number;
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
  knowledge_document_id: string;
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
  knowledge_document_id: "knowledge_engine_document:plan",
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
  knowledge_document_id: "knowledge_engine_document:evidence",
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
    bookmarks: [],
    namedWorkspaces: [],
    operationReceipts: [],
    randomSelections: [],
    restorePlan: null,
    conflictWorkspaceUpdate: false,
    workspaceListReads: 0,
    workspace: {
      // Current Session is a V2 document.  Keep the fixture's durable copy on
      // the same wire contract that the client PUTs, so a reload exercises a
      // fresh GET rather than relying on an in-memory workspace shape.
      version: 2,
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
      navigation: {
        utility_mode: "sources",
        sidebar_visible: true,
        sidebar_width: 320,
        active_bookmark_folder_id: null,
        bookmark_tags: [],
        source_tree_query: "",
        search_query: "",
        search_mode: "text",
        active_draft_id: null,
        selected_space_ids: [],
        authority_filters: [],
        metrics_visible: false,
      },
    },
  };
}

function cloneWorkspaceWire(workspace: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(workspace)) as Record<string, unknown>;
}

function workspaceTabCount(workspace: Record<string, unknown>): number {
  const panes = workspace.panes
  if (!panes || typeof panes !== "object" || Array.isArray(panes)) return 0
  return Object.values(panes).reduce((count, pane) => (
    pane && typeof pane === "object" && !Array.isArray(pane)
      && Array.isArray((pane as { tabs?: unknown }).tabs)
      ? count + (pane as { tabs: unknown[] }).tabs.length
      : count
  ), 0)
}

function fixtureDescriptorForDocumentId(documentId: unknown): Record<string, unknown> | null {
  if (documentId === "knowledge_engine_document:plan") {
    return {
      document_id: documentId,
      space_id: "knowledge_engine_space:fixture",
      authority_kind: "external_read_only",
      source_kind: "obsidian",
      title: "Plan",
      relative_locator: "pages/plan.md",
      legacy_note_id: "note:plan",
      legacy_container_id: "vault:fixture",
    };
  }
  if (documentId === "knowledge_engine_document:evidence") {
    return {
      document_id: documentId,
      space_id: "knowledge_engine_space:fixture",
      authority_kind: "external_read_only",
      source_kind: "obsidian",
      title: "Evidence",
      relative_locator: "pages/evidence.md",
      legacy_note_id: "note:evidence",
      legacy_container_id: "vault:fixture",
    };
  }
  return null;
}

const fixtureNavigationId = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/;
const fixtureDocumentId = /^knowledge_engine_document:[A-Za-z0-9_-]+$/;
const fixtureSpaceId = /^knowledge_engine_space:[A-Za-z0-9_-]+$/;

function validFixtureOpaqueId(value: unknown): boolean {
  return value === null || (typeof value === "string" && fixtureNavigationId.test(value));
}

function validFixtureDocumentIds(value: unknown): boolean {
  return Array.isArray(value)
    && value.length <= 128
    && value.every((documentId) => typeof documentId === "string" && fixtureDocumentId.test(documentId));
}

function validFixtureSpaceIds(value: unknown): boolean {
  return Array.isArray(value)
    && value.length <= 32
    && value.every((spaceId) => typeof spaceId === "string" && fixtureSpaceId.test(spaceId));
}

function fixtureWorkspaceAuthorityForDocumentId(
  documentId: unknown,
): "app_owned" | "external_read_only" | null {
  const descriptor = fixtureDescriptorForDocumentId(documentId);
  if (descriptor?.authority_kind === "external_read_only") {
    return "external_read_only";
  }
  return typeof documentId === "string"
    && documentId.startsWith("knowledge_engine_document:overlay_")
    ? "app_owned"
    : null;
}

function validateNamedWorkspaceSnapshot(snapshot: unknown): string | null {
  if (!snapshot || typeof snapshot !== "object" || Array.isArray(snapshot)) return "snapshot_invalid";
  const value = snapshot as Record<string, unknown>;
  if (value.version !== 1 || !value.panes || typeof value.panes !== "object" || Array.isArray(value.panes)) return "snapshot_invalid";
  for (const pane of Object.values(value.panes as Record<string, unknown>)) {
    if (!pane || typeof pane !== "object" || Array.isArray(pane)) return "pane_invalid";
    const tabs = (pane as Record<string, unknown>).tabs;
    if (!Array.isArray(tabs)) return "tabs_invalid";
    for (const tab of tabs) {
      if (!tab || typeof tab !== "object" || Array.isArray(tab)) return "tab_invalid";
      const candidate = tab as Record<string, unknown>;
      const target = candidate.target;
      if (!target || typeof target !== "object" || Array.isArray(target)) return "target_invalid";
      const targetValue = target as Record<string, unknown>;
      const kind = targetValue.kind;
      const mode = candidate.mode;
      const viewMode = candidate.view_mode;
      if (kind === "document") {
        if (!fixtureDocumentId.test(String(targetValue.document_id)) || !["read", "write"].includes(String(mode))) return "document_mode_invalid";
        if (mode === "write" && viewMode !== "source") return "document_write_invalid";
        if (mode === "write" && fixtureWorkspaceAuthorityForDocumentId(targetValue.document_id) !== "app_owned") return "document_write_authority_invalid";
        continue;
      }
      if (kind === "search") {
        const query = targetValue.query;
        if (mode !== "search" || typeof query !== "string" || query.length > 512 || (query !== "" && query.trim() === "") || !validFixtureSpaceIds(targetValue.space_ids)) return "search_invalid";
        continue;
      }
      if (kind === "graph") {
        if (mode !== "graph" || (targetValue.root_document_id !== null && !fixtureDocumentId.test(String(targetValue.root_document_id))) || !validFixtureSpaceIds(targetValue.space_ids)) return "graph_invalid";
        continue;
      }
      if (kind === "ask") {
        if (mode !== "ask" || !validFixtureOpaqueId(targetValue.thread_id) || !validFixtureDocumentIds(targetValue.selected_document_ids)) return "ask_invalid";
        continue;
      }
      if (kind === "podcast") {
        if (mode !== "podcast" || !validFixtureOpaqueId(targetValue.production_id) || !validFixtureDocumentIds(targetValue.seed_document_ids)) return "podcast_invalid";
        continue;
      }
      return "target_kind_invalid";
    }
  }
  return null;
}

function restorePlanForFixtureWorkspace(workspace: Record<string, unknown>): Record<string, unknown> {
  const snapshot = workspace.snapshot as Record<string, unknown>;
  const panes = snapshot.panes as Record<string, Record<string, unknown>>;
  const summary = { available: 0, stale: 0, unavailable: 0, missing: 0 };
  return {
    workspace_id: workspace.id,
    revision: workspace.revision,
    active_pane_id: snapshot.active_pane_id,
    next_id: snapshot.next_id,
    panes: Object.fromEntries(Object.entries(panes).map(([paneId, pane]) => [paneId, {
      id: pane.id,
      active_tab_id: pane.active_tab_id,
      tabs: ((pane.tabs as Array<Record<string, unknown>>) ?? []).map((tab) => {
        const target = tab.target as Record<string, unknown>;
        const documentId = target.kind === "graph"
          ? target.root_document_id
          : target.document_id;
        const targetDocument = target.kind === "search"
          ? null
          : fixtureDescriptorForDocumentId(documentId);
        // Overlay pages are created dynamically by this fixture. Their stable
        // document IDs are recoverable from the app-owned target itself.
        const overlayId = typeof documentId === "string"
          && documentId.startsWith("knowledge_engine_document:overlay_fixture_")
          ? documentId.slice("knowledge_engine_document:".length)
          : null;
        const overlayOrdinal = overlayId ? Number(overlayId.replace("overlay_fixture_", "")) : Number.NaN;
        const overlay = Number.isInteger(overlayOrdinal)
          ? { id: `overlay_note:fixture_${overlayOrdinal}`, title: tab.display_label }
          : null;
        const resolvedDocument = targetDocument ?? (overlay ? {
          document_id: documentId,
          space_id: "knowledge_engine_space:fixture",
          authority_kind: "app_owned",
          source_kind: "overlay",
          title: overlay.title,
          relative_locator: `Unique/20260730-1200 ${overlay.title}.md`,
          legacy_note_id: `overlay_note:fixture_${overlayOrdinal}`,
          legacy_container_id: "overlay_space:default",
        } : null);
        summary.available += 1;
        return {
          id: tab.id,
          display_label: tab.display_label,
          view_mode: tab.view_mode,
          mode: tab.mode,
          target,
          target_state: "available",
          target_document: resolvedDocument,
        };
      }),
    }])),
    layout: snapshot.layout,
    navigation: snapshot.navigation,
    summary,
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
    {
      name: "onp_intro_seen",
      value: "1",
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
  await fulfillJson(page, "/api/health", { status: "healthy" }, unexpectedApiTraffic);
  await fulfillJson(page, "/api/adapters", [], unexpectedApiTraffic);
  await fulfillJson(page, "/api/auth/get-session", null, unexpectedApiTraffic);
  await fulfillJson(page, "/api/companies", [], unexpectedApiTraffic);
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

  if (path.includes("/deeper-notebook/knowledge/workspaces/") && path.endsWith("/restore-plan")) {
    if (!(await allowRequestMethod(route, ["POST"], unexpectedApiTraffic))) return;
    const workspaceId = decodeURIComponent(path.split("/").at(-2) ?? "");
    const workspace = state.namedWorkspaces.find((candidate) => candidate.id === workspaceId);
    payload = state.restorePlan ?? (workspace ? restorePlanForFixtureWorkspace(workspace) : null);
  } else if (path.includes("/deeper-notebook/knowledge/workspaces/") && method === "PATCH") {
    if (!(await allowRequestMethod(route, ["PATCH"], unexpectedApiTraffic))) return;
    if (state.conflictWorkspaceUpdate) {
      state.conflictWorkspaceUpdate = false;
      await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: "conflict" }) });
      return;
    }
    const workspaceId = decodeURIComponent(path.split("/").at(-1) ?? "");
    const workspace = state.namedWorkspaces.find((candidate) => candidate.id === workspaceId);
    const body = request.postDataJSON() as Record<string, unknown>;
    if (!workspace || body.expected_revision !== workspace.revision) {
      await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ detail: "conflict" }) });
      return;
    }
    if ("snapshot" in body) {
      const invalidSnapshot = validateNamedWorkspaceSnapshot(body.snapshot);
      if (invalidSnapshot) {
        await route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: { code: invalidSnapshot } }) });
        return;
      }
      workspace.snapshot = body.snapshot;
    } else if (typeof body.name === "string" && body.name.trim()) {
      const name = body.name.trim();
      workspace.name = name;
      workspace.name_key = name.toLocaleLowerCase();
    } else {
      await route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: { code: "workspace_update_invalid" } }) });
      return;
    }
    workspace.revision = Number(workspace.revision) + 1;
    workspace.updated_at = "2026-08-01T00:00:00Z";
    payload = workspace;
  } else if (path.endsWith("/deeper-notebook/knowledge/bookmarks")) {
    if (!(await allowRequestMethod(route, ["GET", "HEAD", "POST"], unexpectedApiTraffic))) return;
    if (method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      const ordinal = state.bookmarks.length + 1;
      const now = "2026-07-31T00:00:00Z";
      const bookmark = {
        schema_version: 1,
        id: `knowledge_bookmark:fixture_${ordinal}`,
        target_kind: (body.target as Record<string, unknown>).kind,
        target: body.target,
        display_label: body.display_label,
        authority_kind: body.authority_kind,
        space_id: body.space_id,
        folder_id: body.folder_id,
        tags: body.tags,
        position: body.position,
        revision: 1,
        created_at: now,
        updated_at: now,
      };
      state.bookmarks.push({
        ...bookmark,
        target_state: "available",
        target_document: {
          document_id: "knowledge_engine_document:evidence",
          space_id: "knowledge_engine_space:fixture",
          authority_kind: "external_read_only",
          source_kind: "obsidian",
          title: "Evidence",
          relative_locator: "pages/evidence.md",
          legacy_note_id: "note:evidence",
          legacy_container_id: "vault:fixture",
        },
      });
      state.operationReceipts.push({ operation_id: body.operation_id, entity_id: bookmark.id });
      payload = bookmark;
    } else payload = { items: state.bookmarks, next_cursor: null };
  } else if (path.endsWith("/deeper-notebook/knowledge/bookmark-folders")) {
    if (!(await allowRequestMethod(route, ["GET", "HEAD"], unexpectedApiTraffic))) return;
    payload = { items: [] };
  } else if (path.endsWith("/deeper-notebook/knowledge/random-note")) {
    if (!(await allowRequestMethod(route, ["POST"], unexpectedApiTraffic))) return;
    state.randomSelections.push("note:evidence");
    payload = {
      state: "selected",
      document: {
        document_id: "knowledge_engine_document:evidence",
        space_id: "knowledge_engine_space:fixture",
        authority_kind: "external_read_only",
        source_kind: "obsidian",
        title: "Evidence",
        relative_locator: "pages/evidence.md",
        legacy_note_id: "note:evidence",
        legacy_container_id: "vault:fixture",
      },
    };
  } else if (path.endsWith("/deeper-notebook/knowledge/workspaces")) {
    if (!(await allowRequestMethod(route, ["GET", "HEAD", "POST"], unexpectedApiTraffic))) return;
    if (method === "POST") {
      const body = request.postDataJSON() as Record<string, unknown>;
      const invalidSnapshot = validateNamedWorkspaceSnapshot(body.snapshot);
      if (invalidSnapshot) {
        await route.fulfill({ status: 422, contentType: "application/json", body: JSON.stringify({ detail: { code: invalidSnapshot } }) });
        return;
      }
      const ordinal = state.namedWorkspaces.length + 1;
      const workspace = {
        schema_version: 1,
        id: `named_knowledge_workspace:fixture_${ordinal}`,
        name: body.name,
        name_key: String(body.name).toLocaleLowerCase(),
        snapshot_version: 1,
        snapshot: body.snapshot,
        capacity_slot: ordinal,
        revision: 1,
        created_at: "2026-07-31T00:00:00Z",
        updated_at: "2026-07-31T00:00:00Z",
      };
      state.namedWorkspaces.push(workspace);
      state.operationReceipts.push({ operation_id: body.operation_id, entity_id: workspace.id });
      payload = workspace;
    } else {
      state.workspaceListReads += 1;
      payload = { items: state.namedWorkspaces.map((workspace) => ({
      id: workspace.id, name: workspace.name, revision: workspace.revision, updated_at: workspace.updated_at,
      })) };
    }
  } else if (path.endsWith("/deeper-notebook/workspace/knowledge")) {
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
      const incoming = cloneWorkspaceWire(
        request.postDataJSON() as Record<string, unknown>,
      );
      // A reload can finish an already-scheduled empty startup save after the
      // durable V2 session was read.  The real Current Session must keep the
      // saved non-empty document for that reload; do not let this stale empty
      // fixture write erase it.
      if (workspaceTabCount(incoming) > 0 || workspaceTabCount(state.workspace) === 0) {
        state.workspace = incoming;
      }
    }
    payload = cloneWorkspaceWire(state.workspace);
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
    knowledge_document_id: `knowledge_engine_document:overlay_${note.id.slice("overlay_note:".length)}`,
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
