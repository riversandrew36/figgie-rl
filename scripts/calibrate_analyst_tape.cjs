// Fit discrete likelihoods on half the development deals and score probabilities
// on the other half. Use no validation or held-out deals for this calibration.
const { simulate, lineups } = require('./rate_bots.cjs');

function tapeSamples(round) {
  const prior = goalSuitPosterior(round.players[0].initialInventory);
  const flow = [0,0,0,0];
  let index = 0;
  return [80,160,239].map(tick => {
    while (index < round.roundLog.length && round.roundLog[index].tick < tick) {
      const trade = round.roundLog[index++];
      const buy = trade.aggressorSide === 'buy';
      if ((buy ? trade.buyerIdx : trade.sellerIdx) !== 0) flow[trade.suit] += buy ? 1 : -1;
    }
    return {prior, goal:round.goalSuitIdx, bins:flow.map(value=>Math.max(-2,Math.min(2,value))+2)};
  });
}

function checkTape() {
  const opponents = lineups.intermediate.slice(0,3);
  const sample = seeds => simulate([{name:'Hold',isHuman:true}], opponents, seeds, 'players', tapeSamples)[0].flat();
  const goal = [1,1,1,1,1];
  const nonGoal = [1,1,1,1,1];
  for (const row of sample([1,200])) {
    row.bins.forEach((bin,suit) => (suit === row.goal ? goal : nonGoal)[bin]++);
  }
  const sum = xs => xs.reduce((a,b)=>a+b,0);
  const likelihood = goal.map((count, i) => (count / sum(goal)) / (nonGoal[i] / sum(nonGoal)));
  let priorLoss = 0;
  let adjustedLoss = 0;
  const test = sample([201,400]);
  for (const row of test) {
    const adjusted = row.prior.map((p,suit)=>p * likelihood[row.bins[suit]]);
    const normalizer = sum(adjusted);
    row.prior.forEach((p,suit)=>{
      const truth = Number(suit === row.goal);
      priorLoss += (p-truth)**2;
      adjustedLoss += (adjusted[suit]/normalizer-truth)**2;
    });
  }
  return {fit:[1,200], score:[201,400], likelihood,
    handBrier:priorLoss/test.length, adjustedBrier:adjustedLoss/test.length};
}
if (require.main === module) console.log(JSON.stringify(checkTape(),null,2));
