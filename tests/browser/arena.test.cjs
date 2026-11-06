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
  assert.equal(baseline.schemaVersion, 2);
  assert.equal(baseline.simulationVersion, '1.0.0');
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
  assert.equal(run('scenarioUrl()'), 'https://example.test/figgie-rl/?seed=-23&duration=60000');
});

test('unfinished exports explicitly omit settlement and leave existing fields available', () => {
  const { run } = load();
  run('game.start(30000, 7); game.step(); game.stop(false)');
  const log = plain(run('roundPayload(game)'));
  assert.equal(log.settled, false);
  assert.equal(log.players[0].payoutBreakdown, null);
  assert.ok(Array.isArray(log.trades));
  assert.ok('winner' in log && 'goalSuit' in log && 'cash' in log.players[0]);
});
