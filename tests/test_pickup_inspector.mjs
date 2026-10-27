import fs from "node:fs";
import assert from "node:assert/strict";

const source=fs.readFileSync(new URL("../inspect_test_product.js",import.meta.url),"utf8");
const inspect=new Function("return ("+source+")")();

function fixture({store="The Shops at Blackstone Valley",nearby="",pickupButton="",url="https://www.apple.com/shop/buy-watch/apple-watch"}={}){
  const parent=nearby?{innerText:"Apple "+store+"\n"+nearby,getClientRects:()=>[1],parentElement:null}:null;
  const nodes=[
    {tagName:"SPAN",innerText:store,getClientRects:()=>[1],getAttribute:()=>null,parentElement:parent}
  ];
  if(pickupButton) nodes.push({tagName:"BUTTON",innerText:pickupButton,getClientRects:()=>[1],getAttribute:()=>null,parentElement:null});
  const page={
    url:()=>url,
    evaluate:async(fn)=>{
      const prior=globalThis.document;
      globalThis.document={querySelectorAll:()=>nodes};
      try {return fn();} finally {globalThis.document=prior;}
    }
  };
  return page;
}
async function get(opts) {
  const out=await inspect(fixture(opts));
  assert.ok(out.startsWith("DUO_TEST_PICKUP_INSPECT="));
  return JSON.parse(out.slice("DUO_TEST_PICKUP_INSPECT=".length));
}
const named=await get();
assert.equal(named.status,"read_only");
assert.deepEqual(named.stores,["The Shops at Blackstone Valley"]);
assert.deepEqual(named.storeAvailability,[{store:"The Shops at Blackstone Valley",availability:"unknown"}]);
assert.equal(named.pickupUiPresent,false);

const available=await get({nearby:"Available for pickup today",pickupButton:"Check availability"});
assert.equal(available.storeAvailability[0].availability,"available");
assert.equal(available.pickupUiPresent,true);
assert.deepEqual(available.controls,["button: Check availability"]);

const notAvailable=await get({nearby:"Not available for pickup"});
assert.equal(notAvailable.storeAvailability[0].availability,"unavailable");

const unrelated=await get({nearby:"Delivery only"});
assert.equal(unrelated.storeAvailability[0].availability,"unknown");

const nonStore=await get({url:"https://secure6.store.apple.com/shop/checkout"});
assert.equal(nonStore.status,"not_product_page");

assert.ok(!/click\(|goto\(|fetch\(|add.to.bag|submit.order/i.test(source),"inspector must not navigate or purchase");
console.log("Read-only test-product pickup inspector tests passed.");
