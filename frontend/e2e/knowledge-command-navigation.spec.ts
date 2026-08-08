import { expect, test } from "@playwright/test";

import {
  initialKnowledgeFixtureState,
  installKnowledgeRoutes,
  installKnowledgeShellMocks,
} from "./fixtures/knowledge-editor-modes";

const modifier = process.platform === "darwin" ? "Meta" : "Control";

function persistedActiveTab(state: ReturnType<typeof initialKnowledgeFixtureState>) {
  const workspace = state.workspace as {
    panes?: Record<string, { active_tab_id?: string | null; tabs?: Array<Record<string, unknown>> }>;
  };
  const pane = workspace.panes?.["pane-1"];
  return pane?.tabs?.find((tab) => tab.id === pane.active_tab_id);
}

test.describe("knowledge command navigation", () => {
  test("quick switcher and slash commands preserve the external vault", async ({
    page,
  }) => {
    const state = initialKnowledgeFixtureState();
    const vaultWrites: string[] = [];
    const unexpectedApiTraffic: string[] = [];

    await installKnowledgeShellMocks(page, unexpectedApiTraffic);
    await installKnowledgeRoutes(
      page,
      state,
      vaultWrites,
      unexpectedApiTraffic,
    );
    await page.goto("/knowledge");
    await expect(page.getByTestId("knowledge-workspace")).toBeVisible();
    await page.getByTestId("knowledge-workspace").focus();
    await page.keyboard.press(`${modifier}+o`);
    const switcher = page.getByRole("dialog", { name: "Quick switcher" });
    await expect(switcher).toBeVisible();
    await switcher.getByRole("combobox").fill("evidence");
    await switcher
      .getByRole("option", { name: "evidence pages/evidence.md · Fixture vault", exact: true })
      .click();
    await expect(page.getByRole("tab", { name: "Read: Evidence", exact: true })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect.poll(() => persistedActiveTab(state)).toMatchObject({
      mode: "read",
      title: "Evidence",
      target: {
        kind: "document",
        container_id: "vault:fixture",
        note_id: "note:evidence",
        relative_locator: "pages/evidence.md",
        authority: "external-vault",
        knowledge_document_id: "knowledge_engine_document:evidence",
        render_mode: "reading",
      },
    });
    await expect(
      page.getByLabel("Evidence reading view").getByRole("heading", { name: "Evidence", exact: true }),
    ).toBeVisible();

    await page.getByTestId("knowledge-workspace").focus();
    await page.keyboard.press("/");
    const palette = page.getByRole("dialog", { name: "Quick actions" });
    await expect(
      palette.locator('[role="option"][data-value^="knowledge.commands.viewSource "]'),
    ).toBeVisible();
    await expect(
      palette.getByText(/delete|rename|move|toggle task/iu),
    ).toHaveCount(0);
    const sourceOption = palette.locator(
      '[role="option"][data-value^="knowledge.commands.viewSource "]',
    );
    await expect(sourceOption).toBeVisible();
    await page.keyboard.press("Escape");
    await page
      .getByRole("toolbar", { name: /Knowledge pane/ })
      .getByRole("button", { name: "Source", exact: true })
      .click();
    await expect(
      page
        .getByRole("toolbar", { name: /Knowledge pane/ })
        .getByRole("button", { name: "Source", exact: true }),
    ).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(
      page.getByLabel("Canonical file metadata").getByText("pages/evidence.md", { exact: true }),
    ).toBeVisible();

    expect(vaultWrites).toEqual([]);
    expect(unexpectedApiTraffic).toEqual([]);
  });

  test("text and semantic search remain distinct and provenance-bound", async ({
    page,
  }) => {
    const state = initialKnowledgeFixtureState();
    const vaultWrites: string[] = [];
    const unexpectedApiTraffic: string[] = [];

    await installKnowledgeShellMocks(page, unexpectedApiTraffic);
    await installKnowledgeRoutes(
      page,
      state,
      vaultWrites,
      unexpectedApiTraffic,
    );
    await page.goto("/knowledge");
    await expect(page.getByTestId("knowledge-workspace")).toBeVisible();
    await page.getByTestId("knowledge-workspace").focus();
    await page.keyboard.press(`${modifier}+k`);
    await page
      .getByRole("dialog", { name: "Quick actions" })
      .getByRole("combobox")
      .fill("plan");
    await expect.poll(() => state.searchRequests.length).toBe(1);
    expect(state.searchRequests[0]).toMatchObject({
      query: "plan",
      type: "text",
      search_notes: true,
      search_sources: false,
    });
    await expect(page.getByText("Indexed results", { exact: true })).toBeVisible();
    const planResults = page.getByRole("option", { name: "Plan", exact: true });
    await planResults.last().click();
    await expect.poll(() => persistedActiveTab(state)).toMatchObject({
      mode: "read",
      title: "Plan",
      target: {
        kind: "document",
        container_id: "vault:fixture",
        note_id: "note:plan",
        relative_locator: "pages/plan.md",
        authority: "external-vault",
        knowledge_document_id: "knowledge_engine_document:plan",
        render_mode: "reading",
      },
    });
    await expect(
      page.getByLabel("Plan reading view").getByRole("heading", { name: "Plan", exact: true }),
    ).toBeVisible();

    await page.getByTestId("knowledge-workspace").focus();
    await page.keyboard.press(`${modifier}+k`);
    await page
      .getByRole("dialog", { name: "Quick actions" })
      .getByRole("combobox")
      .fill("plan");

    await page
      .getByRole("option", { name: "Semantic search for plan" })
      .click();
    await expect.poll(() => state.searchRequests.length).toBe(2);
    expect(state.searchRequests[1]).toMatchObject({
      query: "plan",
      type: "vector",
      search_notes: true,
      search_sources: false,
    });
    await expect(page.getByText("Semantic results", { exact: true })).toBeVisible();
    await planResults.last().click();
    await expect.poll(() => persistedActiveTab(state)).toMatchObject({
      mode: "read",
      title: "Plan",
      target: {
        kind: "document",
        container_id: "vault:fixture",
        note_id: "note:plan",
        relative_locator: "pages/plan.md",
        authority: "external-vault",
        knowledge_document_id: "knowledge_engine_document:plan",
        render_mode: "reading",
      },
    });
    await expect(
      page.getByLabel("Plan reading view").getByRole("heading", { name: "Plan", exact: true }),
    ).toBeVisible();
    expect(vaultWrites).toEqual([]);
    expect(unexpectedApiTraffic).toEqual([]);
  });
});
