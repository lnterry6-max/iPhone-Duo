// Offline, no Apple access: invoke the actual final-review verifier used
// immediately before any possible payment click, with controlled input text.
import fs from 'node:fs';
import assert from 'node:assert/strict';

const source=fs.readFileSync(new URL('../chrome_checkout_flow.js',import.meta.url),'utf8');
const a=source.indexOf("  const validateSummary = text => {");
const b=source.indexOf("  try {\n    if (!allowedUrls",a);
assert.ok(a>0 && b>a,'missing final-review guard');
const factory=new Function('cfg','allowedStores',source.slice(a,b)+'\nreturn validateSummary;');
const stores=['The Shops at Blackstone Valley','Natick','Boylston Street','Chestnut Hill','Legacy Place'];
const cfg={sku:'MK1E4LL/A',store:'Natick',valid_hours:[15,16],max_total_usd:2200};
const check=factory(cfg,stores);
const good=[
  'iPhone Duo 256GB Star White',
  'Quantity: 1',
  'No AppleCare coverage',
  'Pick up at Apple Natick on October 27, 2026 at 3:00 PM',
  'Order total: $2,123.94'
].join('\n');
assert.equal(check(good),2123.94,'exactly one approved order should be reviewable');
function reject(change,pattern){
  const text=change(good);
  assert.throws(()=>check(text),pattern);
}
reject(s=>s.replace('Star White','Night Sky'),/order_mismatch/);
reject(s=>s+' Night Sky',/conflicting_product_color/);
reject(s=>s+' Apple Legacy Place',/conflicting_pickup_store/);
reject(s=>s+' Apple Watch',/unexpected_other_device/);
reject(s=>s+' Quantity: 1',/quantity_not_unique/);
reject(s=>s.replace('Quantity: 1','Quantity: 2'),/quantity_not_proven|wrong_quantity/);
reject(s=>s.replace('256GB','512GB'),/order_mismatch/);
reject(s=>s.replace('Natick','Chestnut Hill'),/order_mismatch/);
reject(s=>s.replace('October 27, 2026','October 28, 2026'),/wrong_pickup_date/);
reject(s=>s.replace('3:00 PM','5:00 PM'),/wrong_pickup_time/);
reject(s=>s.replace('$2,123.94','$2,300.00'),/price_above_cap/);
reject(s=>s.replace('No AppleCare coverage','AppleCare+ $199/year'),/no_applecare_not_verified/);
reject(s=>s.replace('Pick up','Deliver'),/order_mismatch/);
reject(s=>s.replace('Order total: $2,123.94',''),/order_total_not_proven/);

// The other permitted color is independently valid.
const black=factory({...cfg,sku:'MK1F4LL/A'},stores);
assert.equal(black(good.replace('Star White','Night Sky')),2123.94);
console.log('Final order summary guard tests passed, including duplicate and conflicting items.');
