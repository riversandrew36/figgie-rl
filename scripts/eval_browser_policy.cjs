// Run the existing Lab matching engine headlessly with the released actors.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const { arena, loadBrowser } = require('./browser_harness.cjs');
const context = loadBrowser(['policies/ppo_goal_shown.js', 'policies/ppo_no_aids.js']);

const results = vm.runInContext(`(() => {
  const subjects = [
    ...Object.entries(PPO_SEATS).map(([policyId, name]) => ({name, policyId})),
    {name: "Hold", isHuman: true},
    ...BOT_NAMES.map((name, strategy) => ({name, strategy})),
  ];
  const opponents = BOT_NAMES.slice(0,3).map((name, strategy) => ({name, strategy}));
  return subjects.map(subject => {
    const profits = [];
    for (let seed = 1; seed <= 200; seed += 1) {
      const round = new FiggieViewerGame();
      round.reset(60000, seed, {marketMode:"lab", playerSpecs:[subject, ...opponents]});
      for (; round.tick < LAB_STEPS; round.tick += 1) round.runLabTurn();
      round.settleRound();
      profits.push(round.players[0].cash - round.startingCash);
    }
    const n = profits.length;
    const mean = profits.reduce((a,b)=>a+b,0)/n;
    const variance = profits.reduce((a,b)=>a+(b-mean)**2,0)/(n-1);
    const halfWidth = 1.96 * Math.sqrt(variance/n);
    return {name:subject.name, n, mean, low:mean-halfWidth, high:mean+halfWidth};
  });
})()`, context);
// The checked-in snapshot also lets the research page work from file://.
const rounded = results.map((row) => ({
  name: row.name, mean: row.mean.toFixed(2), low: row.low.toFixed(2), high: row.high.toFixed(2),
}));
const file = path.join(arena, 'figgie_play.html');
const marker = /(<script type="application\/json" id="labBenchmarkData">)[^<]*(<\/script>)/;
const html = fs.readFileSync(file, 'utf8');
if (!marker.test(html)) throw Error('Missing Lab benchmark snapshot marker');
const next = html.replace(marker, (_, start, end) => start + JSON.stringify(rounded) + end);
if (process.argv.includes('--write')) fs.writeFileSync(file, next);
if (process.argv.includes('--check') && html !== next) throw Error('Stale Lab benchmark snapshot');

console.log('Browser Lab, seeds 1–200 · chips per round · normal-approximation 95% intervals');
for (const row of results) {
  console.log(`${row.name.padEnd(20)} ${row.mean.toFixed(2).padStart(7)}  [${row.low.toFixed(2)}, ${row.high.toFixed(2)}]`);
}
