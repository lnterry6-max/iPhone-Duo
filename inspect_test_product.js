async page => {
  // This is deliberately read-only. A test product can NEVER trigger Duo
  // checkout. Never expose account data, full page text, cookies or tokens.
  const output = data => 'DUO_TEST_PICKUP_INSPECT=' + JSON.stringify(data);
  const empty = status => ({status,controls:[],stores:[],storeAvailability:[],pickupUiPresent:false});
  try {
    const url = new URL(page.url());
    if (!['apple.com','www.apple.com'].includes(url.hostname) ||
        !url.pathname.startsWith('/shop/') ||
        /account|signin|checkout|orderstatus|payment/i.test(url.pathname)) {
      return output(empty('not_product_page'));
    }
    const data=await page.evaluate(() => {
      const approved=[
        'The Shops at Blackstone Valley','Natick','Boylston Street',
        'Chestnut Hill','Legacy Place'
      ];
      const marker=/pick[\s-]?up|collect in store|check availability|search stores|change store|available today|unavailable/i;
      const positive=/\b(?:available (?:for|to) (?:in[- ]store )?pick[\s-]?up|pick[\s-]?up (?:available|today|tomorrow)|ready for pick[\s-]?up)\b/i;
      const negative=/\b(?:unavailable (?:for )?pick[\s-]?up|not available (?:for )?pick[\s-]?up|pick[\s-]?up (?:unavailable|not available)|out of stock)\b/i;
      const norm = x => String(x||'').replace(/\s+/g,' ').trim();
      const controls=new Set(), stores=new Set();
      const storeAvailability=new Map();
      let pickupUiPresent=false;
      const els=document.querySelectorAll('button,a,label,span,p,small,[role="button"],[role="link"],[role="radio"],input[aria-label],h1,h2,h3,h4');
      for(const el of [...els].slice(0,3000)) {
        if(!el.getClientRects().length)continue;
        const role=(el.getAttribute('role')||el.tagName||'').toLowerCase();
        const label=norm(el.getAttribute('aria-label')||el.innerText);
        if(label.length<=120 && marker.test(label))pickupUiPresent=true;
        if(label.length>0 && label.length<=90 && marker.test(label)){
          if(controls.size<15 && /^(?:button|a|label|input)$/.test(role))controls.add((role==='a'?'link':role)+': '+label);
        }
        if(label.length===0 || label.length>95)continue;
        for(const store of approved) {
          const lower=label.toLowerCase();
          const name=store.toLowerCase();
          if(lower!==name && lower!=='apple '+name)continue;
          stores.add(store);
          // Only inspect very small, immediate visible ancestors of the exact
          // store name; broader page-level statuses are NOT attributed to it.
          let p=el.parentElement;
          for(let level=0;p && level<3;level++,p=p.parentElement) {
            if(!p.getClientRects().length)break;
            const nearby=norm(p.innerText);
            if(nearby.length>240)break;
            const no=negative.test(nearby), yes=positive.test(nearby);
            if(no!==yes) {
              const next=no?'unavailable':'available';
              const old=storeAvailability.get(store);
              storeAvailability.set(store,old && old!==next?'unknown':next);
              break;
            }
          }
        }
      }
      return {
        status:'read_only',controls:[...controls].slice(0,15),
        stores:[...stores].slice(0,5),
        storeAvailability:[...stores].slice(0,5).map(store=>({
          store,availability:storeAvailability.get(store)||'unknown'
        })),
        pickupUiPresent
      };
    });
    return output(data);
  } catch {
    return output(empty('inspection_failed'));
  }
}