async page => {
  // Read-only and intentionally narrow. Never click, navigate, mutate, or
  // return a full page snapshot/account details.
  const marker = "DUO_CARE_INSPECT=";
  const safe = (status, controls = []) => marker + JSON.stringify({status, controls});
  try {
    const url = new URL(page.url());
    if (url.hostname !== "apple.com" && !url.hostname.endsWith(".apple.com")) {
      return safe("not_on_apple");
    }
    const controls = await page.evaluate(() => {
      const matcher = /applecare|no coverage|without coverage|no thanks|decline (?:coverage|applecare)|protection plan/i;
      const candidates = [...document.querySelectorAll(
        'button, input[type="radio"], input[type="checkbox"], label, [role="button"], [role="radio"], [role="checkbox"], [role="option"], h1, h2, h3, h4, legend'
      )];
      const seen = new Set();
      const found = [];
      for (const el of candidates.slice(0, 1500)) {
        if (!el.getClientRects().length) continue;
        const role = el.getAttribute("role") || el.tagName.toLowerCase();
        const pieces = [
          el.getAttribute("aria-label"), el.getAttribute("title"),
          el.tagName.toLowerCase() === "input" ? (el.labels?.[0]?.innerText || "") : "",
          el.innerText
        ];
        const label = pieces.filter(Boolean).join(" ").replace(/\s+/g," ").trim();
        if (!matcher.test(label) || !label) continue;
        // Privacy: keep only strictly relevant short control texts; never full page.
        if (label.length > 140) continue;
        const scrub = label.replace(/[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}/g,"[email]")
                           .replace(/(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g,"[phone]");
        const key = role + ":" + scrub;
        if (seen.has(key)) continue;
        seen.add(key);
        found.push({role, label: scrub, disabled: el.matches(':disabled, [aria-disabled="true"]')});
        if (found.length >= 20) break;
      }
      return found;
    });
    return safe(controls.length ? "controls_found" : "no_visible_care_controls", controls);
  } catch (err) {
    return safe("inspection_failed");
  }
}