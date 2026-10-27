import fs from 'node:fs';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../chrome_checkout_flow.js',import.meta.url),'utf8');
const start=source.indexOf('  const readPickupAvailability = async () => {');
const end=source.indexOf('  const chooseStorePickup = async () => {',start);
assert.ok(start>0 && end>start,'pickup availability reader exists');
const fn=new Function('page','cfg','let operation="test";\n'+source.slice(start,end)+'\nreturn readPickupAvailability();');
async function check(text,store='Natick'){
  const page={
    async evaluate(callback,arg){
      const saved=globalThis.document;
      globalThis.document={body:{innerText:text}};
      try{return callback(arg);}finally{globalThis.document=saved;}
    }
  };
  return fn(page,{store});
}

assert.equal(await check('No stores are available for pickup nearby'),'no_stores');
assert.equal(await check('No eligible pickup locations were found'),'no_stores');
assert.equal(await check('Pickup is unavailable at any store'),'no_stores');

assert.equal(await check('Apple Natick unavailable for pickup'),'requested_store_unavailable');
assert.equal(await check('Unavailable for pickup at Apple Natick'),'requested_store_unavailable');

// Prior bag screenshot showed Blackstone unavailable while user tests Natick.
// That does not justify concluding that Natick or all five stores are unavailable.
assert.equal(await check('Unavailable for pickup at Apple The Shops at Blackstone Valley','Natick'),'unknown');
assert.equal(await check('Apple Natick - Pick up tomorrow'),'unknown');
assert.equal(await check('Checkout | Select delivery or pickup'),'unknown');
assert.equal(await check('No ZIP field on this version of the checkout page'),'unknown');

assert.ok(source.includes("if(!zipReady)throw Error('zip_entry_missing')"));
assert.ok(source.includes("throw Error('pickup_no_stores_available')"));
assert.ok(source.includes("throw Error('pickup_requested_store_unavailable')"));
assert.ok(source.includes("throw Error('zip_entry_ambiguous')"));
console.log('Apple pickup availability tests passed: explicit no stock, target-only unavailable, and unknown UI.');
