import { expect, test } from "@playwright/test";

const JOB_ID = "11111111-1111-1111-1111-111111111111";

test("the Persian home page loads right-to-left", async ({ page }) => {
  await page.goto("/fa");
  await expect(page.locator("html")).toHaveAttribute("dir", "rtl");
  await expect(page.getByText("بینا").first()).toBeVisible();
});

test("the English home page loads left-to-right", async ({ page }) => {
  await page.goto("/en");
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});

test("the results page shows every class with its count", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);

  // Each class is a filter row carrying its own count. Every class renders even
  // at zero: a missing row would read as "not measured" rather than
  // "measured, none found".
  const filters = page.getByTestId("class-filter");
  const street = filters.getByRole("button", { name: /تابلو نام معبر/ });
  await expect(street).toContainText("2");
  await expect(filters.getByRole("button", { name: /تابلو ورودی شهر/ })).toBeVisible();
  await expect(filters.getByRole("button", { name: /نامشخص/ })).toBeVisible();
});

test("the sign list shows one row per detected sign", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);
  await expect(page.getByTestId("sign-list").locator("li")).toHaveCount(4);
});

test("selecting a sign opens its detection evidence", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);
  await page.getByTestId("sign-list").locator("button").first().click();

  // The provenance panel is the whole point: which image, which model, where.
  await expect(page.getByText("مستندات تشخیص")).toBeVisible();
  await expect(page.getByText("شناسهٔ تصویر منبع")).toBeVisible();
  await expect(page.getByText("نسخهٔ مدل")).toBeVisible();
});

test("export links are present once the job is finished", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);
  const csv = page.getByRole("link", { name: /CSV/i });
  await expect(csv).toBeVisible();
  await expect(csv).toHaveAttribute("href", new RegExp(`${JOB_ID}/export.csv`));
  await expect(page.getByRole("link", { name: /GeoJSON/i })).toBeVisible();
});

test("signs are plotted on the map as vector features", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);

  // Signs render from a GeoJSON source through vector layers, so there is no
  // DOM node per sign. The map publishes how many features it actually
  // painted, which is stronger than asserting the source holds them.
  const painted = page.locator("[data-signs-rendered]");
  await expect(painted).toHaveAttribute("data-signs-rendered", /[1-9]/, {
    timeout: 25_000,
  });
});

test("class filters hide and show signs", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);
  await expect(page.getByTestId("sign-list").locator("li")).toHaveCount(4);
  await page.getByTestId("class-filter").getByRole("button", { name: /تابلو نام معبر/ }).click();
  await expect(page.getByTestId("sign-list").locator("li")).toHaveCount(2);
});

test("the labeling page offers all four classes", async ({ page }) => {
  await page.goto("/fa/label");
  await expect(page.getByRole("button", { name: /تابلو مسیرنما/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /تابلو ورودی شهر/ })).toBeVisible();
});

test("the locale switch keeps you on the same job", async ({ page }) => {
  await page.goto(`/fa/jobs/${JOB_ID}`);
  await page.getByRole("link", { name: "English" }).click();
  await expect(page).toHaveURL(new RegExp(`/en/jobs/${JOB_ID}`));
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});
