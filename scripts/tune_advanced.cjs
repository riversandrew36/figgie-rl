// Searches development and validation ranges only. No held-out imports.
const fs = require('node:fs');
const { simulate, interval, means, lineups } = require('./rate_bots.cjs');

const dev = [1, 400];
const validation = [500000, 500399];
const reference = lineups.intermediate.slice(0, 3);
function score(subjects, seeds) {
  const profits = simulate([...lineups.intermediate, ...subjects], reference, seeds);
  const bestIndex = lineups.intermediate.reduce((a, _, i) => means(profits[i]) > means(profits[a]) ? i : a, 0);
  return { seeds, bestIntermediate: lineups.intermediate[bestIndex].name, candidates: subjects.map((subject, i) => ({
    ...subject,
    vsBest: interval(profits[i + 4].map((profit, j) => profit - profits[bestIndex][j])),
  })).sort((a,b) => b.vsBest[0] - a.vsBest[0]) };
}
function grid() {
  const candidates = [];
  // Cross thresholds/widths with three distinct activity budgets, with
  // moderate widening throughout. Keep the search small and reproducible.
  for (const edgeThreshold of [0.5, 2, 4]) {
    for (const quoteWidth of [1, 4]) {
      for (const [actionCap, quoteEvery] of [[60,5],[115,2],[205,1]]) {
        candidates.push({name:`Trial ${candidates.length+1}`, strategy:5, tier:'advanced', profile:{
          edgeThreshold, quoteWidth, actionCap, quoteEvery, widening:0.5, endgame:0.85, dumpOdds:0.03,
        }});
      }
    }
  }
  return candidates;
}
function main() {
  const development = score(grid(), dev);
  const held = score(development.candidates.slice(0,5).map(({vsBest, ...subject}) => subject), validation);
  const names = ['Analyst Edge', 'Analyst Patience', 'Analyst Flow', 'Analyst Anchor'];
  const finalists = held.candidates.slice(0,4).map((row, i) => ({
    ...row, trial:row.name, name:names[i],
    development:development.candidates.find(candidate => candidate.name === row.name).vsBest,
  }));
  const result = {development, validation:held, finalists};
  if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(result, null, 2)+'\n');
  console.log(JSON.stringify(result, null, 2));
}
if (require.main === module) main();
