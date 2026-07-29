import { expect, test } from "@playwright/test";

import {
  initialKnowledgeFixtureState,
  installKnowledgeRoutes,
  installKnowledgeShellMocks,
} from "./fixtures/knowledge-editor-modes";

const modifier = process.platform === "darwin" ? "Meta" : "Control";

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
    await switcher.getByRole("option", { name: /evidence/iu }).click();
    await expect(page.getByRole("tab", { name: "evidence" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    await page.getByTestId("knowledge-workspace").focus();
    await page.keyboard.press("/");
    const palette = page.getByRole("dialog", { name: "Quick actions" });
    await expect(palette.getByRole("option", { name: "Source" })).toBeVisible();
    await expect(
      palette.getByText(/delete|rename|move|toggle task/iu),
    ).toHaveCount(0);
    await palette.getByRole("option", { name: "Source" }).click();
    await expect(
      page
        .getByTestId("knowledge-workspace")
        .getByRole("button", { name: "Source", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");

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
    expect(vaultWrites).toEqual([]);
    expect(unexpectedApiTraffic).toEqual([]);
  });
});
