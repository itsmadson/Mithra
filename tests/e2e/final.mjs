import { chromium } from "@playwright/test";
const S = "/tmp/claude-1000/-home-madson-bina/0d4e4ab4-16f9-4d30-aa87-ceaf8555f442/scratchpad";
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 } });
const p = await ctx.newPage();
const errs = [];
p.on("pageerror", (e) => errs.push("pageerror " + e));
p.on("console", (m) => m.type() === "error" && errs.push("console " + m.text()));
await p.goto("http://localhost:3100/en/login", { waitUntil: "networkidle" });
await p.fill('input[type="email"]', "e2e@example.com");
await p.fill('input[type="password"]', "inventory-test-password");
await p.click('button[type="submit"]');
await p.waitForTimeout(2500);

const pages = [["", "home"], ["/inventory", "inv"], ["/detect", "detect"], ["/surveys", "surveys"], ["/label", "review"], ["/audit", "audit"], ["/settings", "settings"]];
const report = [];
for (const [path, name] of pages) {
  await p.goto(`http://localhost:3100/en${path}`, { waitUntil: "networkidle" });
  await p.waitForTimeout(1800);
  const m = await p.evaluate(() => ({
    hOverflow: document.body.scrollWidth > window.innerWidth + 1,
    tinyText: [...document.querySelectorAll("*")].filter(e => {
      const s = getComputedStyle(e); const fs = parseFloat(s.fontSize);
      return e.textContent?.trim() && e.children.length === 0 && fs > 0 && fs < 10.5;
    }).length,
    untranslated: (document.body.innerText.match(/\b[a-z_]+_[a-z_]+\b/g) || []).slice(0, 4),
  }));
  report.push([name, m]);
  await p.screenshot({ path: `${S}/f-${name}.png` });
}
// narrow
await p.setViewportSize({ width: 820, height: 900 });
for (const [path, name] of [["/inventory", "inv"], ["", "home"]]) {
  await p.goto(`http://localhost:3100/en${path}`, { waitUntil: "networkidle" });
  await p.waitForTimeout(1800);
  const o = await p.evaluate(() => document.body.scrollWidth > window.innerWidth + 1);
  report.push([name + "@820", { hOverflow: o }]);
  await p.screenshot({ path: `${S}/f-${name}-narrow.png` });
}
console.log(report.map(([n, m]) => `${n.padEnd(12)} overflow=${m.hOverflow} tiny=${m.tinyText ?? "-"} keys=${JSON.stringify(m.untranslated ?? [])}`).join("\n"));
console.log(errs.length ? "\nERRORS:\n" + [...new Set(errs)].slice(0, 6).join("\n") : "\nno console errors");
await b.close();
