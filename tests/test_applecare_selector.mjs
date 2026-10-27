// Tests exercise the real no-AppleCare chooser with simulated DOM and native
// Playwright-like clicks. No Apple requests, account data or purchases.
import fs from 'node:fs';
import assert from 'node:assert/strict';

const source=fs.readFileSync(new URL('../chrome_checkout_flow.js',import.meta.url),'utf8');
const a=source.indexOf('  const chooseNoAppleCare = async () => {');
const b=source.indexOf('  const findReview = async () => {',a);
assert.ok(a>0 && b>a,'chooser section present');
const choose=new Function('page','stopOnChallenge','let operation="test";\n'+source.slice(a,b)+'\nreturn chooseNoAppleCare();');

function makeLabel(title,{checked=false,linked=true,extra='',childTitle=false}={}){
  const control=linked?{type:'radio',get checked(){return checked;},set checked(v){checked=v;}}:null;
  return {
    innerText:title+(extra?' '+extra:''),
    control,
    querySelector(){return null;},
    getClientRects(){return [1];},
    htmlFor:'',
    querySelectorAll(selector) {
      if(selector==='h1,h2,h3,h4,span,strong,p,div')
        return childTitle?[{innerText:title}]:[];
      return [];
    }
  };
}
function fixture({labels=[makeLabel('No AppleCare coverage')],delay=0,
                  rejectText=false,rejectLabel=false,rejectInput=false,
                  acceptClick=true,challenge=false,disabled=false}={}){
  let ticks=0,clicks=0,attemptText=0,attemptLabel=0;
  const norm=str=>String(str).replace(/\s+/g,' ').trim();
  const labelClick=index=>({
    scrollIntoViewIfNeeded:async({timeout})=>{assert.equal(timeout,3500);},
    click:async({timeout})=>{
      assert.equal(timeout,4000);
      attemptLabel++;
      if(rejectLabel)throw Error('Element is outside viewport');
      clicks++;
      if(acceptClick && labels[index]?.control)labels[index].control.checked=true;
    }
  });
  const textTarget=pattern=>({
    count:async()=>labels.filter(x=>pattern.test(norm(x.innerText))).length,
    isVisible:async()=>true,
    scrollIntoViewIfNeeded:async({timeout})=>{assert.equal(timeout,3500);},
    click:async({timeout})=>{
      assert.equal(timeout,4000);
      attemptText++;
      if(rejectText)throw Error('Element is not stable');
      const index=labels.findIndex(x=>pattern.test(norm(x.innerText)));
      assert.ok(index>=0,'exact no-coverage target exists');
      clicks++;
      if(acceptClick && labels[index]?.control)labels[index].control.checked=true;
    }
  });
  const inputs=labels.map(x=>x.control).filter(Boolean);
  for(const input of inputs){
    input.disabled=disabled;
    input.closest=()=>null;
  }
  const page={
    evaluate:async function(fn){
      const old=globalThis.document;
      globalThis.document={
        querySelectorAll(selector){
          if(selector==='label')return ticks>=delay?labels:[];
          if(selector==='input[type="radio"], input[type="checkbox"]')return ticks>=delay?inputs:[];
          throw Error('unexpected DOM selector '+selector);
        },
        getElementById(){return null;}
      };
      try{return fn();}finally{globalThis.document=old;}
    },
    locator(selector){
      if(selector==='label')return {nth(index){return labelClick(index)}};
      if(selector==='input[type="radio"],input[type="checkbox"]')return {
        nth(index){return {
          async check({timeout}){
            assert.equal(timeout,3500);
            if(rejectInput)throw Error('Radio input not actionable');
            clicks++;
            if(acceptClick&&inputs[index])inputs[index].checked=true;
          }
        }};
      };
      throw Error('unexpected Playwright locator: '+selector);
    },
    getByText(pattern,options){assert.equal(options.exact,true);return textTarget(pattern);},
    waitForTimeout:async ms=>{assert.ok([500,250].includes(ms));ticks++;}
  };
  return {page,guard:async()=>{if(challenge)throw Error('human_verification_required')},
    get clicks(){return clicks},get attemptText(){return attemptText},
    get attemptLabel(){return attemptLabel},get ticks(){return ticks},labels
  };
}

const matched=fixture();
assert.equal(await choose(matched.page,matched.guard),true,'exact No AppleCare coverage');
assert.equal(matched.labels[0].control.checked,true);
assert.equal(matched.attemptText,0);
assert.equal(matched.attemptLabel,0);
assert.equal(matched.clicks,1);

const already=fixture({labels:[makeLabel('No AppleCare coverage',{checked:true})]});
assert.equal(await choose(already.page,already.guard),true);
assert.equal(already.clicks,0);

const deferred=fixture({delay:3});
assert.equal(await choose(deferred.page,deferred.guard),true);
assert.ok(deferred.ticks>=3);

const moreInfo=fixture({labels:[makeLabel('No AppleCare coverage',{extra:'No charge',childTitle:true})]});
assert.equal(await choose(moreInfo.page,moreInfo.guard),true,'label fallback if text contains details');
assert.equal(moreInfo.attemptLabel,0);

const clickFallback=fixture({rejectInput:true,rejectText:true});
assert.equal(await choose(clickFallback.page,clickFallback.guard),true,'native label click fallback');
assert.equal(clickFallback.attemptText,1);
assert.equal(clickFallback.attemptLabel,1);

const noVisible=fixture({labels:[makeLabel('AppleCare One')]});
assert.equal(await choose(noVisible.page,noVisible.guard),false,'no paid AppleCare substitution');
assert.equal(noVisible.clicks,0);

const duplicates=fixture({labels:[makeLabel('No AppleCare coverage'),makeLabel('No AppleCare coverage')]});
await assert.rejects(choose(duplicates.page,duplicates.guard),/no_applecare_control_ambiguous/);
assert.equal(duplicates.clicks,0);

const unlinked=fixture({labels:[makeLabel('No AppleCare coverage',{linked:false})]});
await assert.rejects(choose(unlinked.page,unlinked.guard),/no_applecare_selection_unverified/);

const failedBoth=fixture({rejectInput:true,rejectText:true,rejectLabel:true});
await assert.rejects(choose(failedBoth.page,failedBoth.guard),/no_applecare_click_failed/);
assert.equal(failedBoth.clicks,0);

const notSelected=fixture({rejectInput:true,acceptClick:false});
await assert.rejects(choose(notSelected.page,notSelected.guard),/no_applecare_click_failed/);

const disabled=fixture({disabled:true});
await assert.rejects(choose(disabled.page,disabled.guard),/no_applecare_option_disabled/);
assert.equal(disabled.clicks,0,'disabled radio must never be activated');

const blocked=fixture({challenge:true});
await assert.rejects(choose(blocked.page,blocked.guard),/human_verification_required/);
assert.equal(blocked.clicks,0);

assert.ok(source.includes("if (page.url().replace(/\\/$/, '') !== cfg.url.replace(/\\/$/, ''))"));
console.log('No AppleCare selector: exact, delayed, fallback, paid rejection, ambiguous, unverified, challenge tests passed.');
