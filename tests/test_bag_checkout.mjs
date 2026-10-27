import fs from "node:fs";
import assert from "node:assert/strict";

const source=fs.readFileSync(new URL("../chrome_checkout_flow.js",import.meta.url),"utf8");
const start=source.indexOf("  const openBagCheckout = async () => {");
const stop=source.indexOf("  const chooseNoAppleCare = async () => {",start);
assert.ok(start>0 && stop>start);
const call=new Function("page","stopOnChallenge", 'let operation="test";\n'+source.slice(start,stop)+'\nreturn openBagCheckout();');

function fixture({kind="button",name="Check Out",delay=0,disabled=false,ambiguous=false,challenge=false}={}){
 let ticks=0,clicks=0,checks=0;
 const page={
  getByRole(role,{name:pattern}){
   const exists=kind===role && pattern.test(name) && ticks>=delay;
   return {
    count:async()=>exists?(ambiguous?2:1):0,
    isVisible:async()=>true,
    isEnabled:async()=>!disabled,
    click:async({timeout})=>{assert.equal(timeout,6000);clicks++;}
   };
  },
  waitForTimeout:async ms=>{assert.equal(ms,500);ticks++;}
 };
 return {page,guard:async()=>{checks++;if(challenge)throw Error("human_verification_required")},
   get clicks(){return clicks},get ticks(){return ticks},get checks(){return checks}};
}
const button=fixture();
assert.equal(await call(button.page,button.guard),true);
assert.equal(button.clicks,1);
assert.ok(button.checks>=2);

const link=fixture({kind:"link",name:"Proceed to Checkout"});
assert.equal(await call(link.page,link.guard),true,"checkout may be a link");
assert.equal(link.clicks,1);

const later=fixture({delay:4});
assert.equal(await call(later.page,later.guard),true,"async checkout button");
assert.ok(later.ticks>=4);

const payment=fixture({name:"Check Out with Apple Pay"});
assert.equal(await call(payment.page,payment.guard),false,"must not click quick-pay button");
assert.equal(payment.clicks,0);

const disabled=fixture({disabled:true});
assert.equal(await call(disabled.page,disabled.guard),false);
assert.equal(disabled.clicks,0);

const ambiguous=fixture({ambiguous:true});
await assert.rejects(call(ambiguous.page,ambiguous.guard),/bag_checkout_ambiguous/);
assert.equal(ambiguous.clicks,0);

const challenge=fixture({challenge:true});
await assert.rejects(call(challenge.page,challenge.guard),/human_verification_required/);
assert.equal(challenge.clicks,0);

console.log("Bag checkout tests passed: link, button, delayed, disabled, ambiguous, verification and payment-avoidance.");
