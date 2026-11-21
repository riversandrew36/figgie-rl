// Development only: use the actual goal to score predictions offline.
const {simulate, interval, means, lineups, analysts} = require('./rate_bots.cjs');

function measure(round) {
  const goal = round.goalSuitIdx;
  const tape = round.roundLog;
  const hand = goalSuitPosterior(round.players[0].initialInventory);
  const brier = odds => odds.reduce((sum, p, suit) => sum + (p - Number(suit === goal)) ** 2, 0);
  const score = [80,160,239].map(tick => {
    round.roundLog = tape.filter(trade => trade.tick < tick);
    return brier(round.strategistBelief(0).odds);
  });
  round.roundLog = tape;
  return [brier(hand), score.reduce((a,b)=>a+b,0)/score.length];
}
const seeds = [1,400];
const subjects = [analysts[0], {name:'Hold',isHuman:true}];
const rows = simulate(subjects, lineups.intermediate.slice(0,3), seeds, 'players', measure);
console.log(JSON.stringify({seeds, rows:subjects.map((bot,i)=>({
  name:bot.name, hand:means(rows[i].map(row=>row[0])), tracked:means(rows[i].map(row=>row[1])),
  paired:interval(rows[i].map(([hand,tracked])=>tracked-hand)),
}))},null,2));
