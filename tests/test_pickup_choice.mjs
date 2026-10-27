import fs from "node:fs";
import assert from "node:assert/strict";

const code=fs.readFileSync(new URL("../chrome_checkout_flow.js",import.meta.url),"utf8");
const start=code.indexOf("  const chooseStorePickup = async () => {");
const end=code.indexOf("  const chooseNoAppleCare = async () => {",start);
assert.ok(start>0 && end>start,"pickup chooser exists");
const choose=new Function("page","stopOnChallenge",'let operation="start";\n'+code.slice(start,end)+'\nreturn chooseStorePickup();');

function make({role="button",label="I'll pick it up",delay=0,enabled=true,checked=false,
               copies=1,challenge=false}={}){
  let clicks=0,ticks=0,after=0;
  const page={
    getByRole(kind,{name}){
      const match=kind===role && name.test(label) && ticks>=delay;
      const count=match?copies:0;
      return {
        count:async()=>count,
        nth(index){assert.ok(index<count);return {
          isVisible:async()=>true,
          isEnabled:async()=>enabled,
          isChecked:async()=>checked,
          check:async({timeout})=>{assert.equal(timeout,5500);checked=true;clicks++;},
          click:async({timeout})=>{assert.equal(timeout,5500);clicks++;}
        }}
      };
    },
    getByText(pattern,{exact}){
      assert.equal(exact,true);
      const match=pattern.test(label) && ticks>=delay;
      return {
        count:async()=>match?copies:0,
        isVisible:async()=>true,
        click:async({timeout})=>{assert.equal(timeout,5500);clicks++;}
      };
    },
    waitForTimeout:async t=>{assert.equal(t,500);ticks++;}
  };
  return {page,guard:async()=>{after++;if(challenge)throw Error("human_verification_required")},
    get clicks(){return clicks},get ticks(){return ticks},get after(){return after}};
}

const preferred=make();
assert.equal(await choose(preferred.page,preferred.guard),true);
assert.equal(preferred.clicks,1);
assert.ok(preferred.after>=2);

const apostrophe=make({label:"I’ll pick it up"});
assert.equal(await choose(apostrophe.page,apostrophe.guard),true);
assert.equal(apostrophe.clicks,1);

const radio=make({role:"radio",label:"I'll pick it up"});
assert.equal(await choose(radio.page,radio.guard),true);
assert.equal(radio.clicks,1);

const selected=make({role:"radio",checked:true});
assert.equal(await choose(selected.page,selected.guard),true);
assert.equal(selected.clicks,0);

const late=make({delay:5});
assert.equal(await choose(late.page,late.guard),true);
assert.ok(late.ticks>=5);

const delivery=make({label:"I'll have it delivered"});
await assert.rejects(choose(delivery.page,delivery.guard),/pickup_choice_missing/);
assert.equal(delivery.clicks,0,"must not select delivery");

const noPay=make({label:"Check out with Apple Pay"});
await assert.rejects(choose(noPay.page,noPay.guard),/pickup_choice_missing/);
assert.equal(noPay.clicks,0);

const disabled=make({enabled:false,label:"Pick up"});
// Exact-text fallback only recognizes "I'll pick it up", not a disabled generic control.
await assert.rejects(choose(disabled.page,disabled.guard),/pickup_choice_missing/);
assert.equal(disabled.clicks,0);

const duplicated=make({label:"I'll pick it up",copies:5});
await assert.rejects(choose(duplicated.page,duplicated.guard),/pickup_choice_ambiguous/);
assert.equal(duplicated.clicks,0);

const verification=make({challenge:true});
await assert.rejects(choose(verification.page,verification.guard),/human_verification_required/);
assert.equal(verification.clicks,0);

console.log("Pickup choice tests passed: button/radio/curly apostrophe/delay, reject delivery and verification.");
