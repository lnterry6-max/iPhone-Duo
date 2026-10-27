import fs from "node:fs";
import assert from "node:assert/strict";

const source=fs.readFileSync(new URL("../chrome_checkout_flow.js",import.meta.url),"utf8");
const start=source.indexOf("  const addProductToBag = async () => {");
const end=source.indexOf("  const openBagCheckout = async () => {",start);
assert.ok(start>0 && end>start);
const cfg={url:"https://www.apple.com/shop/buy-iphone/iphone-duo/7.6-inch-display-256gb-star-white-unlocked"};
const run=new Function("page","stopOnChallenge","cfg",'let operation="start"; const appleHost = url => { try { const h=new URL(url).hostname; return h==="apple.com"||h.endsWith(".apple.com"); } catch { return false; }};\n'+source.slice(start,end)+'\nreturn addProductToBag();');
function fixture({control="button",label="Add to Bag",delay=0,disabled=false,duplicate=false,continueFirst=false,
                 changed=false,challenge=false}={}){
 let ticks=0,clicks=0,continues=0;
 let address=changed?"https://www.apple.com/shop/bag/other-product":cfg.url;
 const page={
   url:()=>address,
   getByRole(role,{name:pattern}){
     const isContinue=role==="button" && pattern.test("Continue") && !pattern.test("Add to Bag");
     const isAdd=role===control && pattern.test(label);
     const shouldExist=isContinue?continueFirst&&continues===0
       :isAdd&&ticks>=delay&&(!continueFirst||continues>0);
     return {
       count:async()=>shouldExist?(duplicate?2:1):0,
       isVisible:async()=>true,
       isEnabled:async()=>!disabled,
       click:async({timeout})=>{
         assert.equal(timeout,5500);
         clicks++;
         if(isContinue)continues++;
       }
     };
   },
   waitForTimeout:async ms=>{assert.equal(ms,500);ticks++;}
 };
 return {page,guard:async()=>{if(challenge)throw Error("human_verification_required")},
  get clicks(){return clicks},get continues(){return continues},get ticks(){return ticks}};
}

const button=fixture();
assert.equal(await run(button.page,button.guard,cfg),true);
assert.equal(button.clicks,1);
assert.equal(button.continues,0);

const link=fixture({control:"link",label:"Add to Bag"});
assert.equal(await run(link.page,link.guard,cfg),true);
assert.equal(link.clicks,1);

const delay=fixture({delay:3});
assert.equal(await run(delay.page,delay.guard,cfg),true);
assert.ok(delay.ticks>=3);

const continueStep=fixture({continueFirst:true});
assert.equal(await run(continueStep.page,continueStep.guard,cfg),true);
assert.equal(continueStep.continues,1);
assert.equal(continueStep.clicks,2);

const pay=fixture({label:"Checkout with Apple Pay"});
await assert.rejects(run(pay.page,pay.guard,cfg),/product_add_to_bag_missing/);
assert.equal(pay.clicks,0);

const duplicates=fixture({duplicate:true});
await assert.rejects(run(duplicates.page,duplicates.guard,cfg),/product_add_to_bag_ambiguous/);
assert.equal(duplicates.clicks,0);

const offpage=fixture({changed:true});
assert.equal(await run(offpage.page,offpage.guard,cfg),true,"already on bag");

const disabled=fixture({disabled:true});
await assert.rejects(run(disabled.page,disabled.guard,cfg),/product_add_to_bag_disabled/);
assert.equal(disabled.clicks,0);

const challenge=fixture({challenge:true});
await assert.rejects(run(challenge.page,challenge.guard,cfg),/human_verification_required/);
assert.equal(challenge.clicks,0);

console.log("Product add-to-bag tests passed: button, link, delayed, Continue, disabled, ambiguous, payment rejection.");
