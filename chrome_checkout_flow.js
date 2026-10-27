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
    // Page-reading must not depend on transferring the *entire* Apple Store
    // configurator's text over the extension connection. Inspect DOM text
    // within Chrome and return only a small allowlisted verdict.
    // Do not click past human verification or treat unreadable pages as safe.
    if (typeof page.evaluate !== 'function') throw Error('challenge_eval_unavailable');
    for (let attempt=0; attempt<3; attempt++) {
      let url;
      try { url = page.url(); }
      catch { throw Error('challenge_page_unreadable'); }
      if (!appleHost(url)) throw Error('outside_apple');
      try {
        const state = await page.evaluate(() => {
          const body = document.body;
          if (!body) return 'unreadable';
          const content = (document.title || '') + '\n' + (body.innerText || '');
          if (!content.trim()) return 'unreadable';
          if (/captcha|verify (?:you.?re|that you are) (?:a )?human|unusual traffic|robot check|bot verification|checking your browser|verify you are a robot/i.test(content)) {
            return 'human_verification';
          }
          return 'readable';
        });
        if (!appleHost(page.url())) throw Error('outside_apple');
        if (state === 'human_verification') throw Error('human_verification_required');
        if (state === 'readable') return;
        if (state !== 'unreadable') throw Error('challenge_page_unreadable');
      } catch (err) {
        if (['outside_apple','human_verification_required'].includes(err?.message)) throw err;
        if (attempt === 2) throw Error('challenge_page_unreadable');
      }
      // A transient client-side render can clear on retry. Only retry READS.
      await page.waitForTimeout(600);
    }
    throw Error('challenge_page_unreadable');
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
  const addProductToBag = async () => {
    // Apple may show Add to Bag as a button or link, and the UI may render
    // after selecting No AppleCare. A single product-specific Continue step
    // is allowed; no pay/checkout/express-payment buttons are used here.
    const addPattern=/^add(?:\s+this\s+item)?\s+to\s+(?:my\s+)?(?:bag|cart)(?:\s*[—:-]\s*.*)?$/i;
    const continuePattern=/^continue$/i;
    let usedContinue=false;
    for(let attempt=0;attempt<26;attempt++){
      operation='product_challenge_check';
      await stopOnChallenge();
      const current=page.url();
      if(!appleHost(current))throw Error('outside_apple');
      if (/\/shop\/bag(?:[/?#]|$)/.test(current)) return true;
      // Never use a product Continue control if Apple's flow went off
      // the exact approved 256GB configuration page.
      if(!current.startsWith(cfg.url)) throw Error('product_page_changed');
      operation='product_find_add_to_bag';
      const candidates=[];
      let disabled=false;
      for(const role of ['button','link']){
        const item=page.getByRole(role,{name:addPattern});
        const count=await item.count();
        if(count>1)throw Error('product_add_to_bag_ambiguous');
        if(count===1 && await item.isVisible()){
          if(await item.isEnabled())candidates.push(item);
          else disabled=true;
        }
      }
      if(candidates.length>1)throw Error('product_add_to_bag_ambiguous');
      if(candidates.length===1){
        operation='product_click_add_to_bag';
        await candidates[0].click({timeout:5500});
        operation='product_confirm_add_to_bag';
        await stopOnChallenge();
        return true;
      }
      if(disabled)throw Error('product_add_to_bag_disabled');

      // Apple's phone configurator may have a final "Continue" after the
      // coverage choice; click it at most once, after No AppleCare was verified.
      // Never click general Continue on checkout or payment pages.
      if(!usedContinue){
        operation='product_find_continue';
        const next=page.getByRole('button',{name:continuePattern});
        const nextCount=await next.count();
        if(nextCount>1)throw Error('product_continue_ambiguous');
        if(nextCount===1 && await next.isVisible() && await next.isEnabled()){
          operation='product_click_continue';
          await next.click({timeout:5500});
          usedContinue=true;
          await stopOnChallenge();
          continue;
        }
      }
      operation='product_wait_for_add_to_bag';
      await page.waitForTimeout(500);
    }
    throw Error(usedContinue?'product_add_to_bag_missing_after_continue':'product_add_to_bag_missing');
  };
  const openBagCheckout = async () => {
    // Apple's bag can contain TWO identical standard Check Out buttons
    // (e.g. above and below the bag) as well as the unrelated Apple Pay one.
    // Prioritize ONLY an exact ordinary Checkout label, choose its first
    // visible and enabled instance, and never use Apple Pay/Express Checkout.
    const names = [
      /^check[\s-]?out$/i,
      /^proceed to check[\s-]?out$/i,
      /^continue to check[\s-]?out$/i
    ];
    for (let attempt=0; attempt<20; attempt++) {
      operation='bag_challenge_check';
      await stopOnChallenge();
      operation='bag_find_checkout';
      // First seek the exact standard Checkout button, then a matching link.
      // Duplicates of the SAME label are expected on Apple bag pages.
      for (const name of names) {
        for (const role of ['button','link']) {
          const matched=page.getByRole(role,{name});
          const count=await matched.count();
          // Very large matches imply a changed/misread page; stop safely.
          if (count > 6) throw Error('bag_checkout_ambiguous');
          for (let i=0;i<count;i++) {
            const candidate=matched.nth(i);
            if (!await candidate.isVisible() || !await candidate.isEnabled()) continue;
            operation='bag_checkout_click';
            await candidate.click({timeout:6000});
            operation='bag_checkout_verify';
            await stopOnChallenge();
            return true;
          }
        }
      }
      operation='bag_wait_for_checkout';
      await page.waitForTimeout(500);
    }
    return false;
  };
  const readPickupAvailability = async () => {
    // Return only a minimal status; never expose account or bag text.
    // A single unavailable store is NOT evidence that all five lack stock.
    operation='pickup_read_availability';
    return page.evaluate(store => {
      const lines=(document.body?.innerText||'').split(/\r?\n/)
        .map(x=>x.trim().replace(/\s+/g,' ').toLowerCase())
        .filter(x=>x && x.length < 180);
      const exactNoStores=[
        /\bno (?:apple )?stores? (?:nearby|near you|in your area|are )?available for (?:store )?pick\s*up\b/,
        /\bno (?:available|eligible) (?:pick\s*up )?(?:stores?|locations?)\b/,
        /\bpick\s*up (?:is )?(?:not available|unavailable) (?:at any|near you|in your area)\b/,
        /\bno stores? (?:currently )?offer(?:s|ing)? pick\s*up\b/
      ];
      if (lines.some(line=>exactNoStores.some(rx=>rx.test(line)))) return 'no_stores';
      const requested='apple '+String(store||'').toLowerCase().trim();
      // Only a line explicitly naming the REQUESTED store may determine that
      // store is unavailable. An unrelated Blackstone Valley row must not
      // mark Natick as unavailable.
      const unavailable=/(?:unavailable|not available|out of stock)(?:\s+for)?\s+pick\s*up|pick\s*up.*(?:unavailable|not available|out of stock)/;
      if (requested.length>6 && lines.some(line=>
        (line.includes(requested) || line.includes(requested.slice(6)))
        && unavailable.test(line))) return 'requested_store_unavailable';
      return 'unknown';
    },cfg.store);
  };
  const chooseStorePickup = async () => {
    // Apple can label the shipping/pickup choice "I'll pick it up".
    // Match only intentional pickup controls; never "Deliver it".
    const pickupNames = [
      /^i['’]ll\s+pick\s+it\s+up$/i,
      /^i\s+will\s+pick\s+it\s+up$/i,
      /^i['’]d\s+like\s+to\s+pick\s+it\s+up$/i,
      /^pick\s*up\s+in[- ]store$/i,
      /^pick\s*up\s+at\s+an\s+apple\s+store$/i,
      /^store\s+pick\s*up$/i,
      /^pick\s*up$/i
    ];
    for (let attempt=0;attempt<25;attempt++) {
      operation='pickup_challenge_check';
      await stopOnChallenge();
      operation='pickup_find_choice';
      for (const name of pickupNames) {
        for (const role of ['radio','button','link']) {
          const collection=page.getByRole(role,{name});
          const count=await collection.count();
          if (count>4)throw Error('pickup_choice_ambiguous');
          for(let i=0;i<count;i++){
            const choice=collection.nth(i);
            if(!await choice.isVisible() || !await choice.isEnabled())continue;
            operation='pickup_select_choice';
            if(role==='radio'){
              if(!await choice.isChecked())await choice.check({timeout:5500});
              operation='pickup_verify_choice';
              if(!await choice.isChecked())throw Error('pickup_choice_not_selected');
            } else {
              await choice.click({timeout:5500});
            }
            operation='pickup_after_choice';
            await stopOnChallenge();
            return true;
          }
        }
      }
      // Exact-text fallback, only when one matching node exists.
      operation='pickup_find_text';
      const exact=page.getByText(/^i['’]ll\s+pick\s+it\s+up$/i,{exact:true});
      const textCount=await exact.count();
      if(textCount>1)throw Error('pickup_choice_ambiguous');
      if(textCount===1 && await exact.isVisible()){
        operation='pickup_click_text';
        await exact.click({timeout:5500});
        operation='pickup_after_choice';
        await stopOnChallenge();
        return true;
      }
      operation='pickup_wait_for_choice';
      await page.waitForTimeout(500);
    }
    throw Error('pickup_choice_missing');
  };
  const chooseNoAppleCare = async () => {
    // Read ONLY label text and associated control state inside Chrome.
    // The inspected Apple configurator exposes a <label> containing the
    // literal wording "No AppleCare coverage". Its native radio/checkbox
    // must be verified as checked after a real Playwright click.
    const discover = async () => page.evaluate(() => {
      const norm = text => String(text || '').replace(/\s+/g,' ').trim().toLowerCase();
      const title = /^(no applecare(?:\+)? coverage)$/;
      const labels = [...document.querySelectorAll('label')];
      const found = [];
      labels.forEach((label, index) => {
        const visible = !!(label.getClientRects().length);
        if (!visible) return;
        const own = norm(label.innerText);
        // Apple may include subtext alongside the exact no-coverage title.
        const exactChild = [...label.querySelectorAll('h1,h2,h3,h4,span,strong,p,div')]
          .some(el => title.test(norm(el.innerText)));
        if (!title.test(own) && !exactChild) return;
        const input = label.control || label.querySelector('input[type="radio"], input[type="checkbox"]')
          || (label.htmlFor ? document.getElementById(label.htmlFor) : null);
        if (!input || !['radio','checkbox'].includes(input.type)) {
          found.push({index, readable:false, checked:false});
          return;
        }
        const inputs = [...document.querySelectorAll('input[type="radio"], input[type="checkbox"]')];
        const inputIndex = inputs.indexOf(input);
        found.push({
          index, inputIndex, readable:inputIndex >= 0,
          checked:input.checked === true,
          disabled:!!(input.disabled || input.closest?.('[inert],[aria-disabled="true"],fieldset[disabled]'))
        });
      });
      if (found.length !== 1) return {kind:found.length?'ambiguous':'missing'};
      return {kind:found[0].readable?'found':'unverifiable', ...found[0]};
    });

    // Select only the one observed no-coverage option. A label may be
    // partially off-screen in a narrow Chrome window; prefer its visible
    // exact text, and scroll controls into view before a native click.
    const verifySelected = async index => {
      operation = 'care_verify_selection';
      for (let i=0;i<5;i++) {
        const current = await discover();
        if (current.kind === 'found' && current.index === index && current.checked) {
          operation = 'care_confirm_no_challenge';
          await stopOnChallenge();
          return true;
        }
        if (current.kind === 'ambiguous' || current.kind === 'unverifiable') {
          throw Error('no_applecare_selection_unverified');
        }
        await page.waitForTimeout(250);
      }
      return false;
    };

    const clickMethod = async (target, name) => {
      operation = 'care_' + name + '_scroll';
      try {
        await target.scrollIntoViewIfNeeded({timeout:3500});
        operation = 'care_' + name + '_click';
        await target.click({timeout:4000});
        return true;
      } catch (error) {
        // No raw error data is retained (may contain page details).
        operation = 'care_' + name + '_failed';
        await stopOnChallenge();
        return false;
      }
    };

    for (let attempt=0;attempt<32;attempt++) {
      operation = 'care_challenge_check';
      await stopOnChallenge();
      operation = 'care_discover_label';
      const state = await discover();
      if (state.kind === 'ambiguous') throw Error('no_applecare_control_ambiguous');
      if (state.kind === 'unverifiable') throw Error('no_applecare_selection_unverified');
      if (state.kind === 'found') {
        if (state.disabled) throw Error('no_applecare_option_disabled');
        if (state.checked) {
          operation = 'care_confirm_no_challenge';
          await stopOnChallenge();
          return true;
        }
        // First try the real associated native input. Playwright's check()
        // performs normal actionability checks and verifies the input itself.
        // Do not force clicks, dispatch synthetic DOM events, or modify React state.
        if (Number.isInteger(state.inputIndex) && state.inputIndex >= 0) {
          operation = 'care_input_check';
          const input = page.locator('input[type="radio"],input[type="checkbox"]').nth(state.inputIndex);
          try {
            await input.check({timeout:3500});
            if (await verifySelected(state.index)) return true;
          } catch (error) {
            operation = 'care_input_unavailable';
            await stopOnChallenge();
          }
        }
        // Fall back only to ordinary visible clicks on the exact no-care UI.
        operation = 'care_find_exact_text';
        const text = page.getByText(/^\s*No AppleCare(?:\+)? coverage\s*$/i, {exact:true});
        const count = await text.count();
        if (count === 1 && await text.isVisible()) {
          if (await clickMethod(text,'text') && await verifySelected(state.index)) return true;
        }
        operation = 'care_find_exact_label';
        const label = page.locator('label').nth(state.index);
        if (await clickMethod(label,'label') && await verifySelected(state.index)) return true;
        throw Error('no_applecare_click_failed');
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
    if (cfg.resume_bag && cfg.submit_order) return fail('bag_resume_must_not_submit');
    if (cfg.resume_bag) {
      // A resumed bag is for nonpaying testing ONLY. Confirm the configured
      // phone exists in the bag; do not add another unit or make any payment.
      stage = 'bag';
      operation = 'bag_resume_verify';
      if (!appleHost(page.url())) return fail('outside_apple');
      if (!/\/shop\/bag(?:[/?#]|$)/.test(page.url())) {
        await page.goto('https://www.apple.com/shop/bag',{waitUntil:'domcontentloaded',timeout:30000});
      }
      await stopOnChallenge();
      const expectedColor = cfg.sku === 'MK1E4LL/A' ? 'star white' : 'night sky';
      const present=await page.evaluate(color=>{
        const text=(document.body?.innerText||'').toLowerCase();
        return text.includes('iphone duo 256gb '+color);
      },expectedColor);
      if (!present) return fail('bag_expected_phone_missing');
    } else {
    stage = 'product';
    // The Python launcher already opened the approved SKU in a new Chrome
    // tab. Do NOT reload it again: Apple's React configurator may reset its
    // choices or hydration state on the second redundant navigation.
    if (page.url().replace(/\/$/, '') !== cfg.url.replace(/\/$/, '')) {
      await page.goto(cfg.url, {waitUntil:'domcontentloaded', timeout:30000});
    }
    await stopOnChallenge();
    stage = 'applecare';
    if (!await chooseNoAppleCare()) throw Error('no_applecare_option_missing');
    // Never continue if the explicit no-coverage choice isn't available.
    stage = 'product';
    await addProductToBag();
    stage = 'bag';
    await page.goto('https://www.apple.com/shop/bag', {waitUntil:'domcontentloaded', timeout:30000});
    await stopOnChallenge();
    }
    if (!await openBagCheckout()) throw Error('bag_checkout_control_missing');
    stage = 'pickup';
    await chooseStorePickup();
    const zip = page.getByRole('textbox', {name:/zip|location|postal/i});
    // If Apple has no pickup offer there may be no ZIP-code field at all.
    // Wait for the form to appear, but distinguish explicit unavailability
    // from a layout we simply do not recognize.
    let zipReady=false;
    for(let attempt=0;attempt<20;attempt++){
      operation='pickup_find_zip';
      const count=await zip.count();
      if(count>1)throw Error('zip_entry_ambiguous');
      if(count===1 && await zip.isVisible() && await zip.isEnabled()){
        zipReady=true;
        break;
      }
      const availability=await readPickupAvailability();
      if(availability==='no_stores')throw Error('pickup_no_stores_available');
      if(availability==='requested_store_unavailable')throw Error('pickup_requested_store_unavailable');
      operation='pickup_wait_for_zip';
      await page.waitForTimeout(500);
    }
    if(!zipReady)throw Error('zip_entry_missing');
    operation='pickup_fill_zip';
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
      'outside_apple','human_verification_required','challenge_page_unreadable','challenge_eval_unavailable',
      'bag_checkout_control_missing','bag_checkout_ambiguous',
      'bag_expected_phone_missing','bag_resume_must_not_submit',
      'product_page_changed','product_add_to_bag_ambiguous','product_add_to_bag_disabled',
      'product_continue_ambiguous','product_add_to_bag_missing_after_continue',
      'product_add_to_bag_missing',
      'expected_control_missing',
      'final_review_missing','order_mismatch','wrong_storage','quantity_not_proven',
      'wrong_quantity','wrong_pickup_date','not_pickup','wrong_pickup_time',
      'order_total_not_proven','price_above_cap','zip_entry_missing',
      'zip_entry_ambiguous','pickup_no_stores_available','pickup_requested_store_unavailable',
      'pickup_store_missing','pickup_choice_missing','pickup_choice_ambiguous',
      'pickup_choice_not_selected','pickup_time_selector_missing','review_navigation_missing',
      'final_order_button_missing','no_applecare_option_missing',
      'no_applecare_selection_unverified','no_applecare_option_disabled',
      'no_applecare_click_failed',
      'no_applecare_control_ambiguous',
      'no_applecare_not_verified',
      'unexpected_applecare'
    ]);
    return fail(known.has(error?.message) ? error.message : 'checkout_interface_unrecognized');
  }
}