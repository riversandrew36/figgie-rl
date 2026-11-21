// Dev by default. Freeze and commit profiles before passing --held-out.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { arena, loadBrowser } = require('./browser_harness.cjs');

const revision = 'a852c79562f59dd3b63dd192e0998105fd557f09';
const names = ['Hunter', 'Banker', 'Detective', 'Bluffer'];
const beginner = names.map((name, strategy) => ({
  name: `Rookie ${name}`, strategy, tier: 'beginner',
  profile: { actRate: 0.45, valueNoise: 1, usesTape: false, edgeThreshold: 7, quoteWidth: 8, potWeight: 2 },
}));
const intermediate = names.map((name, strategy) => ({ name, strategy, tier: 'intermediate' }));
const advanced = [
  ['Expert Hunt', 0.14, 0.45],
  ['Expert Bank', 0.12, 0.85],
  ['Expert Scout', 0.18, 0.65],
  ['Expert Flow', 0.22, 0.65],
].map(([name, tapeWeight, inventorySkew]) => ({
  name, strategy: 4, tier: 'advanced',
  profile: { actRate: 1, valueNoise: 0, usesTape: true, edgeThreshold: 2, quoteWidth: 2, potWeight: 0.8, tapeWeight, inventorySkew },
}));
const lineups = { beginner, intermediate, advanced };
const means = (values) => values.reduce((sum, value) => sum + value, 0) / values.length;
function interval(values) {
  const mean = means(values);
  const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
  const half = 1.96 * Math.sqrt(variance / values.length);
  return [mean, mean - half, mean + half].map((value) => Number(value.toFixed(4)));
}
function simulate(subjects, opponents, seeds, marketMode = 'players') {
  const context = loadBrowser();
  if (process.argv.includes('--policy')) {
    const file = process.argv[process.argv.indexOf('--policy') + 1];
    vm.runInContext(fs.readFileSync(file, 'utf8'), context);
  }
  context.settings = { subjects, opponents, seeds, marketMode };
  return vm.runInContext(`(() => {
    const {subjects, opponents, seeds, marketMode} = settings;
    return subjects.map(subject => Array.from({length:seeds[1]-seeds[0]+1}, (_, offset) => {
      const round = new FiggieViewerGame();
      round.reset(60000, seeds[0]+offset, {marketMode,playerSpecs:[subject,...opponents]});
      const end = marketMode === "lab" ? 120 : 240;
      for (; round.tick < end; round.tick++) {
        round.elapsedMs = round.tick * round.tickMs;
        if (marketMode === "lab") round.runLabTurn();
        else {
          round.ageAndExpireQuotes();
          for (let i=0;i<4;i++) if (!round.players[i].isHuman) round.applyAction(i,round.pickAction(i));
        }
      }
      round.settleRound();
      return round.players[0].cash - round.startingCash;
    }));
  })()`, context);
}
function assess(seeds, market = 'players', trained = null) {
  const reference = intermediate.slice(0, 3);
  const candidates = [...intermediate, ...beginner, ...advanced,
    {name:'Hold', isHuman:true}, {name:'Random', strategy:'random'}, ...(trained ? [trained] : [])];
  const values = simulate(candidates, reference, seeds, market);
  const best = intermediate.reduce((a, _, i) => means(values[i]) > means(values[a]) ? i : a, 0);
  const hold = values[12];
  const random = values[13];
  const paired = (a, b) => interval(a.map((value, i) => value - b[i]));
  const rows = Object.fromEntries(candidates.map((bot, i) => {
    const base = i < 12 ? values[i % 4] : values[best];
    return [bot.name, {profit:interval(values[i]), vsBase:paired(values[i],base), vsBest:paired(values[i],values[best]), vsHold:paired(values[i],hold)}];
  }));
  return { seeds, best: intermediate[best].name, rows,
    advancedPass: advanced.every(bot => rows[bot.name].vsBest[1] > 0),
  };
}

function qualifiesBeginner(block, bot) {
  return block.rows[bot.name].vsBase[2] < 0 && block.rows[bot.name].profit[0] > block.rows.Random.profit[0];
}

function addNovice(block, lineup) {
  const novice = {name:'Novice proxy', strategy:'novice'};
  const [rookie] = simulate([novice], lineup.slice(0,3), block.seeds);
  const [reference] = simulate([novice], intermediate.slice(0,3), block.seeds);
  const paired = interval(rookie.map((value, i) => value - reference[i]));
  block.novice = {beginner:interval(rookie), intermediate:interval(reference), paired};
  block.beginnerPass = lineup.length >= 3 && lineup.every(bot => qualifiesBeginner(block, bot)) && paired[1] > 0;
}

function main() {
  const heldOutUsed = process.argv.includes('--held-out') || process.argv.includes('--check');
  const results = {revision, heldOutUsed, market:'players', lineups,
    development:assess([1,400])};
  if (heldOutUsed) {
    results.heldOut = assess([900000,900399]);
    // Eligibility is evaluated once on held-out seeds. No profiles are
    // changed, refit, or replaced after seeing those deals.
    results.lineups = {...lineups, beginner: beginner.filter(bot => qualifiesBeginner(results.heldOut, bot))};
  }
  if (results.lineups.beginner.length < 3) throw Error("Fewer than three Rookie profiles qualified");
  addNovice(results.development, results.lineups.beginner);
  if (heldOutUsed) addNovice(results.heldOut, results.lineups.beginner);
  if (process.argv.includes('--policy')) {
    const file = process.argv[process.argv.indexOf('--policy') + 1];
    const context = loadBrowser();
    vm.runInContext(fs.readFileSync(file,'utf8'),context);
    const id = vm.runInContext('Object.keys(figgiePolicies)[0]',context);
    const lab = assess(heldOutUsed ? [900000,900399] : [1,400], 'lab', {name:id,policyId:id});
    console.log(JSON.stringify({players:results, lab:{market:'lab', heldOutUsed, candidates:lab.rows, best:lab.best,
      eligibleAdvanced:heldOutUsed && lab.rows[id].vsBest[1] > 0, promoted:false}}, null, 2));
    return;
  }
  const compact = JSON.stringify(results);
  const file = path.join(arena,'tier_ratings.json');
  const htmlFile = path.join(arena,'figgie_play.html');
  const marker = /(<script type="application\/json" id="tierRatingsData">)[^<]*(<\/script>)/;
  if (process.argv.includes('--write')) {
    if (!heldOutUsed) throw Error('--write requires --held-out');
    fs.writeFileSync(file,compact+'\n');
    const html = fs.readFileSync(htmlFile,'utf8');
    if (!marker.test(html)) throw Error('Missing tier snapshot marker');
    fs.writeFileSync(htmlFile,html.replace(marker,(_, start,end)=>start+compact+end));
  }
  if (process.argv.includes('--check')) {
    const committed = JSON.parse(fs.readFileSync(file,'utf8'));
    const check = (a,b,key='') => {
      if (typeof a === 'number') {
        if (typeof b !== 'number' || Math.abs(a-b)>0.0002) throw Error(`Stale value ${key}: ${a} != ${b}`);
      } else if (a && typeof a === 'object') {
        if (JSON.stringify(Object.keys(a)) !== JSON.stringify(Object.keys(b))) throw Error(`Stale keys ${key}`);
        for (const name of Object.keys(a)) check(a[name],b[name],key+'.'+name);
      } else if (a !== b) throw Error(`Stale field ${key}`);
    };
    check(results,committed);
    const embedded = fs.readFileSync(htmlFile,'utf8').match(marker)?.[0].slice(markerStart.length,-9);
    if (embedded !== JSON.stringify(committed)) throw Error('Stale inline tier snapshot');
  }
  console.log(JSON.stringify(results,null,2));
}
const markerStart = '<script type="application/json" id="tierRatingsData">';
if (require.main === module) main();
