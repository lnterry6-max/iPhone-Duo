import fs from "node:fs";
import assert from "node:assert/strict";

const source=fs.readFileSync(new URL("../chrome_checkout_flow.js",import.meta.url),"utf8");
const start=source.indexOf("  const appleHost = url => {");
const end=source.indexOf("  const clickUnique =",start);
assert.ok(start > 0 && end > start,"Security check section exists");
const check=new Function("page",source.slice(start,end)+"\nreturn stopOnChallenge();");

function fakePage({values=["Apple shopping options"],domain="www.apple.com",evaluateAvailable=true}={}) {
  let count=0,waits=0,currentDomain=domain,urls=0;
  const page={
    url(){urls++;return "https://"+currentDomain+"/shop/buy-iphone/iphone-duo";},
    async evaluate(fn){
      const value=values[Math.min(count++,values.length-1)];
      if(value instanceof Error) throw value;
      if(value==="navigate") currentDomain="malicious.example";
      const content=value==="navigate"?"Apple shopping options":value;
      const old=globalThis.document;
      globalThis.document={title:"Apple",body:content===null?null:{innerText:content}};
      try{return fn();}finally{globalThis.document=old;}
    },
    async waitForTimeout(ms){assert.equal(ms,600);waits++;}
  };
  if(!evaluateAvailable)delete page.evaluate;
  return {page,get reads(){return count;},get waits(){return waits;},get urlChecks(){return urls;}};
}
const ok=fakePage();
await check(ok.page);
assert.equal(ok.reads,1);
assert.equal(ok.waits,0);
assert.ok(ok.urlChecks>=2);

const transient=fakePage({values:[new Error("temporary render"),"Apple Store"]});
await check(transient.page);
assert.equal(transient.reads,2);
assert.equal(transient.waits,1);

const empty=fakePage({values:[null,"Apple Store"]});
await check(empty.page);
assert.equal(empty.waits,1);

const persist=fakePage({values:[new Error("detached body")]});
await assert.rejects(check(persist.page),/challenge_page_unreadable/);
assert.equal(persist.reads,3,"unreadable page must fail closed");

const captcha=fakePage({values:["Please complete a CAPTCHA to continue"]});
await assert.rejects(check(captcha.page),/human_verification_required/);
assert.equal(captcha.reads,1,"never retry through CAPTCHA");

const challenge=fakePage({values:["Checking your browser before continuing"]});
await assert.rejects(check(challenge.page),/human_verification_required/);

const wrongHost=fakePage({domain:"malicious.example"});
await assert.rejects(check(wrongHost.page),/outside_apple/);
assert.equal(wrongHost.reads,0);

const moved=fakePage({values:["navigate"]});
await assert.rejects(check(moved.page),/outside_apple/);

const unsupported=fakePage({evaluateAvailable:false});
await assert.rejects(check(unsupported.page),/challenge_eval_unavailable/);

console.log("Browser-local challenge verdict tests passed; blocked challenges remain fail-closed.");
