// Bump when simulation mechanics or seeded execution change.
const SIMULATION_VERSION = "1.0.0";
const EXPORT_SCHEMA_VERSION = 2;
const SUPPORTED_DURATIONS = [30000, 60000, 90000];

function normalizeScenario(seed, durationMs) {
  return {
    seed: seed !== null && String(seed).trim() !== "" && Number.isSafeInteger(Number(seed))
      ? Number(seed) : 7,
    durationMs: SUPPORTED_DURATIONS.includes(Number(durationMs)) ? Number(durationMs) : 30000,
  };
}

function scenarioFromUrl(url) {
  const params = new URL(url).searchParams;
  return normalizeScenario(params.get("seed"), params.get("duration"));
}

const SUITS = [
  { name: "Spades", symbol: "♠" },
  { name: "Clubs", symbol: "♣" },
  { name: "Hearts", symbol: "♥" },
  { name: "Diamonds", symbol: "♦" },
];

const COLOR_PARTNER = { 0: 1, 1: 0, 2: 3, 3: 2 };
// Playing styles mirror figgie_rl/agents/styles.py.
const BOT_NAMES = ["Hunter", "Banker", "Detective", "Bluffer"];
const BOT_STYLES = [
  "Trusts its hand and lifts offers to corner the goal suit.",
  "Quotes both sides around fair value and earns the spread.",
  "Waits, reads who is paying up on the tape, then follows.",
  "Fakes demand in a decoy suit, sells into it, buys quietly.",
];
// Under this pot the majority holder takes $200 minus $10 per goal card, roughly $100.
const MAJORITY_BONUS_ESTIMATE = 100.0;

const durationSelect = document.getElementById("durationSelect");
const seedInput = document.getElementById("seedInput");
const speedSelect = document.getElementById("speedSelect");
const playBtn = document.getElementById("playBtn");
const pauseBtn = document.getElementById("pauseBtn");
const stepBtn = document.getElementById("stepBtn");
const downloadBtn = document.getElementById("downloadBtn");
const statusEl = document.getElementById("status");
const timerEl = document.getElementById("timer");
const potEl = document.getElementById("pot");
const goalEl = document.getElementById("goal");
const winnerEl = document.getElementById("winner");
const summaryEl = document.getElementById("summary");
const marketGridEl = document.getElementById("marketGrid");
const botRowsEl = document.getElementById("botRows");
const trackerMetaEl = document.getElementById("trackerMeta");
const strengthRowsEl = document.getElementById("strengthRows");
const resetStrengthBtn = document.getElementById("resetStrengthBtn");
const tapeEl = document.getElementById("tapeItems");

class FiggieViewerGame {
  constructor() {
    this.tickMs = 250;
    this.baseSpread = 2.0;
    this.tickSize = 1.0;
    this.driftStd = 0.25;
    this.externalFillProb = 0.6;
    this.quoteTtlSteps = 8;
    this.goalCardValue = 10.0;
    this.startingCash = 350.0;
    this.ante = 50.0;
    this.tradeId = 0;
    this.intervalId = null;
    this.running = false;
    this.paused = false;
    this.speed = 1;
    this.seed = 7;
    this.rngState = 7;
    this.players = [];
  }

  reset(durationMs, seed = 7) {
    const scenario = normalizeScenario(seed, durationMs);
    this.seed = scenario.seed;
    durationMs = scenario.durationMs;
    this.rngState = this.seed >>> 0;
    this.durationMs = durationMs;
    this.elapsedMs = 0;
    this.tick = 0;
    this.tradeId = 0;
    this.tradeTape = [];
    this.roundLog = [];
    this.revealGoal = false;
    this.winnerIdxs = [];
    this.winnerLabel = "Pending";
    this.antePot = BOT_NAMES.length * this.ante;
    this.cashAfterAnte = this.startingCash - this.ante;
    this.potRemaining = this.antePot;
    this.goalBonusPaid = 0.0;
    this.majorityPaid = 0.0;

    this.fundamentalMid = Array(SUITS.length).fill(5.0);
    this.externalBid = Array(SUITS.length).fill(4.0);
    this.externalAsk = Array(SUITS.length).fill(6.0);
    this.lastTradePrice = Array(SUITS.length).fill(5.0);
    this.lastTradeSignedVolume = Array(SUITS.length).fill(0.0);
    this.cumulativeSignedFlow = Array(SUITS.length).fill(0.0);

    const deal = this.dealRound();
    this.goalSuitIdx = deal.goalSuitIdx;
    this.players = BOT_NAMES.map((name, idx) => ({
      name,
      strategy: idx,
      style: BOT_STYLES[idx],
      inventory: deal.inventories[idx],
      initialInventory: [...deal.inventories[idx]],
      cash: this.cashAfterAnte,
      tradingCashflow: null,
      goalCardPayout: 0,
      majorityPayout: 0,
      trades: 0,
      bidQuotes: Array(SUITS.length).fill(-Infinity),
      askQuotes: Array(SUITS.length).fill(Infinity),
      bidQuoteAges: Array(SUITS.length).fill(-1),
      askQuoteAges: Array(SUITS.length).fill(-1),
    }));
  }

  start(durationMs, seed, speed = 1) {
    this.reset(durationMs, seed);
    this.speed = speed;
    this.running = true;
    this.paused = false;
    this.schedule();
  }

  schedule() {
    if (this.intervalId !== null) {
      clearInterval(this.intervalId);
    }
    this.intervalId = setInterval(() => this.step(), this.tickMs / this.speed);
  }

  setPaused(paused) {
    this.paused = paused;
    if (paused && this.intervalId !== null) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    } else if (!paused && this.running) {
      this.schedule();
    }
  }

  stop(settle) {
    if (this.intervalId !== null) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
    this.running = false;
    this.paused = false;
    if (settle) {
      this.settleRound();
      this.revealGoal = true;
    }
  }

  step(force = false) {
    if (!this.running || (this.paused && !force)) {
      return;
    }

    this.ageAndExpireQuotes();
    this.updateExternalBook();
    for (let i = 0; i < this.players.length; i += 1) {
      const action = this.pickAction(i);
      this.applyAction(i, action);
    }

    this.tick += 1;
    this.elapsedMs += this.tickMs;
    render();

    if (this.elapsedMs >= this.durationMs) {
      this.stop(true);
      onRoundEnded();
    }
  }

  ageAndExpireQuotes() {
    for (const player of this.players) {
      for (let suit = 0; suit < SUITS.length; suit += 1) {
        if (player.bidQuoteAges[suit] >= 0) {
          player.bidQuoteAges[suit] += 1;
          if (player.bidQuoteAges[suit] >= this.quoteTtlSteps) {
            player.bidQuoteAges[suit] = -1;
            player.bidQuotes[suit] = -Infinity;
          }
        }
        if (player.askQuoteAges[suit] >= 0) {
          player.askQuoteAges[suit] += 1;
          if (player.askQuoteAges[suit] >= this.quoteTtlSteps) {
            player.askQuoteAges[suit] = -1;
            player.askQuotes[suit] = Infinity;
          }
        }
      }
    }
  }

  dealRound() {
    const distribution = this.shuffle([12, 10, 10, 8]);
    let heavySuitIdx = 0;
    for (let i = 1; i < distribution.length; i += 1) {
      if (distribution[i] > distribution[heavySuitIdx]) {
        heavySuitIdx = i;
      }
    }
    const goalSuitIdx = COLOR_PARTNER[heavySuitIdx];

    const deck = [];
    for (let s = 0; s < distribution.length; s += 1) {
      for (let n = 0; n < distribution[s]; n += 1) {
        deck.push(s);
      }
    }
    this.shuffle(deck);

    const inventories = [];
    for (let p = 0; p < 4; p += 1) {
      const hand = deck.slice(p * 10, p * 10 + 10);
      const counts = [0, 0, 0, 0];
      for (const suit of hand) {
        counts[suit] += 1;
      }
      inventories.push(counts);
    }

    return { inventories, goalSuitIdx };
  }

  quotePrice(side, suit, level) {
    if (side === "quote_bid") {
      return Math.max(0, this.externalBid[suit] + this.tickSize * (level - 1));
    }
    return Math.max(0, this.externalAsk[suit] + this.tickSize * (level - 1));
  }

  bestBid(suit, excludingPlayerIdx) {
    let bestPrice = this.externalBid[suit];
    let buyer = null;
    for (let i = 0; i < this.players.length; i += 1) {
      if (i === excludingPlayerIdx) {
        continue;
      }
      const quote = this.players[i].bidQuotes[suit];
      if (quote >= bestPrice) {
        bestPrice = quote;
        buyer = i;
      }
    }
    return { price: bestPrice, buyer };
  }

  bestAsk(suit, excludingPlayerIdx) {
    let bestPrice = this.externalAsk[suit];
    let seller = null;
    for (let i = 0; i < this.players.length; i += 1) {
      if (i === excludingPlayerIdx) {
        continue;
      }
      const quote = this.players[i].askQuotes[suit];
      if (quote <= bestPrice) {
        bestPrice = quote;
        seller = i;
      }
    }
    return { price: bestPrice, seller };
  }

  applyAction(playerIdx, action) {
    const player = this.players[playerIdx];
    if (!action || action.kind === "hold") {
      return;
    }

    const suit = action.suit;
    if (suit < 0 || suit >= SUITS.length) {
      return;
    }

    if (action.kind === "quote_bid") {
      const level = this.clamp(action.level, 0, 2);
      player.bidQuotes[suit] = this.quotePrice("quote_bid", suit, level);
      player.bidQuoteAges[suit] = 0;
      return;
    }

    if (action.kind === "quote_ask") {
      const level = this.clamp(action.level, 0, 2);
      player.askQuotes[suit] = this.quotePrice("quote_ask", suit, level);
      player.askQuoteAges[suit] = 0;
      return;
    }

    if (action.kind === "buy") {
      const ask = this.bestAsk(suit, playerIdx);
      let seller = ask.seller;
      if (seller === null) {
        if (this.random() > this.externalFillProb) {
          return;
        }
        seller = this.randomCounterparty("sell", suit, ask.price, playerIdx);
        if (seller === null) {
          return;
        }
      }
      this.trade(playerIdx, seller, suit, ask.price, "buy");
      return;
    }

    if (action.kind === "sell") {
      const bid = this.bestBid(suit, playerIdx);
      let buyer = bid.buyer;
      if (buyer === null) {
        if (this.random() > this.externalFillProb) {
          return;
        }
        buyer = this.randomCounterparty("buy", suit, bid.price, playerIdx);
        if (buyer === null) {
          return;
        }
      }
      this.trade(buyer, playerIdx, suit, bid.price, "sell");
    }
  }

  randomCounterparty(side, suit, price, excludingPlayerIdx) {
    const candidates = this.players
      .map((player, idx) => ({ player, idx }))
      .filter(({ player, idx }) => (
        idx !== excludingPlayerIdx && (
          side === "sell" ? player.inventory[suit] > 0 : player.cash >= price
        )
      ))
      .map(({ idx }) => idx);
    return candidates.length > 0 ? this.choose(candidates) : null;
  }

  trade(buyerIdx, sellerIdx, suit, price, aggressorSide) {
    if (sellerIdx !== -1 && this.players[sellerIdx].inventory[suit] <= 0) {
      return;
    }
    if (buyerIdx !== -1 && this.players[buyerIdx].cash < price) {
      return;
    }

    if (sellerIdx !== -1) {
      this.players[sellerIdx].inventory[suit] -= 1;
      this.players[sellerIdx].cash += price;
      this.players[sellerIdx].trades += 1;
    }

    if (buyerIdx !== -1) {
      this.players[buyerIdx].inventory[suit] += 1;
      this.players[buyerIdx].cash -= price;
      this.players[buyerIdx].trades += 1;
    }

    this.lastTradePrice[suit] = price;
    this.lastTradeSignedVolume[suit] = aggressorSide === "buy" ? 1 : -1;
    this.cumulativeSignedFlow[suit] += this.lastTradeSignedVolume[suit];

    const buyerName = buyerIdx === -1 ? "External" : this.players[buyerIdx].name;
    const sellerName = sellerIdx === -1 ? "External" : this.players[sellerIdx].name;
    const line = `t=${this.tick.toString().padStart(3, "0")} ${buyerName} bought ${SUITS[suit].symbol} @ ${price.toFixed(2)} from ${sellerName}`;
    const trade = {
      id: this.tradeId++,
      tick: this.tick,
      line,
      suit,
      buyerIdx,
      sellerIdx,
      price,
      aggressorSide,
    };
    this.tradeTape.unshift(trade);
    this.roundLog.push(trade);
    if (this.tradeTape.length > 70) {
      this.tradeTape.length = 70;
    }
  }

  pickAction(playerIdx) {
    const p = this.players[playerIdx];
    if (p.strategy === 0) {
      return this.hunterAction(playerIdx);
    }
    if (p.strategy === 1) {
      return this.bankerAction(playerIdx);
    }
    if (p.strategy === 2) {
      return this.detectiveAction(playerIdx);
    }
    return this.blufferAction(playerIdx);
  }

  marketView(playerIdx) {
    const bid = [];
    const ask = [];
    for (let s = 0; s < SUITS.length; s += 1) {
      bid.push(this.bestBid(s, playerIdx).price);
      ask.push(this.bestAsk(s, playerIdx).price);
    }
    return { bid, ask };
  }

  roundFraction() {
    return this.durationMs > 0 ? this.elapsedMs / this.durationMs : 0;
  }

  // Net aggressive buying per suit by everyone else, removing the seat's own net position change.
  othersFlow(player) {
    return this.cumulativeSignedFlow.map(
      (flow, s) => flow - (player.inventory[s] - player.initialInventory[s]),
    );
  }

  hunterAction(playerIdx) {
    const player = this.players[playerIdx];
    const market = this.marketView(playerIdx);
    const posterior = goalSuitPosterior(player.initialInventory);
    const target = this.argmax(posterior);
    const targetCount = 6;
    const bonusShare = player.inventory[target] < targetCount ? MAJORITY_BONUS_ESTIMATE / targetCount : 0;
    const value = posterior[target] * (this.goalCardValue + bonusShare);
    if (player.cash >= market.ask[target] && market.ask[target] <= value) {
      return { kind: "buy", suit: target };
    }

    // Fund the hunt by dumping suits it does not believe in.
    let junk = -1;
    for (let s = 0; s < SUITS.length; s += 1) {
      if (s !== target && posterior[s] < 0.15 && player.inventory[s] > 0
        && (junk === -1 || player.inventory[s] > player.inventory[junk])) {
        junk = s;
      }
    }
    if (junk !== -1 && this.random() < 0.6) {
      return { kind: "sell", suit: junk };
    }
    return { kind: "quote_bid", suit: target, level: 2 };
  }

  bankerAction(playerIdx) {
    const player = this.players[playerIdx];
    const market = this.marketView(playerIdx);
    const edge = 1.0;
    const maxPosition = 3;
    const fair = goalSuitPosterior(player.initialInventory).map((p) => p * this.goalCardValue);
    const position = player.inventory.map((n, s) => n - player.initialInventory[s]);

    // Only cross the spread for clear gifts.
    let buySuit = -1;
    let sellSuit = -1;
    for (let s = 0; s < SUITS.length; s += 1) {
      const buyGift = fair[s] - market.ask[s];
      if (player.cash >= market.ask[s] && buyGift > 2 * edge
        && (buySuit === -1 || buyGift > fair[buySuit] - market.ask[buySuit])) {
        buySuit = s;
      }
      const sellGift = market.bid[s] - fair[s];
      if (player.inventory[s] > 0 && sellGift > 2 * edge
        && (sellSuit === -1 || sellGift > market.bid[sellSuit] - fair[sellSuit])) {
        sellSuit = s;
      }
    }
    if (buySuit !== -1) {
      return { kind: "buy", suit: buySuit };
    }
    if (sellSuit !== -1) {
      return { kind: "sell", suit: sellSuit };
    }

    // Rotate through suits, alternating sides; skip any side or suit with no edge.
    const bidFirst = Math.floor(this.tick / SUITS.length) % 2 === 0;
    for (let offset = 0; offset < SUITS.length; offset += 1) {
      const s = (this.tick + offset) % SUITS.length;
      const skew = -0.5 * position[s];
      for (const side of bidFirst ? ["bid", "ask"] : ["ask", "bid"]) {
        if (side === "bid" && position[s] < maxPosition) {
          const target = fair[s] - edge + skew;
          const level = this.clamp(Math.floor(target - market.bid[s]) + 1, 0, 2);
          if (market.bid[s] + level - 1 <= target) {
            return { kind: "quote_bid", suit: s, level };
          }
        }
        if (side === "ask" && player.inventory[s] > 0 && position[s] > -maxPosition) {
          const target = fair[s] + edge + skew;
          const level = this.clamp(Math.ceil(target - market.ask[s]) + 1, 0, 2);
          return { kind: "quote_ask", suit: s, level };
        }
      }
    }
    return { kind: "hold" };
  }

  detectiveAction(playerIdx) {
    const player = this.players[playerIdx];
    const market = this.marketView(playerIdx);
    const prior = goalSuitPosterior(player.initialInventory);
    const flow = this.othersFlow(player);
    const weighted = prior.map((p, s) => p * Math.exp(0.35 * this.clamp(flow[s], -10, 10)));
    const total = weighted.reduce((a, b) => a + b, 0);
    const posterior = weighted.map((w) => w / total);
    const target = this.argmax(posterior);
    const certainty = posterior[target];

    let ruledOut = -1;
    for (let s = 0; s < SUITS.length; s += 1) {
      if (ruledOut === -1 && s !== target && posterior[s] < 0.05 && player.inventory[s] > 0) {
        ruledOut = s;
      }
    }
    if (this.roundFraction() < 0.2 || certainty < 0.55) {
      // Still gathering evidence: shed suits the tape rules out, bid quietly on the leader.
      if (ruledOut !== -1 && this.random() < 0.3) {
        return { kind: "sell", suit: ruledOut };
      }
      if (this.random() < 0.3) {
        return { kind: "hold" };
      }
      return { kind: "quote_bid", suit: target, level: 0 };
    }

    const bonusShare = player.inventory[target] < 6 ? MAJORITY_BONUS_ESTIMATE / 6 : 0;
    const value = certainty * (this.goalCardValue + bonusShare);
    if (player.cash >= market.ask[target] && market.ask[target] <= value) {
      return { kind: "buy", suit: target };
    }
    if (ruledOut !== -1) {
      return { kind: "sell", suit: ruledOut };
    }
    return { kind: "quote_bid", suit: target, level: 1 };
  }

  blufferAction(playerIdx) {
    const player = this.players[playerIdx];
    const market = this.marketView(playerIdx);
    const posterior = goalSuitPosterior(player.initialInventory);
    const target = this.argmax(posterior);
    // The decoy is the suit it believes in least, the cheapest convincing fake.
    let decoy = -1;
    for (let s = 0; s < SUITS.length; s += 1) {
      if (s !== target && (decoy === -1 || posterior[s] < posterior[decoy])) {
        decoy = s;
      }
    }
    const fraction = this.roundFraction();

    if (fraction < 0.3) {
      // Loud: lift offers in the decoy so the tape shows conviction.
      const bought = player.inventory[decoy] - player.initialInventory[decoy];
      if (bought < 3 && player.cash >= market.ask[decoy] && this.random() < 0.6) {
        return { kind: "buy", suit: decoy };
      }
      return { kind: "quote_bid", suit: target, level: 0 };
    }

    // Fade whoever is chasing a suit it does not believe in.
    const flow = this.othersFlow(player);
    let fade = -1;
    for (let s = 0; s < SUITS.length; s += 1) {
      if (s !== target && flow[s] >= 2 && player.inventory[s] > 0 && (fade === -1 || flow[s] > flow[fade])) {
        fade = s;
      }
    }
    if (fade !== -1 && this.random() < 0.5) {
      return { kind: "sell", suit: fade };
    }

    // Unload the decoy high while the bluff lingers, then at the bid late on.
    if (player.inventory[decoy] > 0 && this.random() < 0.5) {
      if (fraction > 0.7) {
        return { kind: "sell", suit: decoy };
      }
      return { kind: "quote_ask", suit: decoy, level: 2 };
    }

    // Never lifts offers in its real suit until the closing seconds.
    if (fraction > 0.85 && player.cash >= market.ask[target]
      && market.ask[target] <= posterior[target] * this.goalCardValue) {
      return { kind: "buy", suit: target };
    }
    return { kind: "quote_bid", suit: target, level: 1 };
  }

  settleRound() {
    const goalCounts = this.players.map((p) => p.inventory[this.goalSuitIdx]);
    const maxGoal = Math.max(...goalCounts);
    const winners = [];

    this.goalBonusPaid = 0.0;
    for (let i = 0; i < goalCounts.length; i += 1) {
      const bonus = goalCounts[i] * this.goalCardValue;
      this.players[i].tradingCashflow = this.players[i].cash - this.cashAfterAnte;
      this.players[i].goalCardPayout = bonus;
      this.players[i].cash += bonus;
      this.goalBonusPaid += bonus;
      if (goalCounts[i] === maxGoal) {
        winners.push(i);
      }
    }

    this.potRemaining = Math.max(0, this.antePot - this.goalBonusPaid);
    this.majorityPaid = 0.0;
    if (winners.length > 0 && this.potRemaining > 0) {
      const split = this.potRemaining / winners.length;
      for (const w of winners) {
        this.players[w].majorityPayout = split;
        this.players[w].cash += split;
      }
      this.majorityPaid = this.potRemaining;
      this.potRemaining = 0.0;
    }

    this.winnerIdxs = winners;
    if (winners.length === 1) {
      this.winnerLabel = this.players[winners[0]].name;
    } else if (winners.length > 1) {
      this.winnerLabel = `Tie (${winners.map((i) => this.players[i].name).join(", ")})`;
    } else {
      this.winnerLabel = "No winner";
    }
  }

  updateExternalBook() {
    const half = this.baseSpread / 2;
    for (let i = 0; i < SUITS.length; i += 1) {
      this.fundamentalMid[i] = this.clamp(this.fundamentalMid[i] + this.randn(0, this.driftStd), 1, 20);
      this.externalBid[i] = Math.max(0, this.fundamentalMid[i] - half);
      this.externalAsk[i] = this.fundamentalMid[i] + half;
    }
  }

  markToMarket(player) {
    let value = player.cash;
    for (let s = 0; s < SUITS.length; s += 1) {
      value += player.inventory[s] * ((this.externalBid[s] + this.externalAsk[s]) / 2);
    }
    return value;
  }

  timeRemainingMs() {
    return Math.max(0, this.durationMs - this.elapsedMs);
  }

  choose(arr) {
    return arr[this.randInt(0, arr.length)];
  }

  randInt(minIncl, maxExcl) {
    return Math.floor(this.random() * (maxExcl - minIncl)) + minIncl;
  }

  random() {
    this.rngState = (this.rngState + 0x6D2B79F5) >>> 0;
    let t = this.rngState;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  argmin(arr) {
    let idx = 0;
    for (let i = 1; i < arr.length; i += 1) {
      if (arr[i] < arr[idx]) {
        idx = i;
      }
    }
    return idx;
  }

  argmax(arr) {
    let idx = 0;
    for (let i = 1; i < arr.length; i += 1) {
      if (arr[i] > arr[idx]) {
        idx = i;
      }
    }
    return idx;
  }

  clamp(v, lo, hi) {
    return Math.min(hi, Math.max(lo, v));
  }

  shuffle(arr) {
    for (let i = arr.length - 1; i > 0; i -= 1) {
      const j = this.randInt(0, i + 1);
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }

  randn(mean, stdDev) {
    const u1 = 1 - this.random();
    const u2 = 1 - this.random();
    const z0 = Math.sqrt(-2.0 * Math.log(u1)) * Math.cos(2.0 * Math.PI * u2);
    return mean + z0 * stdDev;
  }
}

// Exact goal-suit probabilities from a 10-card hand, matching mechanics.goal_suit_posterior.
const posteriorCache = new Map();

function choose(n, k) {
  if (k < 0 || k > n) {
    return 0;
  }
  let result = 1;
  for (let i = 1; i <= k; i += 1) {
    result = (result * (n - k + i)) / i;
  }
  return result;
}

function goalSuitPosterior(hand) {
  const key = hand.join(",");
  if (posteriorCache.has(key)) {
    return posteriorCache.get(key);
  }
  const remainders = [[10, 10, 8], [10, 8, 10], [8, 10, 10]];
  const posterior = Array(SUITS.length).fill(0);
  for (let heavy = 0; heavy < SUITS.length; heavy += 1) {
    const others = [0, 1, 2, 3].filter((s) => s !== heavy);
    let likelihood = 0;
    for (const remainder of remainders) {
      const deck = Array(SUITS.length).fill(0);
      deck[heavy] = 12;
      others.forEach((s, i) => { deck[s] = remainder[i]; });
      likelihood += deck.reduce((acc, count, s) => acc * choose(count, hand[s]), 1);
    }
    // Each distinct 10/10/8 arrangement appears twice among the six permutations.
    posterior[COLOR_PARTNER[heavy]] += 2 * likelihood;
  }
  const total = posterior.reduce((a, b) => a + b, 0);
  const normalized = total > 0 ? posterior.map((p) => p / total) : Array(SUITS.length).fill(0.25);
  posteriorCache.set(key, normalized);
  return normalized;
}

const game = new FiggieViewerGame();
const STRENGTH_STORAGE_KEY = "figgie_strength_tracker_v2";

function createDefaultStrengthTracker() {
  return {
    rounds: 0,
    bots: BOT_NAMES.map((name) => ({
      name,
      rating: 1000,
      wins: 0,
      totalBankroll: 0,
      lastBankroll: 0,
      history: [1000],
    })),
  };
}

function loadStrengthTracker() {
  try {
    const raw = localStorage.getItem(STRENGTH_STORAGE_KEY);
    if (!raw) {
      return createDefaultStrengthTracker();
    }
    const parsed = JSON.parse(raw);
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      typeof parsed.rounds !== "number" ||
      !Array.isArray(parsed.bots) ||
      parsed.bots.length !== BOT_NAMES.length
    ) {
      return createDefaultStrengthTracker();
    }

    const sanitizedBots = parsed.bots.map((bot, idx) => ({
      name: BOT_NAMES[idx],
      rating: Number.isFinite(bot?.rating) ? bot.rating : 1000,
      wins: Number.isFinite(bot?.wins) ? bot.wins : 0,
      totalBankroll: Number.isFinite(bot?.totalBankroll) ? bot.totalBankroll : 0,
      lastBankroll: Number.isFinite(bot?.lastBankroll) ? bot.lastBankroll : 0,
      history: Array.isArray(bot?.history) && bot.history.length > 0
        ? bot.history.filter((x) => Number.isFinite(x)).slice(-40)
        : [1000],
    }));

    return {
      rounds: Math.max(0, parsed.rounds),
      bots: sanitizedBots,
    };
  } catch {
    return createDefaultStrengthTracker();
  }
}

function saveStrengthTracker() {
  try {
    localStorage.setItem(STRENGTH_STORAGE_KEY, JSON.stringify(strengthTracker));
  } catch {
    // Ignore storage write failures (private mode, disabled storage, quota).
  }
}

function resetStrengthTracker() {
  const fresh = createDefaultStrengthTracker();
  strengthTracker.rounds = fresh.rounds;
  strengthTracker.bots = fresh.bots;
  saveStrengthTracker();
  renderStrengthTracker();
  summaryEl.textContent = "Strength stats reset.";
}

const strengthTracker = loadStrengthTracker();

function updateStrengthTracker() {
  const kFactor = 24;
  const deltas = Array(game.players.length).fill(0);
  const finals = game.players.map((p) => p.cash);

  for (let i = 0; i < finals.length; i += 1) {
    for (let j = i + 1; j < finals.length; j += 1) {
      const ratingI = strengthTracker.bots[i].rating;
      const ratingJ = strengthTracker.bots[j].rating;
      const expectedI = 1 / (1 + 10 ** ((ratingJ - ratingI) / 400));
      let actualI = 0.5;
      if (finals[i] > finals[j]) {
        actualI = 1.0;
      } else if (finals[i] < finals[j]) {
        actualI = 0.0;
      }
      const change = kFactor * (actualI - expectedI);
      deltas[i] += change;
      deltas[j] -= change;
    }
  }

  strengthTracker.rounds += 1;
  const winShare = game.winnerIdxs.length > 0 ? 1 / game.winnerIdxs.length : 0;

  for (let i = 0; i < strengthTracker.bots.length; i += 1) {
    const bot = strengthTracker.bots[i];
    bot.rating = Math.max(100, bot.rating + deltas[i]);
    bot.totalBankroll += finals[i];
    bot.lastBankroll = finals[i];
    if (game.winnerIdxs.includes(i)) {
      bot.wins += winShare;
    }
    bot.history.push(bot.rating);
    if (bot.history.length > 40) {
      bot.history.shift();
    }
  }
  saveStrengthTracker();
}

function renderStrengthTracker() {
  trackerMetaEl.textContent = `Settled rounds: ${strengthTracker.rounds}`;
  const ranked = strengthTracker.bots
    .map((bot, idx) => ({ ...bot, idx }))
    .sort((a, b) => b.rating - a.rating);

  strengthRowsEl.innerHTML = ranked.map((bot, rankIdx) => {
    const winRate = strengthTracker.rounds > 0 ? (100 * bot.wins) / strengthTracker.rounds : 0;
    const avgBankroll = strengthTracker.rounds > 0 ? bot.totalBankroll / strengthTracker.rounds : 0;
    const trendBase = bot.history[Math.max(0, bot.history.length - 6)];
    const trend = bot.rating - trendBase;
    const trendClass = trend >= 0 ? "pos" : "neg";
    const trendSign = trend >= 0 ? "+" : "";
    return `
      <tr>
        <td>${rankIdx + 1}</td>
        <td>${bot.name}</td>
        <td>${bot.rating.toFixed(1)}</td>
        <td>${winRate.toFixed(1)}%</td>
        <td>${avgBankroll.toFixed(2)}</td>
        <td>${bot.lastBankroll.toFixed(2)}</td>
        <td class="${trendClass}">${trendSign}${trend.toFixed(1)}</td>
      </tr>
    `;
  }).join("");
}

function formatTime(ms) {
  const total = Math.ceil(ms / 1000);
  const m = Math.floor(total / 60).toString().padStart(2, "0");
  const s = (total % 60).toString().padStart(2, "0");
  return `${m}:${s}`;
}

function render() {
  timerEl.textContent = `Time Left: ${formatTime(game.timeRemainingMs())}`;
  statusEl.textContent = `Status: ${game.paused ? "Paused" : game.running ? "Running" : "Stopped"}`;
  potEl.textContent = game.revealGoal
    ? `Pot: Settled ($${game.goalBonusPaid.toFixed(0)} cards + $${game.majorityPaid.toFixed(0)} majority)`
    : `Pot: $${game.antePot.toFixed(0)} locked`;

  goalEl.textContent = game.revealGoal
    ? `Goal Suit: ${SUITS[game.goalSuitIdx].name} ${SUITS[game.goalSuitIdx].symbol}`
    : "Goal Suit: Hidden";
  winnerEl.textContent = game.revealGoal ? `Majority bonus: ${game.winnerLabel}` : "Majority bonus: Pending";
  if (!game.running && !game.revealGoal) {
    statusEl.textContent = `Status: Ready (Start $${game.startingCash.toFixed(0)}, Ante $${game.ante.toFixed(0)})`;
  }

  marketGridEl.innerHTML = SUITS.map((suit, idx) => {
    const tapeHead = game.tradeTape[0];
    const isTrade = tapeHead && tapeHead.suit === idx;
    const bestBid = game.bestBid(idx, -1);
    const bestAsk = game.bestAsk(idx, -1);
    const bidOwner = bestBid.buyer === null ? "External" : game.players[bestBid.buyer].name;
    const askOwner = bestAsk.seller === null ? "External" : game.players[bestAsk.seller].name;
    return `
      <article class="suit-card ${isTrade ? "trade-flash" : ""}">
        <div class="suit-head">
          <span>${suit.name} ${suit.symbol}</span>
          <span>${game.lastTradeSignedVolume[idx] > 0 ? "↑" : game.lastTradeSignedVolume[idx] < 0 ? "↓" : "•"}</span>
        </div>
        <div class="suit-meta">
          Bid ${bestBid.price.toFixed(2)} · ${bidOwner}<br />
          Ask ${bestAsk.price.toFixed(2)} · ${askOwner}<br />
          Last ${game.lastTradePrice[idx].toFixed(2)}
        </div>
      </article>
    `;
  }).join("");

  botRowsEl.innerHTML = game.players.map((bot, idx) => {
    const mtm = game.markToMarket(bot);
    const recent = game.tradeTape[0];
    const flash = recent && (recent.buyerIdx === idx || recent.sellerIdx === idx) ? "bot-flash" : "";
    const winnerClass = game.revealGoal && game.winnerIdxs.includes(idx) ? "winner-row" : "";
    return `
      <tr class="${flash} ${winnerClass}">
        <td>${bot.name}<span class="bot-style">${bot.style}</span></td>
        <td>${bot.cash.toFixed(2)}</td>
        <td class="${mtm >= 0 ? "pos" : "neg"}">${mtm.toFixed(2)}</td>
        <td>${bot.trades}</td>
        <td>${bot.inventory.join(" / ")}</td>
      </tr>
    `;
  }).join("");

  tapeEl.innerHTML = game.tradeTape.map((t) => `<li>${t.line}</li>`).join("");
  renderStrengthTracker();
}

function onRoundEnded() {
  playBtn.textContent = "Play";
  durationSelect.disabled = false;
  seedInput.disabled = false;
  pauseBtn.disabled = true;
  stepBtn.disabled = true;
  downloadBtn.disabled = false;
  updateStrengthTracker();
  renderExplanation(game);

  const topBankroll = Math.max(...game.players.map((p) => p.cash));
  summaryEl.textContent = `Round complete in ${formatTime(game.durationMs)}. Majority bonus: ${game.winnerLabel}. Pot payouts: $${game.goalBonusPaid.toFixed(0)} card bonuses + $${game.majorityPaid.toFixed(0)} majority. Top bankroll: $${topBankroll.toFixed(2)}.`;
  render();
}

playBtn.addEventListener("click", () => {
  if (game.running) {
    game.stop(false);
    playBtn.textContent = "Play";
    durationSelect.disabled = false;
    seedInput.disabled = false;
    pauseBtn.disabled = true;
    stepBtn.disabled = true;
    downloadBtn.disabled = game.roundLog.length === 0;
    summaryEl.textContent = "Round stopped before settlement.";
    render();
    return;
  }

  const scenario = normalizeScenario(seedInput.value, durationSelect.value);
  const selectedMs = scenario.durationMs;
  const selectedSeed = scenario.seed;
  seedInput.value = selectedSeed;
  durationSelect.value = selectedMs;
  document.getElementById("round-explanation").hidden = true;
  const selectedSpeed = Number(speedSelect.value);
  durationSelect.disabled = true;
  seedInput.disabled = true;
  playBtn.textContent = "Stop";
  pauseBtn.textContent = "Pause";
  pauseBtn.disabled = false;
  stepBtn.disabled = true;
  downloadBtn.disabled = true;
  summaryEl.textContent = `Round in progress... each bot starts with $${game.startingCash.toFixed(0)} and posts a $${game.ante.toFixed(0)} ante (cash at open: $${game.cashAfterAnte.toFixed(0)}).`;
  game.start(selectedMs, selectedSeed, selectedSpeed);
  render();
});

pauseBtn.addEventListener("click", () => {
  game.setPaused(!game.paused);
  pauseBtn.textContent = game.paused ? "Resume" : "Pause";
  stepBtn.disabled = !game.paused;
  render();
});

stepBtn.addEventListener("click", () => {
  game.step(true);
});

speedSelect.addEventListener("change", () => {
  game.speed = Number(speedSelect.value);
  if (game.running && !game.paused) {
    game.schedule();
  }
});

downloadBtn.addEventListener("click", () => {
  const payload = roundPayload(game);
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `figgie-round-seed-${game.seed}.json`;
  link.click();
  URL.revokeObjectURL(url);
});

resetStrengthBtn.addEventListener("click", () => {
  if (!window.confirm("Are you sure you want to reset strength stats?")) {
    return;
  }
  resetStrengthTracker();
});

const initialScenario = scenarioFromUrl(window.location.href);
seedInput.value = initialScenario.seed;
durationSelect.value = initialScenario.durationMs;
game.reset(initialScenario.durationMs, initialScenario.seed);
render();



function payoutBreakdown(round, player) {
  return {
    startingCash: round.startingCash,
    ante: round.ante,
    netTradingCashflow: player.tradingCashflow,
    goalCardPayout: player.goalCardPayout,
    majorityPayout: player.majorityPayout,
    finalBankroll: player.cash,
    netProfit: player.cash - round.startingCash,
  };
}

function roundPayload(round) {
  return {
    schemaVersion: EXPORT_SCHEMA_VERSION,
    simulationVersion: SIMULATION_VERSION,
    settled: round.revealGoal,
    seed: round.seed,
    durationMs: round.durationMs,
    goalSuit: SUITS[round.goalSuitIdx].name,
    winner: round.winnerLabel, // Legacy field: majority-bonus recipients, not profit leaders.
    players: round.players.map((player) => ({
      name: player.name,
      cash: player.cash,
      inventory: [...player.inventory],
      initialInventory: [...player.initialInventory],
      initialGoalProbabilities: [...goalSuitPosterior(player.initialInventory)],
      trades: player.trades,
      payoutBreakdown: round.revealGoal ? payoutBreakdown(round, player) : null,
    })),
    trades: round.roundLog,
  };
}

function renderExplanation(round) {
  const dollars = (value) => `${value < 0 ? "−" : ""}$${Math.abs(value).toFixed(2)}`;
  const highest = Math.max(...round.players.map((p) => p.cash));
  const leaders = round.players.filter((p) => Math.abs(p.cash - highest) < 1e-9);
  document.getElementById("round-explanation").hidden = false;
  document.getElementById("settlementExplanation").textContent =
    `Hindsight: ${SUITS[round.goalSuitIdx].name} was the goal suit. ` +
    `Goal cards paid ${dollars(round.goalBonusPaid)}; the remaining ${dollars(round.majorityPaid)} ` +
    `went to the majority leader(s): ${round.winnerLabel}. ` +
    `Highest profit: ${leaders.map((p) => p.name).join(", ")} ` +
    `(${dollars(highest - round.startingCash)} each). Collecting the most goal cards and earning the most profit are different outcomes.`;
  document.getElementById("payoutRows").innerHTML = round.players.map((player) => {
    const p = payoutBreakdown(round, player);
    return `<tr><th scope="row">${player.name}</th>` +
      [p.startingCash, -p.ante, p.netTradingCashflow, p.goalCardPayout,
        p.majorityPayout, p.finalBankroll, p.netProfit]
        .map((value) => `<td>${dollars(value)}</td>`).join("") + "</tr>";
  }).join("");
  document.getElementById("beliefRows").innerHTML = round.players.map((player) => {
    const posterior = goalSuitPosterior(player.initialInventory);
    const estimates = posterior.map((probability, idx) =>
      `${SUITS[idx].name} ${(probability * 100).toFixed(1)}%`).join(" · ");
    return `<li><strong>${player.name}</strong>: ${estimates}. ` +
      `Initial hand (S/C/H/D): ${player.initialInventory.join("/")}.</li>`;
  }).join("");
  const highlights = round.roundLog.filter((trade) => trade.suit === round.goalSuitIdx)
    .slice().sort((a, b) => b.price - a.price || a.id - b.id).slice(0, 3);
  document.getElementById("tradeHighlights").innerHTML = highlights.length
    ? highlights.map((trade) => `<li>${trade.line}</li>`).join("")
    : "<li>No goal-suit trades occurred in this round.</li>";
}

function scenarioUrl() {
  const scenario = game.running || game.revealGoal
    ? { seed: game.seed, durationMs: game.durationMs }
    : normalizeScenario(seedInput.value, durationSelect.value);
  const url = new URL(window.location.href);
  url.search = "";
  url.hash = "";
  url.searchParams.set("seed", scenario.seed);
  url.searchParams.set("duration", scenario.durationMs);
  return url.href;
}

document.getElementById("shareBtn").addEventListener("click", async () => {
  const url = scenarioUrl();
  const input = document.getElementById("shareUrl");
  input.value = url;
  document.getElementById("shareResult").hidden = false;
  const status = document.getElementById("shareStatus");
  try {
    await navigator.clipboard.writeText(url);
    status.textContent = `Scenario link copied. Reproduces the starting scenario in simulation ${SIMULATION_VERSION}.`;
  } catch {
    status.textContent = "Select and copy the scenario link below the controls.";
    input.focus();
    input.select();
  }
});
