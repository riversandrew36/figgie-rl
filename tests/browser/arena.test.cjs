const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function load(url = 'https://example.test/figgie-rl/') {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      value: id === 'speedSelect' ? '1' : id === 'durationSelect' ? '30000' : '7',
      addEventListener() {}, focus() {}, select() {},
    });
    return elements.get(id);
  };
  const context = vm.createContext({
    URL, console,
    document: { getElementById: element },
    window: { location: { href: url } },
    localStorage: { getItem() { throw Error('unavailable'); }, setItem() { throw Error('unavailable'); } },
    setInterval() { return 1; }, clearInterval() {},
  });
  vm.runInContext(fs.readFileSync('figgie_rl/arena/figgie_arena.js', 'utf8'), context);
  return { run: (code) => vm.runInContext(code, context), elements };
}
const plain = (value) => JSON.parse(JSON.stringify(value));

function finish(run, speed, step) {
  run(`game.start(30000, 7, ${speed});`);
  if (step) run('game.setPaused(true)');
  run(`while (game.running) game.step(${step});`);
  return plain(run('roundPayload(game)'));
}

test('same scenario has identical trades and payouts at all speeds and with single-step', () => {
  const baseline = finish(load().run, 1, false);
  for (const speed of [2, 4, 8]) assert.deepEqual(finish(load().run, speed, false), baseline);
  assert.deepEqual(finish(load().run, 1, true), baseline);
  assert.equal(baseline.schemaVersion, 3);
  assert.equal(baseline.simulationVersion, '2.0.0');
  assert.equal(baseline.marketMode, 'players');
  assert.equal(baseline.humanSeated, false);
  for (const player of baseline.players) {
    const p = player.payoutBreakdown;
    assert.ok(Math.abs(p.startingCash - p.ante + p.netTradingCashflow +
      p.goalCardPayout + p.majorityPayout - p.finalBankroll) < 1e-8);
    assert.equal(p.netProfit, p.finalBankroll - p.startingCash);
    assert.equal(player.initialInventory.reduce((a, b) => a + b), 10);
    assert.ok(Math.abs(player.initialGoalProbabilities.reduce((a, b) => a + b) - 1) < 1e-8);
  }
});

test('settlement distinguishes majority bonus from profit and splits ties correctly', () => {
  for (const counts of [[6, 2, 1, 1], [5, 5, 0, 0]]) {
    const { run } = load();
    run(`game.goalSuitIdx = 0; game.players.forEach((p, i) => {
      p.inventory = [${JSON.stringify(counts)}[i], 0, 0, 0]; p.cash = i === 2 ? 500 : 300;
    }); game.settleRound(); game.revealGoal = true; renderExplanation(game);`);
    const payouts = plain(run('game.players.map(p => payoutBreakdown(game, p))'));
    const max = Math.max(...counts);
    const leaders = counts.filter((count) => count === max).length;
    payouts.forEach((p, i) => {
      assert.equal(p.goalCardPayout, counts[i] * 10);
      assert.equal(p.majorityPayout, counts[i] === max ? 100 / leaders : 0);
    });
    assert.equal(payouts.reduce((a, p) => a + p.goalCardPayout + p.majorityPayout, 0), 200);
    assert.equal(run('document.getElementById("settlementExplanation").textContent.includes("Highest profit: Detective")'), true);
  }
});

test('URL parameters normalize invalid seeds/durations without starting a round', () => {
  for (const query of ['?seed=NaN&duration=1', '?seed=Infinity', '?seed=1.5', '?seed=', '?seed=9007199254740992']) {
    const { run } = load(`https://example.test/figgie-rl/${query}`);
    assert.equal(run('game.seed'), 7);
    assert.equal(run('game.durationMs'), 30000);
    assert.equal(run('game.running'), false);
  }
  const { run } = load('https://example.test/figgie-rl/?seed=-23&duration=60000&speed=8');
  assert.equal(run('game.seed'), -23);
  assert.equal(run('game.durationMs'), 60000);
  assert.equal(run('game.speed'), 1);
  assert.equal(run('scenarioUrl()'), 'https://example.test/figgie-rl/?seed=-23&duration=60000&market=classic&version=2.0.0');
});

test('unfinished exports explicitly omit settlement and leave existing fields available', () => {
  const { run } = load();
  run('game.start(30000, 7); game.step(); game.stop(false)');
  const log = plain(run('roundPayload(game)'));
  assert.equal(log.settled, false);
  assert.equal(log.players[0].payoutBreakdown, null);
  assert.ok(Array.isArray(log.trades));
  assert.ok('winner' in log && 'goalSuit' in log && 'cash' in log.players[0]);
  assert.equal(log.marketMode, 'players');
  assert.equal(log.humanSeated, false);
});

test('player mode is the default, accepts the official duration, and keeps old links in classic mode', () => {
  const current = load().run;
  assert.equal(current('game.marketMode'), 'players');
  assert.equal(current('normalizeScenario(1, 240000).durationMs'), 240000);
  for (const url of [
    'https://example.test/figgie-rl/?seed=9&duration=60000',
    'https://example.test/figgie-rl/?seed=9&duration=60000&market=players&version=1.0.0',
    'https://example.test/figgie-rl/?seed=9&duration=60000&market=classic',
  ]) {
    const { run } = load(url);
    assert.equal(run('game.marketMode'), 'classic');
    assert.match(run('scenarioFromUrl(window.location.href).compatibilityNote'), /Classic mode/);
  }
  const { run } = load('https://example.test/figgie-rl/?seed=9&duration=60000&market=players&version=2.0.0');
  assert.equal(run('game.marketMode'), 'players');
  assert.equal(run('scenarioUrl()'), 'https://example.test/figgie-rl/?seed=9&duration=60000&market=players&version=2.0.0');
});

test('official player quotes are backed, cross at the resting price, and clear the whole book', () => {
  const { run } = load();
  run(`game.loadDeal({goalSuitIdx: 0, inventories: [[2,3,3,2],[3,2,3,2],[3,3,2,2],[2,2,2,4]]});`);
  run(`game.players[0].cash = 5; game.applyAction(0, {kind:'quote_bid', suit:0, price:6});`);
  run(`game.players[1].inventory[0] = 0; game.applyAction(1, {kind:'quote_ask', suit:0, price:8});`);
  assert.equal(run('game.bestBid(0, -1).buyer'), null);
  assert.equal(run('game.bestAsk(0, -1).seller'), null);
  assert.equal(run('game.bestBid(0, -1).price'), -Infinity);
  assert.equal(run('game.bestAsk(0, -1).price'), Infinity);

  run(`game.players[0].cash = 300; game.players[1].inventory[0] = 3; game.applyAction(1, {kind:'quote_ask', suit:0, price:8});`);
  run(`game.applyAction(0, {kind:'quote_bid', suit:1, price:4});`);
  run(`game.applyAction(2, {kind:'quote_ask', suit:2, price:30});`);
  const beforeBuyer = run('game.players[3].cash');
  const beforeSeller = run('game.players[1].cash');
  run(`game.applyAction(3, {kind:'quote_bid', suit:0, price:12});`);
  assert.equal(run('game.roundLog.length'), 1);
  assert.equal(run('game.roundLog[0].price'), 8);
  assert.equal(run('game.players[3].cash'), beforeBuyer - 8);
  assert.equal(run('game.players[1].cash'), beforeSeller + 8);
  assert.equal(run('game.players.some(p => p.bidQuotes.some(Number.isFinite) || p.askQuotes.some(Number.isFinite))'), false);
});

test('player market orders wait on empty books, replace quotes, and hit the resting bid', () => {
  const { run } = load();
  run(`game.loadDeal({goalSuitIdx: 2, inventories: [[2,3,3,2],[3,2,3,2],[3,3,2,2],[2,2,2,4]]});`);
  run(`game.applyAction(0, {kind:'buy', suit:0}); game.applyAction(0, {kind:'sell', suit:0});`);
  assert.equal(run('game.roundLog.length'), 0);
  run(`game.applyAction(0, {kind:'quote_bid', suit:0, price:5}); game.applyAction(0, {kind:'quote_bid', suit:0, price:7});`);
  assert.equal(run('game.players[0].bidQuotes[0]'), 7);
  const buyerCash = run('game.players[0].cash');
  run(`game.applyAction(2, {kind:'quote_ask', suit:0, price:6});`);
  assert.equal(run('game.roundLog[0].price'), 7);
  assert.equal(run('game.players[0].cash'), buyerCash - 7);
  assert.equal(run('game.players.some(p => p.bidQuotes.some(Number.isFinite) || p.askQuotes.some(Number.isFinite))'), false);
});

test('players mode bot trade rate meets the 1–50 seed target at 60 seconds', () => {
  const { run } = load();
  const result = plain(run(`(() => {
    let trades = 0;
    const perBot = [0, 0, 0, 0];
    for (let seed = 1; seed <= 50; seed += 1) {
      game.start(60000, seed);
      game.setPaused(true);
      while (game.running) {
        for (const player of game.players) {
          player.bidQuotes.forEach((price, suit) => { if (Number.isFinite(price)) {
            if (player.cash < price) throw new Error('unbacked bot bid');
            if (Number.isFinite(player.askQuotes[suit]) && price >= player.askQuotes[suit]) throw new Error('self-crossing bot');
          }});
          player.askQuotes.forEach((price, suit) => { if (Number.isFinite(price)) {
            if (player.inventory[suit] <= 0) throw new Error('unbacked bot ask');
            if (Number.isFinite(player.bidQuotes[suit]) && price <= player.bidQuotes[suit]) throw new Error('self-crossing bot');
          }});
        }
        game.step(true);
      }
      if (game.roundLog.length < 3) throw new Error("fewer than three trades for seed " + seed);
      trades += game.roundLog.length;
      game.players.forEach((player, idx) => { perBot[idx] += player.trades; });
    }
    return {average: trades / 50, perBot};
  })()`));
  assert.ok(result.average >= 3, `average trades were ${result.average}`);
  assert.ok(result.perBot.every((trades) => trades > 0), `bot totals were ${result.perBot}`);
});

test('official Python rule fixtures replay after every action and at settlement', () => {
  const fixtures = JSON.parse(fs.readFileSync('tests/browser/fixtures/official_rules.json', 'utf8'));
  const { run } = load();
  const snapshot = () => plain(run(`(() => ({
    best: [0,1,2,3].map((suit) => {
      const bid = game.bestBid(suit, -1); const ask = game.bestAsk(suit, -1);
      return {bid:{price:bid.buyer === null ? null : bid.price, owner:bid.buyer},
        ask:{price:ask.seller === null ? null : ask.price, owner:ask.seller}};
    }),
    inventories: game.players.map((p) => [...p.inventory]),
    cash: game.players.map((p) => p.cash),
    lastTradePrice: [...game.lastTradePrice],
    trades: game.roundLog.map((t) => ({buyerIdx:t.buyerIdx,sellerIdx:t.sellerIdx,
      suit:t.suit,price:t.price,aggressorSide:t.aggressorSide})),
  }))()`));
  for (const scenario of fixtures.scenarios) {
    run(`game.reset(30000, 7, {marketMode:'players'});`);
    run(`game.loadDeal(${JSON.stringify({
      inventories: scenario.inventories,
      goalSuitIdx: scenario.goalSuitIdx,
      startingCash: scenario.startingCash,
      ante: scenario.ante,
      marketMode: 'players',
    })});`);
    scenario.steps.forEach((step, idx) => {
      run(`game.applyAction(${step.player}, ${JSON.stringify(step.action)});`);
      assert.deepEqual(snapshot(), scenario.expectedAfterSteps[idx], `${scenario.name} after step ${idx + 1}`);
    });
    run('game.settleRound(); game.revealGoal = true;');
    const settlement = plain(run(`(() => {
      const goalCounts = game.players.map((p) => p.inventory[game.goalSuitIdx]);
      return {goalSuitIdx:game.goalSuitIdx, goalCardCounts:goalCounts,
        goalCardPayouts:game.players.map((p) => p.goalCardPayout),
        majorityPool:game.majorityPaid,
        majorityShares:game.players.map((p) => p.majorityPayout),
        winners:game.winnerIdxs,
        finalBankrolls:game.players.map((p) => p.cash),
        profitFromStart:game.players.map((p) => p.cash - game.startingCash)};
    })()`));
    assert.deepEqual(settlement, scenario.expectedSettlement, `${scenario.name} settlement`);
  }
});
