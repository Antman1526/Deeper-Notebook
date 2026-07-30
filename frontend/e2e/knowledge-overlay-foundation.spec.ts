import { expect, test } from "@playwright/test";

import {
  installStrictKnowledgeFixture,
  openExternalEvidenceNote,
} from "./fixtures/knowledge-editor-modes";

test.describe("knowledge overlay foundation", () => {
  test("creates and edits owned notes without touching external vaults", async ({
    page,
  }) => {
    const fixture = await installStrictKnowledgeFixture(page);
    await page.goto("/knowledge");

    await page.getByRole("button", { name: "Today", exact: true }).click();
    await expect(
      page.getByText("Writable app-owned note").last(),
    ).toBeVisible();
    await page
      .getByRole("textbox", { name: /source/i })
      .fill("# Today\n\nDraft");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page.getByText("Revision 2")).toBeVisible();

    await page.getByRole("button", { name: "New unique note" }).click();
    await page.getByLabel("Unique note title").fill("Research Idea");
    await page.getByRole("button", { name: "Create note" }).click();
    await expect(
      page.getByRole("tab", { name: "Research Idea" }),
    ).toBeVisible();
    expect(
      fixture.overlayNotes.map((note) => note.relative_path),
    ).toContainEqual(
      expect.stringMatching(/^Unique\/\d{8}-\d{4} Research Idea\.md$/),
    );

    await openExternalEvidenceNote(page);
    await expect(
      page.getByText("Read-only external file").last(),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Save", exact: true }),
    ).toHaveCount(0);

    expect(fixture.externalMutationRequests).toEqual([]);
    expect(fixture.externalFingerprintsAfter).toEqual(
      fixture.externalFingerprintsBefore,
    );
    expect(fixture.unexpectedRequests).toEqual([]);
  });

  test("replays daily notes, resolves collisions, preserves conflicts, hydrates restart, and restores focus", async ({
    page,
  }) => {
    const fixture = await installStrictKnowledgeFixture(page);
    await page.goto("/knowledge");

    const today = page.getByRole("button", { name: "Today", exact: true });
    await today.click();
    await today.click();
    expect(fixture.dailyRequests).toHaveLength(2);
    expect(
      fixture.overlayNotes.filter((note) => note.kind === "daily"),
    ).toHaveLength(1);

    for (let attempt = 0; attempt < 2; attempt += 1) {
      await page.getByRole("button", { name: "New unique note" }).click();
      await page.getByLabel("Unique note title").fill("Collision Proof");
      await page.getByRole("button", { name: "Create note" }).click();
    }
    const collisionPaths = fixture.overlayNotes
      .filter((note) => note.title === "Collision Proof")
      .map((note) => note.relative_path);
    expect(collisionPaths).toEqual([
      expect.stringMatching(/^Unique\/\d{8}-\d{4} Collision Proof\.md$/),
      expect.stringMatching(/^Unique\/\d{8}-\d{4} Collision Proof-2\.md$/),
    ]);

    const source = page.getByRole("textbox", {
      name: "Collision Proof source",
    });
    await source.fill("# Collision Proof\n\nLocal draft survives");
    fixture.injectNextSaveConflict();
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(
      page.getByText("This note changed elsewhere. Your draft is still safe."),
    ).toBeVisible();
    await expect(source).toContainText("Local draft survives");

    const review = page.getByRole("button", { name: "Review server version" });
    await review.click();
    await page.getByRole("button", { name: "Cancel", exact: true }).click();
    await expect(review).toBeFocused();

    await expect
      .poll(() => JSON.stringify(fixture.state.workspace))
      .toContain('"source_authority":"overlay"');
    await page.reload();
    await expect(
      page.locator(
        '[role="tab"][aria-label="Collision Proof"][title$="Collision Proof-2.md"]',
      ),
    ).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Revision 2")).toBeVisible();

    expect(fixture.externalMutationRequests).toEqual([]);
    expect(fixture.externalFingerprintsAfter).toEqual(
      fixture.externalFingerprintsBefore,
    );
    expect(fixture.unexpectedRequests).toEqual([]);
  });
});
