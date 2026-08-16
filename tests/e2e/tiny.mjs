import { chromium } from "@playwright/test";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1440, height: 950 } });
await p.goto("http://localhost:3100/fa/login", { waitUntil: "networkidle" });
await p.fill('input[type="email"]', "e2e@example.com");
await p.fill('input[type="password"]', "inventory-test-password");
await p.click('button[type="submit"]');
await p.waitForTimeout(2000);
await p.goto("http://localhost:3100/fa/detect", { waitUntil: "networkidle" });
await p.waitForTimeout(2200);
const out = await p.evaluate(() => {
  const m = {};
  for (const e of document.querySelectorAll("*")) {
    if (!e.textContent?.trim() || e.children.length) continue;
    const s = getComputedStyle(e);
    const fs = Math.round(parseFloat(s.fontSize) * 10) / 10;
    if (fs < 11.5) {
      const k = `${fs}px "${e.textContent.trim().slice(0, 22)}"`;
      m[k] = (m[k] || 0) + 1;
    }
  }
  return Object.entries(m).sort((a,b)=>b[1]-a[1]).slice(0, 8);
});
console.log(out.map(([k, n]) => `${n}x  ${k}`).join("\n"));
await b.close();
