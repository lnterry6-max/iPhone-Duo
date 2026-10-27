async page => {
  // Runs ONLY in the existing Chrome extension session, on the user's Mac.
  // Parameters are inserted locally by checkout_bot.py (no passwords/cookies).
  const cfg = __DUO_CONFIG_JSON__;
  let stage = 'start';
  let clickedOrderButton = false;
  const result = obj => 'DUO_AUTOMATION_RESULT=' + JSON.stringify(obj);
  const fail = code => result({status: 'stopped', stage, code, clickedOrderButton});
  const allowedUrls = {
    'MK1E4LL/A': 'https://www.apple.com/shop/buy-iphone/iphone-duo/7.6-inch-display-256gb-star-white-unlocked',
    'MK1F4LL/A': 'https://www.apple.com/shop/buy-iphone/iphone-duo/7.6-inch-display-256gb-night-sky-unlocked'
  };
  const allowedStores = [
    'The Shops at Blackstone Valley', 'Natick', 'Boylston Street', 'Chestnut Hill', 'Legacy Place'
  ];
  const appleHost = url => {
    try {
      const name = new URL(url).hostname;
      return name === 'apple.com' || name.endsWith('.apple.com');
    } catch { return false; }
  };
  const stopOnChallenge = async () => {
    if (!appleHost(page.url())) throw Error('outside_apple');
    const text = (await page.locator('body').innerText({timeout: 3500})).toLowerCase();
    if (/captcha|verify (?:you.?re|that you are) (?:a )?human|unusual traffic|robot check|bot verification/.test(text)) {
      throw Error('human_verification_required');
    }
  };
  const clickUnique = async (patterns, types=['button']) => {
    for (const name of patterns) {
      for (const type of types) {
        const e = page.getByRole(type, {name});
        if (await e.count() === 1 && await e.isVisible() && await e.isEnabled()) {
          await e.click({timeout: 4500});
          await stopOnChallenge();
          return true;
        }
      }
    }
    return false;
  };
  const requireClick = async (patterns, types=['button']) => {
    if (!await clickUnique(patterns, types)) throw Error('expected_control_missing');
  };
  const chooseNoAppleCare = async () => {
    // Based on the actual read-only Chrome inspection: Apple's visible label
    // is "No AppleCare coverage", with an associated input. This is deliberately
    // strict: never click an offered paid AppleCare+ or AppleCare One plan.
    const withoutCare = /^\s*No AppleCare(?:\+)? coverage\s*$/i;
    const labels = page.locator('label').filter({hasText: withoutCare});
    const radios = page.getByRole('radio', {name: withoutCare});
    // Apple's product page can render the insurance section after DOMContentLoaded.
    // Give it at most twelve seconds, but never guess a different choice.
    for (let attempt = 0; attempt < 24; attempt++) {
      await stopOnChallenge();
      if (await labels.count() === 1 && await labels.isVisible()) {
        const label = labels;
        const selectedBefore = await label.evaluate(node => {
          const control = node.control || node.querySelector('input[type="radio"], input[type="checkbox"]');
          return !!control && control.checked === true;
        });
        if (!selectedBefore) await label.click({timeout:4500});
        await stopOnChallenge();
        const selectedAfter = await label.evaluate(node => {
          const control = node.control || node.querySelector('input[type="radio"], input[type="checkbox"]');
          return !!control && control.checked === true;
        });
        if (!selectedAfter) throw Error('no_applecare_selection_unverified');
        return true;
      }
      // Accessible-radio fallback for a different but still semantically
      // correct Apple control; verify its checked state after selection.
      if (await radios.count() === 1 && await radios.isVisible()) {
        const radio = radios;
        if (!await radio.isChecked()) await radio.check({timeout:4500});
        await stopOnChallenge();
        if (!await radio.isChecked()) throw Error('no_applecare_selection_unverified');
        return true;
      }
      await page.waitForTimeout(500);
    }
    return false;
  };
  const findReview = async () => {
    const candidates = [
      '[data-autom="order-summary"]', '[data-testid="order-summary"]',
      '#order-summary', '.rs-order-summary', '[aria-label="Order Summary"]'
    ];
    for (const selector of candidates) {
      const element = page.locator(selector);
      if (await element.count() === 1 && await element.isVisible()) {
        return await element.innerText({timeout: 4000});
      }
    }
    throw Error('final_review_missing');
  };
  const validateSummary = text => {
    const s = text.replace(/\s+/g, ' ').toLowerCase();
    const color = cfg.sku === 'MK1E4LL/A' ? 'star white' : 'night sky';
    for (const required of ['iphone duo', '256gb', color, cfg.store.toLowerCase(), 'pick up']) {
      if (!s.includes(required)) throw Error('order_mismatch');
    }
    if (/512gb|1tb|2tb/.test(s)) throw Error('wrong_storage');
    // Only accept a final order summary explicitly documenting no extra
    // AppleCare coverage; never mistake a paid line for a harmless upsell.
    if (!/no applecare(?:\+)? coverage/.test(s)) throw Error('no_applecare_not_verified');
    if (/applecare\s*(?:\+|one).*?(?:\$\s*\d|per month|monthly|annual)/i.test(s)) {
      throw Error('unexpected_applecare');
    }
    if (!/(?:quantity|qty)\s*:?\s*1\b/.test(s)) throw Error('quantity_not_proven');
    if (/(?:quantity|qty)\s*:?\s*[2-9]/.test(s)) throw Error('wrong_quantity');
    if (!/\b(?:oct(?:ober)?\.?\s+27(?:,?\s+2026)?|10\/27(?:\/2026)?|2026-10-27)\b/.test(s)) throw Error('wrong_pickup_date');
    if (!/\b(?:pick\s*up|pickup)\b/.test(s)) throw Error('not_pickup');
    const hours = [...s.matchAll(/(?<!\d)([34]):00\s*p\.?m\.?(?!\w)/g)].map(m => Number(m[1]) + 12);
    if (!hours.some(hour => cfg.valid_hours.includes(hour))) throw Error('wrong_pickup_time');
    const totals = [...s.matchAll(/(?:order\s+total|estimated\s+total|total\s+due|total)\s*:?\s*\$\s*([\d,]+(?:\.\d{2})?)/g)];
    if (totals.length !== 1) throw Error('order_total_not_proven');
    const total = Number(totals[0][1].replace(/,/g, ''));
    if (!Number.isFinite(total) || total <= 0 || total > cfg.max_total_usd) throw Error('price_above_cap');
    return total;
  };
  try {
    if (!allowedUrls[cfg.sku] || cfg.url !== allowedUrls[cfg.sku]) return fail('sku_rejected');
    if (!allowedStores.includes(cfg.store)) return fail('store_rejected');
    if (!Number.isFinite(cfg.max_total_usd) || cfg.max_total_usd < 1999 || cfg.max_total_usd > 3000) return fail('cap_invalid');
    if (!Array.isArray(cfg.valid_hours) || !cfg.valid_hours.length || cfg.valid_hours.some(x=>![15,16].includes(x))) return fail('hours_invalid');
    if (cfg.quantity !== 1 || typeof cfg.submit_order !== 'boolean') return fail('not_armed');
    stage = 'product';
    await page.goto(cfg.url, {waitUntil:'domcontentloaded', timeout:30000});
    await stopOnChallenge();
    stage = 'applecare';
    if (!await chooseNoAppleCare()) throw Error('no_applecare_option_missing');
    // Never continue if the explicit no-coverage choice isn't available.
    stage = 'product';
    await requireClick([/^add to bag$/i, /^add to cart$/i]);
    stage = 'bag';
    await page.goto('https://www.apple.com/shop/bag', {waitUntil:'domcontentloaded', timeout:30000});
    await stopOnChallenge();
    await requireClick([/^check out$/i, /^checkout$/i]);
    stage = 'pickup';
    await stopOnChallenge();
    await requireClick([/^(pick up|pickup|pick up in store)$/i, /pick up at an apple store/i]);
    const zip = page.getByRole('textbox', {name:/zip|location|postal/i});
    if (await zip.count() !== 1) throw Error('zip_entry_missing');
    await zip.fill(cfg.zip);
    await zip.press('Enter');
    await page.waitForTimeout(700);
    await stopOnChallenge();
    const storeChoices = [
      page.getByText(cfg.store, {exact:true}),
      page.getByText('Apple ' + cfg.store, {exact:true})
    ];
    let selectedStore = false;
    for (const option of storeChoices) {
      if (await option.count() === 1 && await option.isVisible()) {
        await option.click({timeout:4500});
        selectedStore = true;
        break;
      }
    }
    if (!selectedStore) throw Error('pickup_store_missing');
    await stopOnChallenge();
    stage = 'pickup_time';
    // Never guess or choose a different date/time. If Apple requires an
    // unrecognized calendar interaction, stop and leave the tab for user.
    // The final review must independently confirm the exact requested slot.
    const slotLabel = h => new RegExp('^' + (h - 12) + ':00\\s*p\\.?m\\.?$', 'i');
    let slotSelected = false;
    for (const hour of cfg.valid_hours) {
      if (await clickUnique([slotLabel(hour)], ['radio','button','option'])) {
        slotSelected = true;
        break;
      }
    }
    if (!slotSelected) throw Error('pickup_time_selector_missing');
    stage = 'final_review';
    for (let step=0; step<3; step++) {
      try { await findReview(); break; }
      catch {
        if (!await clickUnique([/^continue$/i, /^review order$/i, /^review your order$/i])) {
          throw Error('review_navigation_missing');
        }
      }
    }
    await stopOnChallenge();
    const summary = await findReview();
    const total = validateSummary(summary);
    if (cfg.submit_order === false) return result({status:'review_verified', stage, total_usd:total});
    stage = 'submit';
    const final = page.getByRole('button', {name:/^(place (?:your )?order|complete purchase)$/i});
    if (await final.count() !== 1 || !await final.isVisible() || !await final.isEnabled()) {
      throw Error('final_order_button_missing');
    }
    // Single guarded submission. No retries, even if network/browser errors.
    clickedOrderButton = true; // conservative: treat exceptions as possibly submitted
    await final.click({timeout:5000});
    return result({status:'submitted_unverified', stage, clickedOrderButton, total_usd:total});
  } catch (error) {
    // Never log browser snapshots, account IDs, tokens, cards or private page text.
    const known = new Set([
      'outside_apple','human_verification_required','expected_control_missing',
      'final_review_missing','order_mismatch','wrong_storage','quantity_not_proven',
      'wrong_quantity','wrong_pickup_date','not_pickup','wrong_pickup_time',
      'order_total_not_proven','price_above_cap','zip_entry_missing',
      'pickup_store_missing','pickup_time_selector_missing','review_navigation_missing',
      'final_order_button_missing','no_applecare_option_missing',
      'no_applecare_selection_unverified','no_applecare_not_verified',
      'unexpected_applecare'
    ]);
    return fail(known.has(error?.message) ? error.message : 'checkout_interface_unrecognized');
  }
}