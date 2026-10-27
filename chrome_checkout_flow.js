async page => {
  // Runs ONLY in the existing Chrome extension session, on the user's Mac.
  // Parameters are inserted locally by checkout_bot.py (no passwords/cookies).
  const cfg = __DUO_CONFIG_JSON__;
  let stage = 'start';
  let clickedOrderButton = false;
  let operation = 'start';
  const result = obj => 'DUO_AUTOMATION_RESULT=' + JSON.stringify(obj);
  const fail = code => result({status: 'stopped', stage, step: operation, code, clickedOrderButton});
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
    // The user's read-only browser inspection showed a label and input
    // named "No AppleCare coverage". Prefer the associated control rather
    // than inferring state from a wrapper element.
    const noCareName = /^\s*No AppleCare(?:\+)? coverage\s*$/i;
    operation = 'care_locate_control';
    const control = page.getByLabel(noCareName, {exact:true});
    const labels = page.locator('label').filter({hasText:noCareName});
    for (let attempt=0; attempt<24; attempt++) {
      operation = 'care_challenge_check';
      await stopOnChallenge();

      operation = 'care_count_control';
      const controlCount = await control.count();
      if (controlCount > 1) throw Error('no_applecare_control_ambiguous');
      if (controlCount === 1) {
        operation = 'care_check_status';
        const isSelected = await control.isChecked();
        if (!isSelected) {
          operation = 'care_select_control';
          await control.check({timeout:4500});
        }
        operation = 'care_verify_control';
        if (!await control.isChecked()) throw Error('no_applecare_selection_unverified');
        operation = 'care_confirm_no_challenge';
        await stopOnChallenge();
        return true;
      }

      // Fallback for an Apple label with an unexposed accessible name.
      // Click ONLY the exact no-coverage label and confirm its linked input.
      operation = 'care_count_label';
      const labelCount = await labels.count();
      if (labelCount > 1) throw Error('no_applecare_control_ambiguous');
      if (labelCount === 1 && await labels.isVisible()) {
        operation = 'care_fallback_inspect';
        const before = await labels.evaluate(node => {
          const input = node.control || node.querySelector('input[type="radio"], input[type="checkbox"]');
          return !!input && input.checked === true;
        });
        if (!before) {
          operation = 'care_fallback_click';
          await labels.click({timeout:4500});
        }
        operation = 'care_fallback_verify';
        const verified = await labels.evaluate(node => {
          const input = node.control || node.querySelector('input[type="radio"], input[type="checkbox"]');
          return !!input && input.checked === true;
        });
        if (!verified) throw Error('no_applecare_selection_unverified');
        operation = 'care_confirm_no_challenge';
        await stopOnChallenge();
        return true;
      }
      operation = 'care_wait_for_render';
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
      'no_applecare_selection_unverified','no_applecare_control_ambiguous',
      'no_applecare_not_verified',
      'unexpected_applecare'
    ]);
    return fail(known.has(error?.message) ? error.message : 'checkout_interface_unrecognized');
  }
}