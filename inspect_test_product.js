async page => {
  // Read-only public Apple shopping UI test. No purchases, clicks, cookies,
  // navigation, page dumps, tokens, account access, or full personal text.
  const output = payload => 'DUO_TEST_PICKUP_INSPECT=' + JSON.stringify(payload);
  try {
    const url = new URL(page.url());
    if (!['apple.com','www.apple.com'].includes(url.hostname) ||
        !url.pathname.startsWith('/shop/') ||
        /account|signin|checkout|orderstatus|payment/i.test(url.pathname)) {
      return output({status:'not_product_page',controls:[],stores:[]});
    }
    const data=await page.evaluate(() => {
      const markers = /pick[\s-]?up|collect in store|check availability|search stores|change store|available today|unavailable/i;
      const approved=[
        'The Shops at Blackstone Valley','Natick','Boylston Street',
        'Chestnut Hill','Legacy Place'
      ];
      const controls = new Set();
      const stores = new Set();
      const norm = str => String(str||'').replace(/\s+/g,' ').trim();
      const els=document.querySelectorAll('button,a,label,[role="button"],[role="link"],[role="radio"],input[aria-label],h1,h2,h3,h4');
      for(const el of [...els].slice(0,2000)) {
        if (!el.getClientRects().length) continue;
        const role=(el.getAttribute('role') || el.tagName || '').toLowerCase();
        const label=norm(el.getAttribute('aria-label') || el.innerText);
        // Avoid logging large or sensitive sections.
        if (label && label.length <= 90 && markers.test(label)) {
          controls.add((role==='a'?'link':role) + ': ' + label);
        }
        if (label && label.length <= 90) {
          for(const store of approved) {
            if (label.toLowerCase()===store.toLowerCase() ||
                label.toLowerCase()==='apple '+store.toLowerCase()) stores.add(store);
          }
        }
        if(controls.size>=15 && stores.size>=5)break;
      }
      return {status:'read_only',controls:[...controls].slice(0,15),
              stores:[...stores].slice(0,5)};
    });
    return output(data);
  } catch {
    return output({status:'inspection_failed',controls:[],stores:[]});
  }
}