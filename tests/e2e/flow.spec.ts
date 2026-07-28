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
  await expect(page.getByText("تابلو نام معبر")).toBeVisible();
  await expect(page.getByText("2", { exact: true }).first()).toBeVisible();
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
