import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  registerKnowledgeCommandContext,
  resetKnowledgeCommandContextStore,
} from "@/lib/commands/knowledge-command-context-store";
import {
  requestCommandSurface,
  resetCommandSurfaceStore,
} from "@/lib/commands/command-surface-store";
import { useKnowledgeWorkspaceStore } from "@/lib/stores/knowledge-workspace-store";
import type { SearchResponse } from "@/lib/types/search";

const router = vi.hoisted(() => ({ push: vi.fn() }));
const dialogs = vi.hoisted(() => ({
  openSourceDialog: vi.fn(),
  openNotebookDialog: vi.fn(),
  openPodcastDialog: vi.fn(),
}));
const theme = vi.hoisted(() => ({ setTheme: vi.fn() }));
const indexed = vi.hoisted(() => ({
  runSemanticSearch: vi.fn(),
  text: {
    data: { results: [], total_count: 0, search_type: "text" } as
      SearchResponse | undefined,
    isCurrent: true,
  },
  semantic: {
    data: undefined as SearchResponse | undefined,
    variables: undefined as string | undefined,
    isError: false,
    error: null as Error | null,
  },
}));
const commandData = vi.hoisted(() => ({
  catalog: {
    candidates: [] as Array<{
      key: string;
      vaultId: string;
      noteId: string;
      vaultName: string;
      format: "markdown";
      title: string;
      relativePath: string;
      isOpen: boolean;
    }>,
    isLoading: false,
    failedVaultCount: 0,
    retryFailedVaults: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({ useRouter: () => router }));
vi.mock("@/lib/hooks/use-create-dialogs", () => ({
  useCreateDialogs: () => dialogs,
}));
vi.mock("@/lib/hooks/use-notebooks", () => ({
  useNotebooks: () => ({
    data: [{ id: "notebook-1", name: "Research Core", description: "" }],
    isLoading: false,
  }),
}));
vi.mock("@/lib/stores/theme-store", () => ({ useTheme: () => theme }));
vi.mock("@/lib/hooks/use-translation", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { query?: string }) =>
      ({
        "common.quickActions": "Quick actions",
        "common.quickActionsDesc": "Quick actions description",
        "common.search": "Search",
        "common.noResults": "No results found.",
        "common.newSource": "New source",
        "common.newNotebook": "New notebook",
        "common.newPodcast": "New podcast",
        "common.light": "Light",
        "common.dark": "Dark",
        "common.system": "System",
        "navigation.sources": "Sources",
        "navigation.notebooks": "Notebooks",
        "navigation.askAndSearch": "Search and Ask",
        "navigation.podcasts": "Podcasts",
        "navigation.models": "Models",
        "navigation.transformations": "Transformations",
        "navigation.settings": "Settings",
        "navigation.advanced": "Advanced",
        "navigation.nav": "Navigation",
        "navigation.create": "Create",
        "navigation.theme": "Theme",
        "notebooks.title": "Notebooks",
        "searchPage.enterSearchPlaceholder": "Search commands",
        "searchPage.searchAndAsk": "Search and Ask",
        "searchPage.orSearchKb": "Or search",
        "searchPage.searchResultsFor": `Search results for ${options?.query ?? "{query}"}`,
        "searchPage.askAbout": `Ask about ${options?.query ?? "{query}"}`,
        "knowledge.commands.viewSource": "Source",
        "knowledge.commands.closePane": "Close pane",
        "knowledge.commands.scanVault": "Scan vault",
        "knowledge.commands.splitRight": "Split pane right",
        "knowledge.commands.requiresActiveTab": "Requires active tab",
        "knowledge.commands.requiresActivePane": "Requires active pane",
        "knowledge.commands.requiresMultiplePanes": "Requires multiple panes",
        "knowledge.commands.requiresSelectedVault": "Requires selected vault",
        "knowledge.commands.requiresFileTree": "Requires file tree",
        "knowledge.commands.requiresLinks": "Requires links",
        "knowledge.commandUnavailable": "Command unavailable",
        "knowledge.knowledgeCommands": "Knowledge commands",
        "knowledge.semanticSearchFor": `Semantic search for ${options?.query ?? ""}`,
        "knowledge.semanticSearchResults": "Semantic results",
        "knowledge.semanticUnavailable": "Semantic search unavailable",
      })[key] ?? key,
  }),
}));
vi.mock("@/lib/hooks/use-knowledge-command-data", () => ({
  useKnowledgeCatalog: () => commandData.catalog,
  useKnowledgeIndexedSearch: () => indexed,
}));
vi.mock("@/lib/hooks/use-vault", () => ({
  useVaults: () => ({ data: [], isLoading: false, isError: false }),
}));

import { CommandPalette } from "./CommandPalette";

function renderPalette() {
  return render(<CommandPalette />);
}

function registerKnowledgeContext(
  options: {
    scanSelectedVault?: () => Promise<void>;
  } = {},
) {
  const activePane = document.createElement("section");
  const fileTree = document.createElement("aside");
  const links = document.createElement("aside");
  document.body.append(activePane, fileTree, links);
  registerKnowledgeCommandContext({
    selectedVaultId: "vault:one",
    activePaneElement: activePane,
    fileTreeElement: fileTree,
    linksElement: links,
    scanSelectedVault:
      options.scanSelectedVault ?? vi.fn(async () => undefined),
  });
  return { activePane, fileTree, links };
}

describe("CommandPalette", () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollIntoView = vi.fn();
    router.push.mockReset();
    Object.values(dialogs).forEach((mock) => mock.mockReset());
    theme.setTheme.mockReset();
    indexed.runSemanticSearch.mockReset();
    commandData.catalog.candidates = [];
    indexed.text = {
      data: { results: [], total_count: 0, search_type: "text" },
      isCurrent: true,
    };
    indexed.semantic = {
      data: undefined,
      variables: undefined,
      isError: false,
      error: null,
    };
    resetCommandSurfaceStore();
    resetKnowledgeCommandContextStore();
    useKnowledgeWorkspaceStore.getState().resetWorkspace();
  });

  it("preserves global palette commands and closes on a second Cmd+K", async () => {
    renderPalette();
    fireEvent.keyDown(document, { key: "k", metaKey: true });

    expect(
      await screen.findByRole("dialog", { name: "Quick actions" }),
    ).toBeVisible();
    expect(screen.getByRole("option", { name: "Sources" })).toBeVisible();
    expect(screen.getByRole("option", { name: "New notebook" })).toBeVisible();
    expect(screen.getByRole("option", { name: "Dark" })).toBeVisible();
    expect(screen.getByRole("option", { name: "Research Core" })).toBeVisible();

    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(screen.queryByRole("dialog", { name: "Quick actions" })).toBeNull();
  });

  it("preserves Cmd+N, Cmd+U, and Cmd+/ global shortcuts", () => {
    renderPalette();
    fireEvent.keyDown(document, { key: "n", metaKey: true });
    fireEvent.keyDown(document, { key: "u", metaKey: true });
    fireEvent.keyDown(document, { key: "/", metaKey: true });

    expect(dialogs.openNotebookDialog).toHaveBeenCalledTimes(1);
    expect(dialogs.openSourceDialog).toHaveBeenCalledTimes(1);
    expect(router.push).toHaveBeenCalledWith("/search");
  });

  it("does not open from editable targets but lets a second Cmd+K close the palette", async () => {
    const input = document.createElement("input");
    const editable = document.createElement("div");
    Object.defineProperty(editable, "isContentEditable", { value: true });
    document.body.append(input, editable);
    renderPalette();

    fireEvent.keyDown(input, { key: "k", metaKey: true });
    fireEvent.keyDown(editable, { key: "k", metaKey: true });
    expect(screen.queryByRole("dialog", { name: "Quick actions" })).toBeNull();

    fireEvent.keyDown(document, { key: "k", metaKey: true });
    expect(
      await screen.findByRole("dialog", { name: "Quick actions" }),
    ).toBeVisible();
    fireEvent.keyDown(screen.getByRole("combobox"), {
      key: "k",
      metaKey: true,
    });
    expect(screen.queryByRole("dialog", { name: "Quick actions" })).toBeNull();
    input.remove();
    editable.remove();
  });

  it("shows only safe Knowledge commands for a slash invocation", async () => {
    const elements = registerKnowledgeContext();
    useKnowledgeWorkspaceStore.getState().openTab({
      vaultId: "vault:one",
      noteId: "note:one",
      title: "One",
      relativePath: "One.md",
    });
    renderPalette();
    act(() => requestCommandSurface("slash", "/"));

    expect(await screen.findByText("Knowledge commands")).toBeVisible();
    expect(await screen.findByRole("option", { name: "Source" })).toBeVisible();
    expect(
      screen.getByRole("option", { name: "Split pane right" }),
    ).toBeVisible();
    expect(screen.queryByRole("option", { name: "Sources" })).toBeNull();
    expect(screen.queryByRole("option", { name: "New notebook" })).toBeNull();
    expect(screen.queryByRole("option", { name: "Dark" })).toBeNull();
    elements.activePane.remove();
    elements.fileTree.remove();
    elements.links.remove();
  });

  it("executes a safe command in the active pane without closing for unavailable context", async () => {
    const elements = registerKnowledgeContext();
    useKnowledgeWorkspaceStore.getState().openTab({
      vaultId: "vault:one",
      noteId: "note:one",
      title: "One",
      relativePath: "One.md",
    });
    renderPalette();
    act(() => requestCommandSurface("slash", "/"));
    fireEvent.click(await screen.findByRole("option", { name: "Source" }));
    await waitFor(() => {
      const workspace = useKnowledgeWorkspaceStore.getState();
      const pane = workspace.panes[workspace.activePaneId];
      expect(
        pane.tabs.find((tab) => tab.id === pane.activeTabId)?.viewMode,
      ).toBe("source");
    });
    elements.activePane.remove();
    elements.fileTree.remove();
    elements.links.remove();
  });

  it("offers semantic search only after explicit selection", async () => {
    registerKnowledgeContext();
    renderPalette();
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    fireEvent.change(await screen.findByRole("combobox"), {
      target: { value: "research" },
    });

    fireEvent.click(
      screen.getByRole("option", { name: "Semantic search for research" }),
    );
    expect(indexed.runSemanticSearch).toHaveBeenCalledTimes(1);
  });

  it("keeps disabled commands visible without closing the palette", async () => {
    registerKnowledgeContext();
    renderPalette();
    act(() => requestCommandSurface("slash", "/"));

    const closePane = await screen.findByRole("option", { name: /Close pane/ });
    expect(closePane).toHaveAttribute("data-disabled", "true");
    fireEvent.click(closePane);
    expect(screen.getByRole("dialog", { name: "Quick actions" })).toBeVisible();
  });

  it("announces a live rejection without closing", async () => {
    const elements = registerKnowledgeContext({
      scanSelectedVault: vi.fn(async () => {
        registerKnowledgeCommandContext({
          selectedVaultId: "vault:one",
          activePaneElement: elements.activePane,
          fileTreeElement: elements.fileTree,
          linksElement: elements.links,
          scanSelectedVault: async () => undefined,
        });
      }),
    });
    renderPalette();
    act(() => requestCommandSurface("slash", "/"));

    fireEvent.click(await screen.findByRole("option", { name: "Scan vault" }));
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Command unavailable",
    );
    expect(screen.getByRole("dialog", { name: "Quick actions" })).toBeVisible();
  });

  it("restores focus to the command invoker after closing", async () => {
    const invoker = document.createElement("button");
    document.body.append(invoker);
    renderPalette();
    act(() => requestCommandSurface("global", "", invoker));
    expect(
      await screen.findByRole("dialog", { name: "Quick actions" }),
    ).toBeVisible();

    fireEvent.keyDown(document, { key: "k", metaKey: true });
    await waitFor(() => expect(invoker).toHaveFocus());
    invoker.remove();
  });

  it("renders exact catalog results before accepted indexed results", async () => {
    registerKnowledgeContext();
    commandData.catalog.candidates = [
      {
        key: "vault:one\0note:exact",
        vaultId: "vault:one",
        noteId: "note:exact",
        vaultName: "Fixture",
        format: "markdown",
        title: "Research exact",
        relativePath: "Research/exact.md",
        isOpen: false,
      },
    ];
    indexed.text = {
      data: {
        results: [
          {
            id: "note:indexed",
            title: "Research indexed",
            parent_id: "parent",
            final_score: 1,
            created: "",
            updated: "",
            vault_provenance: {
              canonical_external: true,
              vault_id: "vault:one",
              relative_path: "Research/indexed.md",
              source_hash: "a".repeat(64),
            },
          },
        ],
        total_count: 1,
        search_type: "text",
      },
      isCurrent: true,
    };
    renderPalette();
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    fireEvent.change(await screen.findByRole("combobox"), {
      target: { value: "research" },
    });

    const exact = await screen.findByRole("option", { name: "Research exact" });
    const indexedResult = screen.getByRole("option", {
      name: "Research indexed",
    });
    expect(
      exact.compareDocumentPosition(indexedResult) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("routes no-provenance text and semantic results to Search and omits invalid provenance", async () => {
    registerKnowledgeContext();
    const invalid = {
      id: "note:invalid",
      title: "Unsafe result",
      parent_id: "parent",
      final_score: 1,
      created: "",
      updated: "",
      vault_provenance: {
        canonical_external: true,
        vault_id: "vault:one",
        relative_path: "/unsafe.md",
        source_hash: "not-a-hash",
      },
    };
    const noProvenance = {
      id: "result:search",
      title: "Research result",
      parent_id: "parent",
      final_score: 1,
      created: "",
      updated: "",
    };
    indexed.text = {
      data: {
        results: [invalid, noProvenance],
        total_count: 2,
        search_type: "text",
      },
      isCurrent: true,
    };
    indexed.semantic = {
      data: {
        results: [invalid, noProvenance],
        total_count: 2,
        search_type: "vector",
      },
      variables: "research",
      isError: false,
      error: null,
    };
    renderPalette();
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    fireEvent.change(await screen.findByRole("combobox"), {
      target: { value: "research" },
    });

    expect(
      await screen.findAllByRole("option", { name: "Research result" }),
    ).toHaveLength(2);
    expect(screen.queryByRole("option", { name: "Unsafe result" })).toBeNull();
    fireEvent.click(
      screen.getAllByRole("option", { name: "Research result" })[1],
    );
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith(
        "/search?q=research&mode=search",
      ),
    );
  });

  it("suppresses stale semantic results and routes embedding errors to model settings", async () => {
    registerKnowledgeContext();
    indexed.semantic = {
      data: {
        results: [
          {
            id: "note:stale",
            title: "Stale semantic",
            parent_id: "parent",
            final_score: 1,
            created: "",
            updated: "",
          },
        ],
        total_count: 1,
        search_type: "vector",
      },
      variables: "older query",
      isError: true,
      error: new Error("Vector search requires an embedding model"),
    };
    renderPalette();
    fireEvent.keyDown(document, { key: "k", metaKey: true });
    fireEvent.change(await screen.findByRole("combobox"), {
      target: { value: "research" },
    });

    expect(screen.queryByRole("option", { name: "Stale semantic" })).toBeNull();
    fireEvent.click(
      screen.getByRole("option", { name: "Semantic search unavailable" }),
    );
    await waitFor(() =>
      expect(router.push).toHaveBeenCalledWith("/settings/api-keys"),
    );
  });

  it("keeps the palette open when a command rejects", async () => {
    registerKnowledgeContext({
      scanSelectedVault: vi.fn(async () => {
        throw new Error("scan failed");
      }),
    });
    renderPalette();
    act(() => requestCommandSurface("slash", "/"));

    fireEvent.click(await screen.findByRole("option", { name: "Scan vault" }));
    expect(screen.getByRole("dialog", { name: "Quick actions" })).toBeVisible();
  });

  it("closes after a successful scan without announcing unavailable", async () => {
    const scanSelectedVault = vi.fn(async () => undefined);
    registerKnowledgeContext({ scanSelectedVault });
    renderPalette();
    act(() => requestCommandSurface("slash", "/"));

    fireEvent.click(await screen.findByRole("option", { name: "Scan vault" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Quick actions" }),
      ).toBeNull(),
    );
    expect(scanSelectedVault).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("status")).toBeNull();
  });
});
