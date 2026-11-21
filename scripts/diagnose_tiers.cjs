// Development only. Measure each subject on the same deals as Intermediate.
const { simulate, interval, means, lineups, analysts } = require('./rate_bots.cjs');

function measure(round) {
  const player = round.players[0];
  const ownTrades = round.roundLog.filter(t => t.buyerIdx === 0 || t.sellerIdx === 0);
  const goalTrades = ownTrades.filter(t => t.suit === round.goalSuitIdx);
  const buckets = { buyTake: [], buyMake: [], sellTake: [], sellMake: [] };
  for (const trade of ownTrades) {
    const buy = trade.buyerIdx === 0;
    const took = (trade.aggressorSide === 'buy') === buy;
    const value = trade.suit === round.goalSuitIdx ? round.goalCardValue : 0;
    buckets[(buy ? 'buy' : 'sell') + (took ? 'Take' : 'Make')].push((buy ? 1 : -1) * (value - trade.price));
  }
  const majority = round.winnerIdxs.includes(0);
  const profit = player.cash - round.startingCash;
  if (Math.abs(profit - (player.tradingCashflow + player.goalCardPayout + player.majorityPayout - round.ante)) > 1e-8) {
    throw Error('Profit decomposition failed');
  }
  const goalCount = player.inventory[round.goalSuitIdx];
  const lead = Math.max(...round.players.slice(1).map(p => p.inventory[round.goalSuitIdx]));
  let count = player.initialInventory[round.goalSuitIdx];
  let reached = count === goalCount ? 0 : null;
  for (const trade of goalTrades) {
    count += trade.buyerIdx === 0 ? 1 : -1;
    if (reached === null && count === goalCount) reached = trade.tick;
  }
  const prior = goalSuitPosterior(player.initialInventory);
  const favorite = round.argmax(prior);
  const decoy = round.argmin(prior.map((p, suit) => suit === favorite ? Infinity : p));
  const earlyBuys = ownTrades.filter(t => t.tick < 72 && t.buyerIdx === 0 && t.aggressorSide === 'buy');
  const decoyBuys = earlyBuys.filter(t => t.suit === decoy);
  const followed = earlyBuys.filter(trade => {
    const start = round.roundLog.indexOf(trade);
    return round.roundLog.slice(start + 1).some(t => t.tick <= trade.tick + 8 &&
      t.suit === trade.suit && t.buyerIdx !== 0 && t.aggressorSide === 'buy');
  });
  return {
    profit, cash: player.tradingCashflow, goal: player.goalCardPayout, majority: player.majorityPayout,
    trades: ownTrades.length, goalShare: ownTrades.length ? goalTrades.length / ownTrades.length : 0,
    goalCount, loss: Number(!majority), oneShort: Number(goalCount === lead - 1),
    reached, goalSells: goalTrades.filter(t => t.sellerIdx === 0).length,
    earlyBuys: earlyBuys.length, earlyDecoys: decoyBuys.length,
    earlyGoalBuys: earlyBuys.filter(t => t.suit === round.goalSuitIdx).length,
    followed: followed.length,
    followedDecoys: followed.filter(t => t.suit === decoy).length,
    win: Number(majority && round.winnerIdxs.length === 1),
    tie: Number(majority && round.winnerIdxs.length > 1),
    ...Object.fromEntries(Object.entries(buckets).map(([key, values]) =>
      [key, values.length ? values.reduce((a,b)=>a+b,0)/values.length : 0])),
  };
}
function diagnose(count = 400) {
  if (!Number.isInteger(count) || count < 2 || count > 400) throw Error('Use 2–400 development seeds');
  const subjects = [...lineups.intermediate, ...analysts];
  const rounds = simulate(subjects, lineups.intermediate.slice(0,3), [1,count], 'players', measure);
  const best = lineups.intermediate.reduce((a,_,i) =>
    means(rounds[i].map(row=>row.profit)) > means(rounds[a].map(row=>row.profit)) ? i : a, 0);
  return { seeds:[1,count], ante:50, best:subjects[best].name,
    rows: Object.fromEntries(subjects.map((subject,i) => [subject.name,
      Object.fromEntries(Object.keys(rounds[i][0]).map(key => {
        const values = rounds[i].map(row => row[key]);
        return [key, {mean:means(values), paired:interval(values.map((value,j)=>value-rounds[best][j][key]))}];
      }))])) };
}
module.exports = { diagnose };
if (require.main === module) console.log(JSON.stringify(diagnose(Number(process.argv[2] || 400)), null, 2));
