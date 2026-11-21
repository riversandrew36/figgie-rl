// Searches development and validation ranges only. No held-out imports.
const fs = require('node:fs');
const { simulate, interval, means, lineups, analysts } = require('./rate_bots.cjs');

const dev = [1, 400];
const validation = [520000, 520399];
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
  const candidates = [...analysts];
  for (const edgeThreshold of [0.5, 2, 4]) {
    for (const [quoteWidth, quoteEvery, actionCap] of [[1,3,90],[4,5,60],[7,5,60]]) {
      for (const liveWeight of [0.5, 1]) {
        candidates.push({name:`Tracked ${candidates.length - analysts.length + 1}`, strategy:6, tier:'advanced', profile:{
          edgeThreshold, quoteWidth, actionCap, quoteEvery, widening:0.5, endgame:0.85, liveWeight,
          useTrackedOdds:true,
        }});
      }
    }
  }
  return candidates;
}
function extraChecks() {
  const seeds = validation;
  const hold = {name:'Hold',isHuman:true};
  const pair = (first, second) => interval(first.map((value,i) => value-second[i]));
  const rivals = [...lineups.intermediate, ...lineups.advanced, hold];
  const beginner = simulate(rivals, lineups.beginner, seeds);
  const best = lineups.intermediate.reduce((a,_,i) =>
    means(beginner[i]) > means(beginner[a]) ? i : a, 0);
  const strategists = lineups.advanced.filter(bot => bot.strategy === 6);
  const trio = strategists.length >= 3 ? strategists.slice(0,3) : grid().filter(bot => bot.strategy === 6).slice(0,3);
  const [bluffer, blufferControl] = simulate([lineups.intermediate[3],hold], trio, seeds);
  return {seeds, blufferTable:{lineup:trio.map(bot=>bot.name), profit:interval(bluffer), vsHold:pair(bluffer,blufferControl)}, beginnerReference:lineups.intermediate[best].name,
    rows:lineups.advanced.map((subject,i) => {
      const opponents = lineups.advanced.filter(bot=>bot !== subject);
      const [allAdvanced, reference] = simulate([subject,hold], opponents, seeds);
      return {name:subject.name, allAdvanced:interval(allAdvanced),
        allAdvancedHold:interval(reference), allAdvancedVsHold:pair(allAdvanced,reference),
        beginnerProfit:interval(beginner[4+i]),
        beginnerVsHold:pair(beginner[4+i],beginner.at(-1)),
        beginnerVsBest:pair(beginner[4+i],beginner[best])};
    }),
  };
}

function main() {
  if (process.argv.includes("--extra")) {
    console.log(JSON.stringify(extraChecks(), null, 2));
    return;
  }
  const development = score(grid(), dev);
  const held = score(development.candidates.slice(0,8).map(({vsBest, ...subject}) => subject), validation);
  const names = ['Strategist Hold', 'Strategist Press', 'Strategist Read', 'Strategist Close'];
  const finalists = held.candidates.slice(0,4).map((row, i) => ({
    ...row, trial:row.name, name:names[i],
    development:development.candidates.find(candidate => candidate.name === row.name).vsBest,
  }));
  const result = {development, validation:held, finalists};
  if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(result, null, 2)+'\n');
  console.log(JSON.stringify(result, null, 2));
}
if (require.main === module) main();
