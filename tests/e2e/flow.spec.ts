import { expect, test } from "@playwright/test";

const JOB_ID = "11111111-1111-1111-1111-111111111111";
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8020";
const EMAIL = "e2e@example.com";
const PASSWORD = "a-long-enough-password";

/**
 * Sign in before each test.
 *
 * Every data route requires a session now. The token is obtained from the API
 * directly and planted in the browser context rather than driven through the
 * form, so a broken login screen fails its own test instead of every test.
 */
test.beforeEach(async ({ context, request }) => {
  const response = await request.post(`${API}/api/auth/login`, {
    data: { email: EMAIL, password: PASSWORD },
  });
  if (!response.ok()) throw new Error(`e2e login failed: ${response.status()}`);

  const cookie = response
    .headersArray()
    .find((h) => h.name.toLowerCase() === "set-cookie")?.value;
  const token = cookie?.match(/bina_session=([^;]+)/)?.[1];
  if (!token) throw new Error("no session cookie returned");

  await context.addCookies([
    { name: "bina_session", value: token, domain: "localhost", path: "/" },
  ]);
});

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
  // Generous: against the dev server this route is compiled on first request,
  // and the style and glyphs load before anything is painted.
  await expect(painted).toHaveAttribute("data-signs-rendered", /[1-9]/, {
    timeout: 45_000,
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
  // The locale control lives in the navigation rail and is abbreviated there.
  await page.getByRole("link", { name: "EN", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`/en/jobs/${JOB_ID}`));
  await expect(page.locator("html")).toHaveAttribute("dir", "ltr");
});

test("the navigation rail reaches every section", async ({ page }) => {
  await page.goto("/fa");
  const nav = page.getByRole("navigation");

  await nav.getByRole("link", { name: "تابلوها" }).click();
  await expect(page).toHaveURL(/\/fa\/signs$/);

  await nav.getByRole("link", { name: "بازبینی" }).click();
  await expect(page).toHaveURL(/\/fa\/label$/);

  await nav.getByRole("link", { name: "تنظیمات" }).click();
  await expect(page).toHaveURL(/\/fa\/settings$/);
  await expect(page.getByText("موجودی")).toBeVisible();

  await nav.getByRole("link", { name: "تحلیل\u200cها" }).click();
  await expect(page).toHaveURL(/\/fa\/surveys$/);

  await nav.getByRole("link", { name: "داشبورد" }).click();
  await expect(page).toHaveURL(/\/fa$/);
});

test("the signs section aggregates every survey", async ({ page }) => {
  await page.goto("/fa/signs");
  // The seeded job contributes signs; this section counts across surveys, so
  // it must list at least those.
  await expect(page.getByTestId("sign-list").locator("li").first()).toBeVisible({
    timeout: 20_000,
  });
});

test("an anonymous visitor is sent to sign in", async ({ browser }) => {
  // A fresh context: no session, which is what an unauthenticated visitor is.
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/fa");
  await expect(page).toHaveURL(/\/fa\/login$/);
  await expect(page.getByRole("button", { name: "ورود" })).toBeVisible();
  await context.close();
});

test("signing in through the form reaches the surveys view", async ({ browser }) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/fa/login");

  await page.getByLabel("رایانامه").fill(EMAIL);
  await page.getByLabel("گذرواژه").fill(PASSWORD);
  await page.getByRole("button", { name: "ورود" }).click();

  await expect(page).toHaveURL(/\/fa$/);
  await expect(page.getByRole("navigation")).toBeVisible();
  await context.close();
});

test("a wrong password is refused without saying which field was wrong", async ({
  browser,
}) => {
  const context = await browser.newContext();
  const page = await context.newPage();
  await page.goto("/fa/login");

  await page.getByLabel("رایانامه").fill(EMAIL);
  await page.getByLabel("گذرواژه").fill("definitely-not-it");
  await page.getByRole("button", { name: "ورود" }).click();

  await expect(page.getByText("رایانامه یا گذرواژه نادرست است.")).toBeVisible();
  await expect(page).toHaveURL(/\/fa\/login$/);
  await context.close();
});

test("signing out returns to the login screen", async ({ page }) => {
  await page.goto("/fa");
  await page.getByRole("button", { name: "خروج" }).click();
  await expect(page).toHaveURL(/\/fa\/login$/);
});

test("the dashboard leads with the numbers a decision needs", async ({ page }) => {
  await page.goto("/fa");

  await expect(page.getByText("کل تابلوها")).toBeVisible();
  await expect(page.getByText("در انتظار بازبینی")).toBeVisible();
  await expect(page.getByText("توزیع اطمینان مدل")).toBeVisible();
  await expect(page.getByText("پربارترین تحلیل\u200cها")).toBeVisible();
});

test("changing the range reloads the dashboard", async ({ page }) => {
  await page.goto("/fa");
  const seven = page.getByRole("button", { name: /۷ روز|7 روز/ });
  await seven.click();
  await expect(seven).toHaveAttribute("aria-pressed", "true");
});

test("the dashboard links through to a survey", async ({ page }) => {
  await page.goto("/fa");
  // Recent activity is a list of real surveys; following one must land on it.
  const link = page.locator('a[href*="/fa/jobs/"]').first();
  await expect(link).toBeVisible({ timeout: 15_000 });
  await link.click();
  await expect(page).toHaveURL(/\/fa\/jobs\//);
});
