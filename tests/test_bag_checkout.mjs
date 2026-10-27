import fs from "node:fs";
import assert from "node:assert/strict";

const source=fs.readFileSync(new URL("../chrome_checkout_flow.js",import.meta.url),"utf8");
const start=source.indexOf("  const openBagCheckout = async () => {");
const end=source.indexOf("  const chooseNoAppleCare = async () => {",start);
assert.ok(start>0 && end>start,"bag helper missing");
const checkout=new Function("page","stopOnChallenge",'let operation="test";\n'+source.slice(start,end)+'\nreturn openBagCheckout();');

function fixture({role="button",label="Check Out",duplicates=1,delay=0,disabledIndices=[],
                  challenge=false}={}) {
 let ticks=0,clicks=0,checks=0,clickedIndex=-1,clickedRole="";
 const page={
   getByRole(kind,{name}) {
     const exists=kind===role && name.test(label) && ticks>=delay;
     const count=exists?duplicates:0;
     return {
       count:async()=>count,
       nth(index) {
         assert.ok(index<count);
         return {
           isVisible:async()=>true,
           isEnabled:async()=>!disabledIndices.includes(index),
           click:async({timeout})=>{
             assert.equal(timeout,6000);
             clicks++;
             clickedIndex=index;
             clickedRole=kind;
           }
         };
       }
     };
   },
   waitForTimeout:async ms=>{assert.equal(ms,500);ticks++;}
 };
 return {page,guard:async()=>{checks++;if(challenge)throw Error("human_verification_required");},
   get clicks(){return clicks},get index(){return clickedIndex},get kind(){return clickedRole},
   get ticks(){return ticks},get checks(){return checks}};
}

const one=fixture();
assert.equal(await checkout(one.page,one.guard),true);
assert.equal(one.clicks,1);
assert.equal(one.index,0);
assert.ok(one.checks>=2);

const two=fixture({duplicates:2});
assert.equal(await checkout(two.page,two.guard),true,
             "two identical standard Check Out buttons must not block checkout");
assert.equal(two.clicks,1);
assert.equal(two.index,0);

const secondOnly=fixture({duplicates:2,disabledIndices:[0]});
assert.equal(await checkout(secondOnly.page,secondOnly.guard),true);
assert.equal(secondOnly.index,1);

const link=fixture({role:"link",label:"Proceed to Checkout"});
assert.equal(await checkout(link.page,link.guard),true,"checkout can be a link");
assert.equal(link.kind,"link");

const delayed=fixture({delay:4});
assert.equal(await checkout(delayed.page,delayed.guard),true);
assert.ok(delayed.ticks>=4);

const applePay=fixture({label:"Check out with Apple Pay"});
assert.equal(await checkout(applePay.page,applePay.guard),false,
  "never select Apple Pay");
assert.equal(applePay.clicks,0);

const disabled=fixture({duplicates:2,disabledIndices:[0,1]});
assert.equal(await checkout(disabled.page,disabled.guard),false);
assert.equal(disabled.clicks,0);

const suspicious=fixture({duplicates:7});
await assert.rejects(checkout(suspicious.page,suspicious.guard),/bag_checkout_ambiguous/);
assert.equal(suspicious.clicks,0);

const blocked=fixture({challenge:true});
await assert.rejects(checkout(blocked.page,blocked.guard),/human_verification_required/);
assert.equal(blocked.clicks,0);

console.log("Apple bag checkout tests passed: duplicates, visible button/link, later render, Apple Pay rejection, disabled, challenge.");
