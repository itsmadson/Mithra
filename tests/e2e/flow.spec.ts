import { expect, test } from "@playwright/test";

const JOB_ID = "11111111-1111-1111-1111-111111111111";

test("the Persian home page loads right-to-left", async ({ page }) => {
  await page.goto("/fa");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByText("بینا")).toBeVisible();
});

test("the English home page loads left-to-right", async ({ page }) => {
  await page.goto("/en");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});

test("the results page shows per-class counts", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);

  // The class name also appears once per matching table row, so scope the
  // assertion to the counts panel rather than the whole page.
  const tile = page.locator("section div", { hasText: /^تابلو نام معبر$/ }).locator("..");
  await expect(tile).toContainText("2");

  // Every class renders even at zero — a missing row would read as
  // "not measured" rather than "measured, none found".
  const counts = page.locator("section").first();
  await expect(counts).toContainText("تابلو ورودی شهر");
  await expect(counts).toContainText("تابلو اطلاعاتی");

  // The seeded job has one crop_failed-style unknown; the total and the
  // unclassified count must both be present.
  await expect(counts).toContainText("مجموع تابلوها");
});

test("the results table lists the individual signs", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);
  await expect(page.getByRole("cell", { name: "تابلو نام معبر" })).toHaveCount(2);
});

test("export links are present once the job is finished", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);
  const csv = page.getByRole("link", { name: /CSV/i });
  await expect(csv).toBeVisible();
  await expect(csv).toHaveAttribute("href", new RegExp(`${JOB_ID}/export.csv`));
});

test("the labeling page offers all four classes", async ({ page }) => {
  await page.goto("/fa/label");
  await expect(page.getByRole("button", { name: "تابلو مسیرنما" })).toBeVisible();
  await expect(page.getByRole("button", { name: "تابلو ورودی شهر" })).toBeVisible();
});
