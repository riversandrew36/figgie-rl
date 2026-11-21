const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function load(url = 'https://example.test/figgie-rl/') {
  const elements = new Map();
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      value: id === 'speedSelect' ? '1' : id === 'durationSelect' ? '30000' : '7',
      addEventListener(type, handler) { this[type === "click" ? "clickHandler" : type] = handler; }, focus() {}, select() {}, scrollIntoView() {},
      click() { this.clickHandler?.(); },
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

test('a fresh visit opens Play with a one-minute round; shared links keep their mode', () => {
  const fresh = load();
  assert.equal(fresh.elements.get('playModeInput').checked, true);
  assert.equal(fresh.elements.get('watchModeInput').checked, false);
  assert.equal(fresh.run('scenarioFromUrl(window.location.href).durationMs'), 60000);

  const legacy = load('https://example.test/figgie-rl/?seed=9');
  assert.equal(legacy.run('scenarioFromUrl(window.location.href).durationMs'), 30000);
  assert.equal(legacy.elements.get('playModeInput').checked, false);

  const sharedWatch = load('https://example.test/figgie-rl/?seed=9&duration=60000&market=players&version=2.0.0');
  assert.equal(sharedWatch.elements.get('watchModeInput').checked, true);

  const sharedPlay = load('https://example.test/figgie-rl/?seed=9&duration=60000&market=players&version=2.0.0&mode=play');
  assert.equal(sharedPlay.elements.get('playModeInput').checked, true);
  sharedPlay.run("game.reset(60000, 9, {marketMode: 'players', humanSeated: true})");
  assert.equal(
    sharedPlay.run('scenarioUrl()'),
    'https://example.test/figgie-rl/?seed=9&duration=60000&market=players&version=2.0.0&mode=play',
  );
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

test('Your read uses the detective weighting and ignores hidden deal data', () => {
  const { run } = load();
  run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
  const result = plain(run(`(() => {
    const hand = [3, 3, 2, 2];
    const trades = [{ buyerIdx: 1, sellerIdx: 0, suit: 1, aggressorSide: "buy" },
      { buyerIdx: 0, sellerIdx: 2, suit: 2, aggressorSide: "buy" }];
    const read = () => estimateRead(game.players[0].initialInventory, game.players[0].inventory, trades, 0);
    game.loadDeal({ inventories: [hand, [2,4,2,2], [1,2,3,4], [2,3,3,2]], goalSuitIdx: 0 });
    const first = read();
    game.loadDeal({ inventories: [hand, [1,2,3,4], [2,4,2,2], [2,3,3,2]], goalSuitIdx: 2 });
    return [first, read()];
  })()`));
  assert.deepEqual(result[0], result[1]);
  const weighted = result[0].map((row, suit) => row.handOdds * Math.exp(suit === 1 ? 0.35 : 0));
  const total = weighted.reduce((a, b) => a + b);
  result[0].forEach((row, suit) => assert.equal(row.tapeOdds, weighted[suit] / total));
});

test('every fixed lesson seed demonstrates its bot tell within one minute', () => {
  const { run } = load();
  run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
  const tells = plain(run(`Object.fromEntries(Object.entries(BOT_LESSONS).map(([id, lesson]) => {
    const replay = new FiggieViewerGame();
    replay.reset(60000, lesson.seed, { humanSeated: true, playerSpecs: [
      { name: 'You', isHuman: true },
      ...lesson.opponents.map(name => ({ name, strategy: BOT_NAMES.indexOf(name) })),
    ] });
    const seat = lesson.opponents.findIndex(name => name.toLowerCase() === id) + 1;
    const bot = replay.players[seat];
    const prior = goalSuitPosterior(bot.initialInventory);
    const favorite = replay.argmax(prior);
    const decoy = replay.argmin(prior.map((p, suit) => suit === favorite ? Infinity : p));
    const quoteSides = new Set();
    let trades = 0;
    for (let tick = 0; tick < 240; tick += 1) {
      replay.tick = tick;
      replay.elapsedMs = tick * replay.tickMs;
      replay.ageAndExpireQuotes();
      for (let i = 1; i < 4; i += 1) {
        const action = replay.pickAction(i);
        const flow = replay.othersFlow(bot);
        const before = replay.roundLog.length;
        replay.applyAction(i, action);
        if (i !== seat) continue;
        if (action.kind.startsWith('quote')) quoteSides.add(action.kind);
        const trade = replay.roundLog.at(-1);
        if (replay.roundLog.length === before || trade.buyerIdx !== seat || trade.aggressorSide !== 'buy') continue;
        if (id === 'hunter' && tick < 72 && trade.suit === favorite) trades += 1;
        if (id === 'bluffer' && tick < 72 && trade.suit === decoy) trades += 1;
        if (id === 'detective' && tick >= 48 && flow[trade.suit] > 0) trades += 1;
      }
    }
    return [id, id === 'banker' ? quoteSides.size : trades];
  }))`));
  assert.ok(tells.hunter >= 2);
  assert.equal(tells.banker, 2);
  assert.ok(tells.detective >= 1);
  assert.ok(tells.bluffer >= 2);
});

for (const id of ['hunter', 'banker', 'detective', 'bluffer']) {
  test(`${id} lesson scores passing and failing scripted rounds`, () => {
    const { run } = load();
    run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
    const result = plain(run(`[true, false].map(pass => {
      const id = ${JSON.stringify(id)};
      const round = new FiggieViewerGame();
      round.reset(60000, 7);
      round.loadDeal({ inventories: [[3,3,2,2],[2,4,2,2],[1,2,3,4],[2,3,3,2]], goalSuitIdx: 0,
        playerSpecs: [{name:"You",isHuman:true}, ...BOT_NAMES.map(name => ({name})).filter(player => player.name !== "Detective")] });
      const suit = id === "banker" || id === "hunter" && pass ? 2 : id === "bluffer" && pass ? 2 : 0;
      if (id !== "banker" || pass) {
        const buyer = id === "bluffer" ? 3 : 1;
        round.applyAction(buyer, {kind:"quote_bid",suit,price:id === "banker" ? 50 : 5});
        round.applyAction(0, {kind:"sell",suit});
      } else {
        // Trade away the majority and finish below the starting bankroll.
        round.applyAction(1, {kind:"quote_bid",suit:0,price:1});
        round.applyAction(0, {kind:"sell",suit:0});
      }
      round.stop(true);
      return lessonPassed(id, round, 0, 0, pass ? 119 : 120);
    })`));
    assert.deepEqual(result, [true, false]);
  });
}

test('hindsight undoes goal and non-goal sales, majority flips and ties', () => {
  const { run } = load();
  run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
  const values = plain(run(`[
    [[4,2,1,1], 0], [[4,2,1,1], 1], [[2,3,2,1], 0], [[3,3,1,1], 0],
  ].map(([counts, suit]) => {
    const round = new FiggieViewerGame();
    round.reset(60000, 7);
    round.goalSuitIdx = 0;
    round.players.forEach((p,i) => { p.inventory = [counts[i], 2, 2, 2]; });
    // Restore pre-trade holdings so the real matcher produces the final state.
    round.players[0].inventory[suit] += 1;
    round.players[1].inventory[suit] -= 1;
    round.applyAction(1, {kind:"quote_bid", suit, price:20});
    round.applyAction(0, {kind:"sell", suit});
    round.stop(true);
    const [trade] = tradeHindsight(round, 0);
    return [trade.value, trade.edge];
  })`));
  assert.deepEqual(values.map(row => row.slice(0, 2)), [[10, 10], [0, 20], [130, -110], [70, -50]]);

});

test('coach recording leaves seeded trades unchanged', () => {
  function replay(capture) {
    const { run } = load();
    run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
    return plain(run(`(() => {
      game.captureCoach = ${capture};
      game.start(60000, 19, 1, {humanSeated:true, playerSpecs:[
        {name:"You",isHuman:true}, ...BOT_NAMES.slice(0,3).map((name,strategy) => ({name,strategy}))
      ]});
      figgieTeaching.roundStarted();
      while (game.running) game.step(true);
      return {log:game.roundLog, rng:game.rngState, frames:game.coachSnapshots.length};
    })()`));
  }
  const on = replay(true);
  const off = replay(false);
  assert.ok(on.log.length);
  assert.equal(on.frames, 240);
  assert.equal(off.frames, 0);
  assert.equal(on.rng, off.rng);
  assert.deepEqual(on.log, off.log);
});

test('missed edges exclude same-tick actions and unaffordable offers', () => {
  const { run } = load();
  run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
  const quotes = plain(run(`(() => {
    game.reset(60000, 19);
    game.goalSuitIdx = 0;
    game.players.forEach((player) => { player.inventory = [2,2,2,2]; });
    const frame = (tick, price) => ({tick,cash:0,books:[
      {held:2,bid:null,ask:{owner:1,price:1}},
      {held:2,bid:{owner:1,price},ask:null},
    ]});
    game.humanActionTicks.add(5);
    game.coachSnapshots.push(frame(5,20),frame(6,12),frame(7,12));
    return missedEdges(game,0);
  })()`));
  assert.deepEqual(quotes.map(quote => [quote.tick, quote.edge]), [[6, 12]]);
});

const reconciliationCases = [
  { name: 'no trades', counts: [2,3,2,1], actions: [], expected: [320, -30, 0, 0, -30, 0] },
  { name: 'non-goal sale', counts: [2,3,2,1], actions: [['sell', 1]], expected: [320, -30, 8, 0, -22, 0] },
  { name: 'one buy wins majority', counts: [2,3,2,1], actions: [['buy', 0]], expected: [320, -30, 122, 0, 92, 120] },
  // Both buys are needed. Each single undo loses the same $120 majority payout.
  { name: 'two buys win majority', counts: [1,4,2,1], actions: [['buy', 0], ['buy', 0]], expected: [310, -40, 244, -120, 84, 120] },
  // Eight goal cards leave $120. The two leaders get $60 each.
  { name: 'one buy creates a tie', counts: [2,4,1,1], actions: [['buy', 0]], expected: [320, -30, 62, 0, 32, 60] },
];
for (const { name, counts, actions, expected } of reconciliationCases) {
  test(`profit decomposition: ${name}`, () => {
    const { run } = load();
    run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
    const actual = plain(run(`(() => {
      game.goalSuitIdx = 0;
      game.players.forEach((p, i) => { p.inventory = [${JSON.stringify(counts)}[i], 2, 2, 2]; });
      for (const [side, suit] of ${JSON.stringify(actions)}) {
        game.applyAction(1, { kind: side === "buy" ? "quote_ask" : "quote_bid", suit, price: 8 });
        game.applyAction(0, { kind: side, suit });
      }
      game.settleRound();
      const { baselineBankroll, baseline, edge, interaction, profit } = tradeReconciliation(game, 0);
      const payout = payoutBreakdown(game, game.players[0]);
      return { terms: [baselineBankroll, baseline, edge, interaction, profit, payout.majorityPayout],
        sum: baseline + edge + interaction, actual: payout.netProfit };
    })()`));
    assert.deepEqual(actual.terms, expected);
    assert.equal(actual.sum, actual.actual);
    assert.equal(actual.actual, expected[4]);
  });
}

test('daily seeds are stable and UTC midnight changes the date', () => {
  const { run } = load();
  run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
  assert.deepEqual(plain(run(`['2026-11-20','2026-11-21','2027-01-01'].map(dailySeed)`)),
    [3443902763, 3427125144, 3908099178]);
  assert.equal(run(`utcDay(new Date('2026-11-20T23:59:00Z'))`), '2026-11-20');
  assert.equal(run(`utcDay(new Date('2026-11-21T00:00:00Z'))`), '2026-11-21');
});

test('daily attempt reservation and streak respect prior dates and gaps', () => {
  const { run } = load();
  run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
  const output = plain(run(`(() => {
    const days = {'2026-11-18': {firstProfit: 0}, '2026-11-19': {firstProfit: 12}};
    const date = '2026-11-21';
    const first = dailyAttempt(days, date, date);
    days[date] = {firstProfit: null};
    const second = dailyAttempt(days, date, date);
    const old = dailyAttempt(days, '2026-11-20', date);
    const gap = dailyStreak(days, date);
    days[date].firstProfit = -2;
    return {first, second, old, gap, newRun: dailyStreak(days, date)};
  })()`));
  assert.deepEqual(output, {first:true, second:false, old:false,
    gap:{current:0,best:2}, newRun:{current:1,best:2}});
});

test('daily share text ignores hidden fields', () => {
  const { run } = load();
  run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
  const shared = run(`dailyShareText({date:"2026-11-21", profit:42, practice:false, called:true,
    lockedTime:"0:24", edges:[5,-2,0], streak:1, goalSuit:"Diamonds", inventory:[1,2,3,4]})`);
  assert.match(shared, /goal called at 0:24/);
  assert.match(shared, /🟩🟥⬜/);
  assert.match(shared, /\?daily=2026-11-21/);
  assert.doesNotMatch(shared, /Diamonds|1,2,3,4/);
});

test('daily round hides the seed field until the round ends', () => {
  const { run, elements } = load();
  run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
  elements.get('playDaily').click();
  assert.equal(elements.get('seedInput').hidden, true);
  assert.equal(elements.get('dailySeedLabel').hidden, false);
  elements.get('playBtn').click();
  assert.equal(elements.get('seedInput').hidden, false);
});

test('Lab matches Python observations, MaskablePPO masks, logits and actions', (t) => {
  const fixture = require('./fixtures/ppo_lab_parity.json');
  const { run } = load();
  run(fs.readFileSync('figgie_rl/arena/figgie_lab_policy.js', 'utf8'));
  let maxObservation = 0;
  let maxLogits = 0;
  for (const [name, deals] of Object.entries(fixture)) {
    run(fs.readFileSync(`figgie_rl/arena/policies/${name}.js`, 'utf8'));
    for (const deal of deals) {
      run(`game.reset(60000, 7, {marketMode:'lab'});
        game.loadDeal(${JSON.stringify({ inventories: deal.inventories, goalSuitIdx: deal.goalSuitIdx, marketMode: 'lab' })});
        game.actionOrderStart = ${deal.order};
        game.tieBreakStart = ${deal.tie};
        var scriptedActions = ${JSON.stringify(deal.actions)};`);
      let tick = 0;
      for (const expected of deal.decisions) {
        while (tick < expected.tick) {
          run('game.runLabTurn(scriptedActions[game.tick] || {}); game.tick += 1;');
          tick += 1;
        }
        const computed = plain(run(`(() => {
          const actor = figgiePolicies.${name};
          const observation = labObservation(game, 0, actor.hidden_blocks);
          const mask = labActionMask(game, 0, actor.actions);
          const logits = labActor(actor.layers, observation);
          return {observation: [...observation], logits: [...logits],
            mask: mask.map(Number).join(""), argmax: labMaskedArgmax(logits, mask)};
        })()`));
        const diff = (actual, reference) => {
          assert.equal(actual.length, reference.length);
          return Math.max(...actual.map((value, i) => Math.abs(value - reference[i])));
        };
        const obs = diff(computed.observation, expected.observation);
        const logits = diff(computed.logits, expected.logits);
        const context = `${name}, order ${deal.order}, step ${tick}`;
        assert.ok(obs <= 1e-6, `${context}: observation diff ${obs}`);
        assert.ok(logits <= 1e-4, `${context}: logit diff ${logits}`);
        assert.equal(computed.mask, expected.mask, context);
        assert.equal(computed.argmax, expected.argmax, context);
        maxObservation = Math.max(maxObservation, obs);
        maxLogits = Math.max(maxLogits, logits);
      }
    }
  }
  t.diagnostic(`Maximum observation difference ${maxObservation}; logit difference ${maxLogits}`);
});

test('existing one-minute scripted rounds keep their main-branch trade logs', () => {
  const { createHash } = require('node:crypto');
  const expected = {
    1: '4125e20f6a1023af43141b7bf35a92a414290d147c4511e8211d69b33dd415dc',
    7: 'c1d5401de1cfa301ededb0b3dc2f105285904e8d7ab1f239314f5ea130cf4798',
    19: '1cb33f05b6cf9d9d65f48cf04525f5f6685b87ef2f7571dfb8a005f0af48c2f3',
    50: '772447b419728ab8ff11216787916956c77e63d5a76e783b7ec6a3d8a7bd9d19',
  };
  for (const [seed, digest] of Object.entries(expected)) {
    const { run } = load();
    const log = run(`game.start(60000,${Number(seed)}); while (game.running) game.step(true); JSON.stringify(game.roundLog)`);
    assert.equal(createHash('sha256').update(log).digest('hex'), digest);
  }
});

test('Players preserves main-branch trades, RNG and settlement', () => {
  const { createHash } = require('node:crypto');
  for (const [seed, expected] of [
    [7, '4e4a82b3178be6dcafdb777aed326db3de93cb26db8ffda6594a2bd5bf84bbbc'],
    [19, '2fa2ed7c7793c13818b92d4829672d2c9dcfc758633679268bfdd3b03e91d859'],
  ]) {
    const { run } = load();
    const output = run(`game.start(60000,${seed},1,{marketMode:"players"});while(game.running)game.step(true);
      JSON.stringify([game.roundLog,game.rngState,game.goalSuitIdx,game.players.map(p=>p.cash),game.winnerIdxs])`);
    assert.equal(createHash('sha256').update(output).digest('hex'), expected);
  }
});

// Classic's outside-book noise goes through Math.log and Math.cos, whose last
// bit can differ between CPU architectures, so a pinned hash is not portable.
// Check instead that a seed replays exactly and keeps Classic's schedule.
test('Classic replays a seed exactly and keeps its schedule', () => {
  for (const seed of [7, 19]) {
    const outputs = [0, 1].map(() => {
      const { run } = load();
      return run(`game.start(60000,${seed},1,{marketMode:"classic"});while(game.running)game.step(true);
        JSON.stringify([game.marketMode,game.tickMs,game.tick,game.roundLog,game.rngState,game.goalSuitIdx,game.players.map(p=>p.cash),game.winnerIdxs])`);
    });
    assert.equal(outputs[0], outputs[1]);
    const [market, tickMs, ticks, log] = JSON.parse(outputs[0]);
    assert.deepEqual([market, tickMs, ticks], ['classic', 250, 240]);
    assert.ok(log.length > 0);
  }
});

test('lab rotates actions, applies a queued order once and ages quotes in decisions', () => {
  const { run } = load();
  const outcome = plain(run(`(() => {
    game.start(60000, 7, 1, {marketMode:"lab", humanSeated:true,
      playerSpecs:[{name:"You",isHuman:true}, ...BOT_NAMES.slice(0,3).map((name,strategy)=>({name,strategy}))]});
    game.players[3].inventory[0] = 1;
    game.actionOrderStart = 3;
    const order = [];
    game.pickAction = i => i === 3 && !game.tick ? {kind:"quote_ask", suit:0, price:8} : null;
    const apply = game.applyAction.bind(game);
    game.applyAction = (i, action) => {order.push(i); return apply(i, action);};
    game.queuedHumanAction = {kind:"buy", suit:0};
    game.step(true);
    game.applyAction(2,{kind:"quote_bid",suit:2,price:8});
    for(let i=0;i<7;i++) game.step(true);
    const stillOpen = game.bestBid(2,0).price;
    game.step(true);
    return {order:order.slice(0,4), open:stillOpen, expired:game.bestBid(2,0).buyer === null,
      trades:game.roundLog.length, interval:game.tickMs, queue:game.queuedHumanAction};
  })()`));
  assert.deepEqual(outcome, {order:[3,0,1,2],open:8,expired:true,trades:1,interval:500,queue:null});
});

test('daily, lessons and tutorial switch a lab share visitor back to Players', () => {
  for (const button of ['playDaily', 'learnBasics']) {
    const {run,elements} = load('https://example.test/figgie-rl/?market=lab&version=2.0.0&seed=7');
    assert.equal(run('game.marketMode'), 'lab');
    run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
    elements.get(button).click();
    assert.equal(run('game.marketMode'), 'players');
  }
  const {run} = load('https://example.test/figgie-rl/?market=lab&version=2.0.0&seed=7&lesson=hunter');
  run(fs.readFileSync('figgie_rl/arena/figgie_lessons.js', 'utf8'));
  assert.equal(run('game.marketMode'), 'players');
});

test('weight scripts are lazy, per-policy, and resolve under the arena prefix', async () => {
  const { run } = load();
  run(`document.currentScript = {src:"https://example.test/figgie-rl/figgie_lab_policy.js"};
      var appended = [];
      document.createElement = () => ({});
      document.head = {append(script) {appended.push(script);}};`);
  run(fs.readFileSync('figgie_rl/arena/figgie_lab_policy.js', 'utf8'));
  assert.equal(run('appended.length'), 0);
  const pending = run('loadLabPolicy("ppo_no_aids")');
  const duplicate = run('loadLabPolicy("ppo_no_aids")');
  assert.equal(pending, duplicate);
  assert.equal(run('appended.length'), 1);
  assert.equal(run('appended[0].src'), 'https://example.test/figgie-rl/policies/ppo_no_aids.js');
  run('globalThis.figgiePolicies = {ppo_no_aids:{}}; appended[0].onload();');
  await pending;
});
