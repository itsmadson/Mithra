import { chromium } from "playwright";
import { execSync } from "child_process";

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1400, height: 900 } });
const p = await ctx.newPage();
p.on("requestfailed", (r) => console.log("  FAILED:", r.url().slice(30, 100), r.failure()?.errorText));

await p.goto("http://localhost:3100/fa/login", { waitUntil: "networkidle" });
await p.getByLabel("رایانامه").fill("e2e@example.com");
await p.getByLabel("گذرواژه").fill("a-long-enough-password");
await p.getByRole("button", { name: "ورود" }).click();
await p.waitForURL(/\/fa$/, { timeout: 20000 });
await p.waitForTimeout(2000);
console.log("tab is open on the current build");

// Rebuild + restart, exactly what I have been doing between checks.
console.log("rebuilding server under the open tab...");
execSync("cd /home/madson/bina/apps/web && NEXT_PUBLIC_API_URL=http://localhost:8020 npm run build > /dev/null 2>&1");
execSync("pkill -f next-server || true");
execSync("sleep 2");
execSync("cd /home/madson/bina/apps/web && PORT=3100 NEXT_PUBLIC_API_URL=http://localhost:8020 nohup npm run start > /tmp/w.log 2>&1 & sleep 10");
console.log("server restarted with a new build id");

// Now click, from the stale tab.
await p.getByRole("navigation").getByRole("link", { name: "تابلوها" }).click();
for (const t of [2000, 5000, 9000]) {
  await p.waitForTimeout(t === 2000 ? 2000 : 3000);
  const txt = (await p.locator("body").innerText()).replace(/\n/g," | ");
  console.log(`  +${t}ms url=${p.url().replace("http://localhost:3100","")} :: ${txt.slice(55, 125)}`);
}
await b.close();
