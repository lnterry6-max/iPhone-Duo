import fs from "node:fs";
import assert from "node:assert/strict";

const source = fs.readFileSync(new URL("../chrome_checkout_flow.js", import.meta.url), "utf8");
const start = source.indexOf("  const appleHost = url => {");
const end = source.indexOf("  const clickUnique =", start);
assert.ok(start > 0 && end > start, "Safety check section exists");
const testSafety = new Function("page", source.slice(start, end) + "\nreturn stopOnChallenge();");

function fakePage({values=["Apple shopping options"], domain="www.apple.com"} = {}) {
  let count = 0, waits = 0;
  let currentDomain = domain;
  const page = {
    url() { return "https://" + currentDomain + "/shop/buy-iphone/iphone-duo"; },
    locator(selector) {
      assert.equal(selector, "body");
      return {
        async innerText({timeout}) {
          assert.equal(timeout, 4000);
          const value = values[Math.min(count++, values.length - 1)];
          if (value instanceof Error) throw value;
          if (value === "navigate") {
            currentDomain = "evil.example";
            return "Apple shopping page";
          }
          return value;
        }
      };
    },
    async waitForTimeout(value) {
      assert.equal(value, 600);
      waits++;
    }
  };
  return {page, get reads(){return count;}, get waits(){return waits;}};
}

const ok = fakePage();
await testSafety(ok.page);
assert.equal(ok.reads, 1);
assert.equal(ok.waits, 0);

const transient = fakePage({values:[new Error("temporary page re-render"), "Apple Store"]});
await testSafety(transient.page);
assert.equal(transient.reads, 2);
assert.equal(transient.waits, 1);

const persistent = fakePage({values:[new Error("detached body")]});
await assert.rejects(testSafety(persistent.page),/challenge_page_unreadable/);
assert.equal(persistent.reads, 3, "unreadable page fails after bounded reads");

const captcha = fakePage({values:["Please complete a CAPTCHA to continue"]});
await assert.rejects(testSafety(captcha.page),/human_verification_required/);
assert.equal(captcha.reads, 1, "never retry or suppress verification");

const wrongHost = fakePage({domain:"evil.example"});
await assert.rejects(testSafety(wrongHost.page),/outside_apple/);
assert.equal(wrongHost.reads, 0);

const moved = fakePage({values:["navigate"]});
await assert.rejects(testSafety(moved.page),/outside_apple/);

console.log("Chrome checkout challenge guard tests passed");
