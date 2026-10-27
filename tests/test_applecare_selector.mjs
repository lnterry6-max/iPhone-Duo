// Offline tests only: extract the real chooseNoAppleCare function from the
// Chrome checkout template and simulate visible Apple Store radio/label controls.
import fs from 'node:fs';
import assert from 'node:assert/strict';

const source = fs.readFileSync(new URL('../chrome_checkout_flow.js', import.meta.url), 'utf8');
const begin = source.indexOf('  const chooseNoAppleCare = async () => {');
const end = source.indexOf('  const findReview = async () => {', begin);
assert.ok(begin > 0 && end > begin, 'Cannot locate AppleCare code');
const selectorCode = source.slice(begin, end);
const choose = new Function('page', 'stopOnChallenge', 'let operation="start";\n' + selectorCode + '\nreturn chooseNoAppleCare();');

function fakePage({initialSelected=false, visibleAfter=0, allowSelect=true, labeled=true, ambiguous=false}={}) {
  let selected = initialSelected;
  let waits = 0, clicks = 0, matcher;
  const label = {
    count: async () => waits >= visibleAfter ? 1 : 0,
    isVisible: async () => true,
    evaluate: async fn => fn({control:{get checked(){return selected;}}}),
    click: async () => { clicks++; if (allowSelect) selected = true; }
  };
  const control = {
    count: async () => ambiguous ? 2 : ((labeled && waits >= visibleAfter) ? 1 : 0),
    isChecked: async () => selected,
    check: async () => {clicks++; if (allowSelect) selected=true;}
  };
  return {
    page: {
      locator: selector => {
        assert.equal(selector, 'label');
        return {filter:({hasText}) => {matcher=hasText;return label;}};
      },
      getByLabel: (pattern) => { matcher=pattern; return control; },
      waitForTimeout: async ms => {assert.equal(ms,500);waits++;}
    },
    get waits(){return waits;},
    get clicks(){return clicks;},
    get selected(){return selected;},
    get matcher(){return matcher;}
  };
}

const stopOnChallenge = async () => {};
const delayed = fakePage({visibleAfter:3});
assert.equal(await choose(delayed.page, stopOnChallenge), true, 'should select visible option after late rendering');
assert.equal(delayed.clicks,1);
assert.equal(delayed.selected,true);
assert.ok(delayed.waits >= 3);
assert.ok(delayed.matcher.test('No AppleCare coverage'));
assert.ok(delayed.matcher.test('No AppleCare+ coverage'));
assert.equal(delayed.matcher.test('AppleCare+ with Theft and Loss'),false);

const already = fakePage({initialSelected:true});
assert.equal(await choose(already.page,stopOnChallenge),true);
assert.equal(already.clicks,0,'already selected option should not be clicked');

const absent = fakePage({visibleAfter:999});
assert.equal(await choose(absent.page,stopOnChallenge),false,'absent option must fail closed');
assert.equal(absent.clicks,0);

const fallback = fakePage({labeled:false});
assert.equal(await choose(fallback.page,stopOnChallenge),true,'exact label fallback should work');
assert.equal(fallback.selected,true);

const duplicate = fakePage({ambiguous:true});
await assert.rejects(choose(duplicate.page,stopOnChallenge), /no_applecare_control_ambiguous/);

const unverified = fakePage({allowSelect:false});
await assert.rejects(choose(unverified.page,stopOnChallenge), /no_applecare_selection_unverified/);

console.log('AppleCare chooser offline tests passed (delayed, selected, missing, unverified).');
