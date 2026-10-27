// Behavioral offline tests for the real AppleCare chooser, using simulated
// HTML labels and linked radio inputs. No browsing, account or purchases.
import fs from 'node:fs';
import assert from 'node:assert/strict';

const source=fs.readFileSync(new URL('../chrome_checkout_flow.js', import.meta.url),'utf8');
const start=source.indexOf('  const chooseNoAppleCare = async () => {');
const end=source.indexOf('  const findReview = async () => {',start);
assert.ok(start>=0 && end>start,'missing chooser');
const factory=new Function('page','stopOnChallenge','let operation="test";\n'+source.slice(start,end)+'\nreturn chooseNoAppleCare();');

function makeLabel(name,{checked=false,linked=true,extra='',childTitle=false}={}) {
  const control=linked?{type:'radio',get checked(){return checked;},set checked(value){checked=value;}}:null;
  const title={innerText:name};
  return {
    innerText:extra ? name+' '+extra : name,
    control,
    querySelector(){return null;},
    htmlFor: '',
    getClientRects(){return [1];},
    querySelectorAll(selector){
      if(selector==='h1,h2,h3,h4,span,strong,p,div')return childTitle?[title]:[];
      return [];
    }
  };
}
function fixture({labels=[makeLabel('No AppleCare coverage')],delay=0,acceptClick=true,challenge=false}={}) {
  let ticks=0,clicked=0,checks=0;
  const page={
    evaluate:async function(fn) {
      const old=globalThis.document;
      globalThis.document={
        querySelectorAll(selector){
          assert.equal(selector,'label');
          return ticks>=delay?labels:[];
        },
        getElementById(){return null;}
      };
      try {return fn();} finally {globalThis.document=old;}
    },
    locator(selector) {
      assert.equal(selector,'label');
      return {nth(index){return {
        async click({timeout}){
          assert.equal(timeout,7000);
          const label=labels[index];
          assert.ok(label);
          clicked++;
          if(acceptClick && label.control)label.control.checked=true;
        }
      }}};
    },
    async waitForTimeout(ms){assert.ok(ms===500||ms===300);ticks++;}
  };
  return {page,guard:async()=>{checks++;if(challenge)throw Error('human_verification_required')},
    get clicked(){return clicked},get checks(){return checks},get ticks(){return ticks},
    labels
  };
}
const noCare=fixture();
assert.equal(await factory(noCare.page,noCare.guard),true,'select no coverage');
assert.equal(noCare.clicked,1);
assert.equal(noCare.labels[0].control.checked,true);
assert.ok(noCare.checks>=2);

const already=fixture({labels:[makeLabel('No AppleCare coverage',{checked:true})]});
assert.equal(await factory(already.page,already.guard),true);
assert.equal(already.clicked,0,'do not toggle already selected radio');

const rendered=fixture({delay:4});
assert.equal(await factory(rendered.page,rendered.guard),true);
assert.ok(rendered.ticks>=4,'wait for dynamic layout');

const decorated=fixture({labels:[makeLabel('No AppleCare coverage',{extra:'No added monthly protection',childTitle:true})]});
assert.equal(await factory(decorated.page,decorated.guard),true);

const paid=fixture({labels:[makeLabel('AppleCare+ with Theft and Loss')]});
assert.equal(await factory(paid.page,paid.guard),false,'paid coverage is NOT no-coverage');
assert.equal(paid.clicked,0);

const ambiguous=fixture({labels:[makeLabel('No AppleCare coverage'),makeLabel('No AppleCare coverage')]});
await assert.rejects(factory(ambiguous.page,ambiguous.guard),/no_applecare_control_ambiguous/);
assert.equal(ambiguous.clicked,0);

const unlinked=fixture({labels:[makeLabel('No AppleCare coverage',{linked:false})]});
await assert.rejects(factory(unlinked.page,unlinked.guard),/no_applecare_selection_unverified/);

const unverified=fixture({acceptClick:false});
await assert.rejects(factory(unverified.page,unverified.guard),/no_applecare_selection_unverified/);

const blocked=fixture({challenge:true});
await assert.rejects(factory(blocked.page,blocked.guard),/human_verification_required/);
assert.equal(blocked.clicked,0,'do not click past human verification');

assert.ok(source.includes("if (page.url().replace(/\\/$/, '') !== cfg.url.replace(/\\/$/, ''))"),"should not reload matching product tab");
console.log('AppleCare DOM-label chooser tests passed: exact, pending, duplicate, paid, verification, and no reload.');
