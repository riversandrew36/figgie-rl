// Teaching UI uses only the player's hand and the public trade log for estimates.
function estimateRead(startingHand, hand, trades, seat, cardValue = 10) {
  const prior = goalSuitPosterior(startingHand);
  const flow = SUITS.map(() => 0);
  for (const trade of trades) {
    const buy = trade.aggressorSide === "buy";
    if ((buy ? trade.buyerIdx : trade.sellerIdx) !== seat) flow[trade.suit] += buy ? 1 : -1;
  }
  const weighted = prior.map((p, suit) => p * Math.exp(0.35 * Math.max(-10, Math.min(10, flow[suit]))));
  const total = weighted.reduce((sum, weight) => sum + weight, 0);
  return prior.map((handOdds, suit) => {
    const tapeOdds = weighted[suit] / total;
    const value = tapeOdds * (cardValue + (hand[suit] < 6 ? EXPECTED_POT_REMAINDER / 6 : 0));
    return { handOdds, tapeOdds, value, flow: flow[suit] };
  });
}

function goalPayout(round, counts, seat) {
  const majority = Math.max(...counts);
  const pot = round.antePot - counts.reduce((total, count) => total + count, 0) * round.goalCardValue;
  return counts[seat] * round.goalCardValue
    + (counts[seat] === majority ? pot / counts.filter((count) => count === majority).length : 0);
}

// Undo one transfer while keeping the rest of the final position fixed.
function tradeHindsight(round, seat) {
  const counts = round.players.map((player) => player.inventory[round.goalSuitIdx]);
  const payout = goalPayout(round, counts, seat);
  return round.roundLog.filter((trade) => trade.buyerIdx === seat || trade.sellerIdx === seat).map((trade) => {
    const buy = trade.buyerIdx === seat;
    const without = [...counts];
    if (trade.suit === round.goalSuitIdx) {
      without[trade.buyerIdx] -= 1;
      without[trade.sellerIdx] += 1;
    }
    const payoutDelta = payout - goalPayout(round, without, seat);
    const value = buy ? payoutDelta : -payoutDelta;
    const bankrollDelta = payoutDelta + (buy ? -trade.price : trade.price);
    return { ...trade, buy, value, edge: bankrollDelta };
  });
}

function lessonPassed(id, round, seat, prediction, lockedTick) {
  switch (id) {
    case "hunter":
      return tradeHindsight(round, seat).some((trade) =>
        !trade.buy && round.players[trade.buyerIdx].name === "Hunter" && trade.edge > 0);
    case "bluffer":
      return round.roundLog.some((trade) => trade.sellerIdx === seat
        && trade.suit !== round.goalSuitIdx && round.players[trade.buyerIdx].name === "Bluffer");
    case "detective":
      return prediction === round.goalSuitIdx && lockedTick !== null
        && lockedTick * round.tickMs < round.durationMs / 2;
    case "banker":
      return round.players[seat].cash > round.startingCash;
    default:
      return false;
  }
}

// The final positions are held fixed while a hypothetical transfer is added.
function missedEdges(round, seat) {
  const counts = round.players.map((player) => player.inventory[round.goalSuitIdx]);
  const payout = goalPayout(round, counts, seat);
  const seen = new Map();
  for (const frame of round.coachSnapshots || []) {
    if (round.humanActionTicks?.has(frame.tick)) continue;
    frame.books.forEach(({ bid, ask, held }, suit) => {
      for (const [buy, quote] of [[true, ask], [false, bid]]) {
        if (!quote || (buy ? quote.price > frame.cash : held === 0)) continue;
        const after = [...counts];
        if (suit === round.goalSuitIdx) {
          if ((buy ? after[quote.owner] : after[seat]) === 0) continue;
          after[seat] += buy ? 1 : -1;
          after[quote.owner] += buy ? -1 : 1;
        }
        const delta = goalPayout(round, after, seat) - payout;
        const edge = delta + (buy ? -quote.price : quote.price);
        const key = [buy, suit, quote.owner, quote.price].join(",");
        if (edge > 0 && !seen.has(key)) seen.set(key, { ...quote, tick: frame.tick, buy, suit, edge });
      }
    });
  }
  return [...seen.values()].sort((a, b) => b.edge - a.edge).slice(0, 3);
}

function coachSnapshot(round, seat) {
  const player = round.players[seat];
  const books = SUITS.map((_, suit) => {
    const bid = round.bestBid(suit, seat);
    const ask = round.bestAsk(suit, seat);
    return {
      held: player.inventory[suit],
      bid: bid.buyer === null ? null : { price: bid.price, owner: bid.buyer },
      ask: ask.seller === null ? null : { price: ask.price, owner: ask.seller },
    };
  });
  round.coachSnapshots.push({ tick: round.tick, cash: player.cash, books });
}

function coachMoney(amount) {
  return (amount < -1e-8 ? "−" : "+") + "$" + Math.abs(amount).toFixed(2);
}

function coachTime(round, tick) {
  const seconds = Math.floor(tick * round.tickMs / 1000);
  return Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
}

function tradeReconciliation(round, seat, trades = tradeHindsight(round, seat)) {
  const counts = round.players.map((player) => player.inventory[round.goalSuitIdx]);
  for (const trade of round.roundLog) {
    if (trade.suit !== round.goalSuitIdx || (trade.buyerIdx !== seat && trade.sellerIdx !== seat)) continue;
    counts[trade.buyerIdx] -= 1;
    counts[trade.sellerIdx] += 1;
  }
  const baselineBankroll = round.startingCash - round.ante + goalPayout(round, counts, seat);
  const baseline = baselineBankroll - round.startingCash;
  const edge = trades.reduce((sum, trade) => sum + trade.edge, 0);
  const actual = round.players[seat].cash;
  const interaction = actual - baselineBankroll - edge;
  return { baselineBankroll, baseline, edge, interaction, profit: actual - round.startingCash };
}

function oddsHistory(round, seat) {
  const starting = round.players[seat].initialInventory;
  const hand = [...starting];
  const odds = (trades) => estimateRead(starting, hand, trades, seat).map((row) => row.tapeOdds);
  return [{ tick: 0, odds: odds([]) }, ...round.roundLog.map((trade, index) => {
    if (trade.buyerIdx === seat) hand[trade.suit] += 1;
    if (trade.sellerIdx === seat) hand[trade.suit] -= 1;
    return { tick: trade.tick, odds: odds(round.roundLog.slice(0, index + 1)) };
  })];
}

function coachChart(round, seat, lockedTick) {
  const history = oddsHistory(round, seat);
  const goal = round.goalSuitIdx;
  const leads = (point) => point.odds[goal] === Math.max(...point.odds);
  const first = history.find(leads);
  const lastLoss = history.findLastIndex((point) => !leads(point));
  const sustained = history[lastLoss + 1];
  const summary = first
    ? `Your read first put the goal on top or tied at ${coachTime(round, first.tick)}.` +
      (sustained ? ` It stayed there from ${coachTime(round, sustained.tick)}.` : "")
    : "Your read never put the goal on top.";
  const end = Math.max(1, round.tick, ...history.map((point) => point.tick));
  const left = 42;
  const right = 286;
  const top = 14;
  const bottom = 134;
  const x = (tick) => left + (right - left) * tick / end;
  const y = (odds) => bottom - (bottom - top) * odds;
  const grid = [0, 25, 50, 75, 100].map((percent) => {
    const row = y(percent / 100);
    return `<path class="odds-grid" d="M${left} ${row}H${right}"/>
      <text class="odds-scale" x="${left - 5}" y="${row}" text-anchor="end" dominant-baseline="middle">${percent}%</text>`;
  }).join("");
  const series = SUITS.map((_, suit) => {
    const points = [...history, { ...history.at(-1), tick: end }].map((point) =>
      `${x(point.tick)},${y(point.odds[suit])}`).join(" ");
    return `<polyline points="${points}" class="odds-series odds-${suit}${suit === goal ? " odds-goal" : ""}"/>`;
  }).join("");
  const labels = history.at(-1).odds.map((odds, suit) => ({ odds, suit, row: y(odds) }))
    .sort((a, b) => a.row - b.row);
  // Room for end labels in wide fallback fonts (Linux CI uses DejaVu Sans).
  const gap = 18;
  labels.forEach((label, index) => {
    label.labelRow = Math.max(label.row, index === 0 ? top : labels[index - 1].labelRow + gap);
  });
  for (let index = labels.length - 1; index >= 0; index -= 1) {
    const limit = index === labels.length - 1 ? bottom : labels[index + 1].labelRow - gap;
    labels[index].labelRow = Math.min(labels[index].labelRow, limit);
  }
  const endLabels = labels.map(({ odds, suit, row, labelRow }) =>
    `<g class="odds-${suit}${suit === goal ? " odds-goal-label" : ""}">
      <path class="odds-leader" d="M${right} ${row}L${right + 13} ${labelRow}"/>
      <text class="odds-end-label" data-suit="${suit}" x="${right + 17}" y="${labelRow}" dominant-baseline="middle">${SUITS[suit].name} ${Math.round(100 * odds)}%</text>
    </g>`).join("");
  const lock = lockedTick === null ? "" : `<path class="odds-lock" d="M${x(lockedTick)} ${top}V${bottom}"/>`;
  const markers = round.roundLog.filter((trade) => trade.buyerIdx === seat || trade.sellerIdx === seat)
    .map((trade) => `<circle class="odds-trade" cx="${x(trade.tick)}" cy="${bottom + 4}" r="2.5"/>`).join("");
  return `<p id="coachOddsSummary">${summary}</p>
    <svg class="coach-chart" viewBox="0 0 450 180" role="img" aria-label="${summary}">
      ${grid}
      <path class="odds-axis" d="M${left} ${top}V${bottom}H${right}"/>
      ${series}${lock}${markers}${endLabels}
      <text x="${left}" y="155">0:00</text>
      <text x="${right}" y="155" text-anchor="end">${coachTime(round, end)}</text>
      <text x="${(left + right) / 2}" y="172" text-anchor="middle">Round time</text>
    </svg>
    <p class="odds-legend">${SUITS.map((suit, index) => `<span class="odds-${index}">${suit.name}${index === goal ? " (goal)" : ""}</span>`).join(" · ")}
      · Dots: your trades${lockedTick === null ? "" : ` · Dashed line: prediction locked at ${coachTime(round, lockedTick)}`}</p>`;
}

function coachTakeaways(round, trades, missed) {
  const goal = SUITS[round.goalSuitIdx].name;
  const goalTrades = trades.filter((trade) => trade.suit === round.goalSuitIdx);
  const groups = [true, false].map((buy) => goalTrades.filter((trade) => trade.buy === buy && trade.edge < 0));
  const notes = groups.filter((group) => group.length).map((group) => {
    const impact = -group.reduce((sum, trade) => sum + trade.edge, 0);
    return { impact, text: `You ${group[0].buy ? "bought" : "sold"} ${group.length} goal ${group.length === 1 ? "card" : "cards"} at a total hindsight cost of $${impact.toFixed(2)}. The goal was ${goal}.` };
  });
  if (missed.length) notes.push({ impact: missed[0].edge, text: `The largest missed quote was worth $${missed[0].edge.toFixed(2)} in hindsight.` });
  if (!goalTrades.length) notes.push({ impact: 0, text: `You made 0 trades in the goal suit, ${goal}.` });
  const best = trades.filter((trade) => trade.edge > 0).sort((a, b) => b.edge - a.edge)[0];
  if (best) notes.push({ impact: best.edge, text: `Your best trade added $${best.edge.toFixed(2)} in hindsight on one ${SUITS[best.suit].name} card.` });
  if (!notes.length) notes.push({ impact: 0, text: `You traded ${goalTrades.length} goal ${goalTrades.length === 1 ? "card" : "cards"} with no positive or negative hindsight edge on those trades.` });
  return notes.sort((a, b) => b.impact - a.impact).slice(0, 3).map((note) => note.text);
}

const BOT_LESSONS = {
  hunter: {
    seed: 5, opponents: ["Hunter", "Banker", "Detective"], condition: "Sell Hunter a card for more than keeping it would have paid at settlement.",
    brief: "Hunter spends early on the suit it rates highest from its hand. Notice which offers it lifts, then compare that activity with your own hand. You can sell into strong demand when the price is worth more to you than the card.",
  },
  banker: {
    seed: 1, opponents: ["Hunter", "Banker", "Detective"], condition: "Finish with a profit above $0.",
    brief: "Banker rotates between bids and offers and adjusts its prices as its holdings change. Watch both sides before trading. If you disagree with its valuation, a resting quote can buy a cheap card or give you a good exit.",
  },
  detective: {
    seed: 19, opponents: ["Hunter", "Banker", "Detective"], condition: "Lock in a correct goal prediction before halftime.",
    brief: "Detective waits for aggressive buys, then puts more weight on the suits buyers are chasing. Compare early and late trades. A quote from Detective can give you a buyer when your own hand suggests the crowd is paying too much.",
  },
  bluffer: {
    seed: 4, opponents: ["Hunter", "Banker", "Bluffer"], condition: "Sell Bluffer a card outside the goal suit.",
    brief: "Bluffer buys a low-belief suit early to make demand look stronger. Check the buyer on the tape before following a price move. You can offer cards from a suit you rate low and let Bluffer pay for them.",
  },
};

const DAILY_URL = "https://riversandrew36.github.io/figgie-rl/";

function utcDay(date = new Date()) {
  return date.toISOString().slice(0, 10);
}

function dailySeed(date) {
  let hash = 2166136261;
  for (const char of "figgie-daily-" + date) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619);
  return hash >>> 0;
}

function dailyAttempt(days, date, today) {
  return date === today && !Object.hasOwn(days, date);
}

function dailyStreak(days, today) {
  const dates = Object.keys(days).filter((date) => days[date].firstProfit !== null && date <= today).sort();
  const dayNumber = (date) => Date.parse(date) / 86400000;
  let run = 0;
  let best = 0;
  let previous = -Infinity;
  for (const date of dates) {
    const day = dayNumber(date);
    run = day === previous + 1 ? run + 1 : 1;
    best = Math.max(best, run);
    previous = day;
  }
  return { current: dayNumber(today) - previous <= 1 ? run : 0, best };
}

function dailyShareText(result) {
  const { date, profit, practice, called, lockedTime, edges, streak } = result;
  const prediction = called === null ? "no goal prediction"
    : `${called ? "goal called" : "goal missed"}${lockedTime ? " at " + lockedTime : ""}`;
  const squares = edges.slice(0, 40).map((edge) => edge > 0 ? "🟩" : edge < 0 ? "🟥" : "⬜").join("");
  return [
    `Figgie Learning Lab · Daily ${date}${practice ? " · practice" : ""}`,
    `${coachMoney(profit)} · ${prediction} · ${edges.length} ${edges.length === 1 ? "trade" : "trades"} · ${streak}-day streak`,
    squares ? squares + (edges.length > 40 ? "…" : "") : "",
    DAILY_URL + "?daily=" + date,
  ].filter(Boolean).join("\n");
}

const arenaTeaching = (() => {
  const read = document.getElementById("yourRead");
  const toggle = document.getElementById("readToggle");
  const rows = document.getElementById("readRows");
  function load(key, fallback) {
    try { return JSON.parse(localStorage.getItem("figgie.teaching." + key)) ?? fallback; }
    catch { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem("figgie.teaching." + key, JSON.stringify(value)); }
    catch { /* Keep the current session usable. */ }
  }
  toggle.open = load("read", true);
  toggle.addEventListener("toggle", () => save("read", toggle.open));

  function render() {
    renderPrediction();
    const dailyRunning = Boolean(game.running && activeDaily?.hideSeed);
    seedInput.hidden = dailyRunning;
    byId("seedLabel").hidden = dailyRunning;
    byId("dailySeedLabel").hidden = !dailyRunning;
    if (!game.revealGoal || !game.humanSeated) byId("roundCoach").hidden = true;
    const seat = humanPlayerIndex();
    read.hidden = !isPlayMode();
    if (seat < 0 || !isPlayMode()) {
      rows.textContent = "";
      return;
    }
    const player = game.players[seat];
    const data = estimateRead(player.initialInventory, player.inventory, game.roundLog, seat, game.goalCardValue);
    const percent = (value) => (100 * value).toFixed(1) + "%";
    const markup = data.map(({ handOdds, tapeOdds, value, flow }, suit) => {
      const direction = Math.abs(tapeOdds - handOdds) < 1e-9 ? "unchanged" : tapeOdds > handOdds ? "up" : "down";
      const count = Math.abs(flow);
      const verb = flow > 0 ? "buy" : "sell";
      const evidence = direction === "down" && flow === 0 && data.some((other) => other.flow > 0)
        ? "other suits drew the buying"
        : flow ? `others initiated ${count} more ${verb}${count === 1 ? "" : "s"} than ${flow > 0 ? "sells" : "buys"}`
          : "net aggressive buying here is zero";
      return `<li><strong>${SUITS[suit].name} ${SUITS[suit].symbol}</strong>
        <span>Hand odds ${percent(handOdds)} · Tape-adjusted odds ${percent(tapeOdds)} · Rough value ≈ $${value.toFixed(2)}</span>
        <small>Odds ${direction}: ${evidence}.</small></li>`;
    }).join("");
    if (rows.innerHTML !== markup) rows.innerHTML = markup;
  }

  const byId = (id) => document.getElementById(id);
  const tutorial = byId("tutorial");
  const prompt = byId("learnPrompt");
  const steps = [
    "Find your ten cards on the Market Board. One suit has 12 cards. Its same-color partner scores, but you do not know which suit has 12.",
    "Open Your read and compare the four hand odds. Those estimates use your starting cards.",
    "Post an $8 bid for Spades. A bid needs enough cash to pay the full quoted price.",
    "Hunter posted an offer below your bid. Check the trade price on the board.",
    "The crossing traded at your resting $8 bid and cleared every quote. Hearts looks less likely from this hand. Offer a Heart at $8 to turn a card into cash. Banker will lift your offer.",
    "Watch the tape. Hunter just bought Clubs aggressively. Compare the tape-adjusted odds to your hand odds.",
    "Each goal card pays $10. Players tied for the most goal cards split what remains. See Your settlement for your result.",
  ];
  const checks = {
    0: { question: "Which suit scores?", answers: ["The 12-card suit", "Its same-color partner"], correct: 1 },
    1: { question: "What goes into hand odds?", answers: ["Starting cards", "Current bids and offers"], correct: 0 },
    3: { question: "What price did the crossing trade use?", answers: ["The $7 offer", "The $8 resting bid"], correct: 1 },
    5: { question: "Which suit just gained tape-adjusted odds?", answers: ["Clubs", "Diamonds"], correct: 0 },
  };
  const deal = [[3,3,2,2], [2,4,2,2], [1,2,3,4], [2,3,3,2]];
  let step = -1;
  let highlight;
  const specs = [
    { name: "You", strategy: -1, isHuman: true },
    ...BOT_NAMES.slice(0, 3).map((name, strategy) => ({ name, strategy })),
  ];

  function dismissPrompt() {
    prompt.hidden = true;
    save("promptDismissed", true);
  }

  function showStep() {
    highlight?.classList.remove("tutorial-target");
    byId("tutorialInstruction").textContent = `Step ${step + 1} of 7. ${steps[step]}`;
    byId("tutorialHint").textContent = "";
    const check = checks[step];
    byId("tutorialCheckLabel").hidden = !check;
    if (check) {
      byId("tutorialQuestion").textContent = check.question;
      byId("tutorialCheck").innerHTML = '<option value="">Choose an answer</option>' +
        check.answers.map((answer, index) => `<option value="${index}">${answer}</option>`).join("");
    }
    byId("tutorialBack").disabled = step === 0;
    byId("tutorialNext").hidden = [2, 4, 6].includes(step);
    byId("tutorialFinish").hidden = step !== 6;
    if (step === 2 || step === 4) {
      selectedSuitIdx = step === 2 ? 0 : 2;
      selectedQuoteSide = step === 2 ? "quote_bid" : "quote_ask";
    }
    globalThis.render();
    const targets = ["#tableBook", "#yourRead", '[data-table-action="quote_bid"]',
      "#tableBook", '[data-table-action="quote_ask"]', "#tableFeed", "#humanPayout"];
    highlight = document.querySelector?.(targets[step]);
    highlight?.classList.add("tutorial-target");
    if (step === 1) toggle.open = true;
    (check ? byId("tutorialCheck") : step === 2 || step === 4 ? highlight : byId("tutorialTitle"))?.focus();
  }

  function crossingBid() {
    game.applyAction(2, { kind: "quote_bid", suit: 1, price: 5 });
    game.applyAction(1, { kind: "quote_ask", suit: 0, price: 7 });
  }

  function liftOffer() { game.applyAction(2, { kind: "buy", suit: 2 }); }

  function moveTape() {
    game.applyAction(3, { kind: "quote_ask", suit: 1, price: 6 });
    game.applyAction(1, { kind: "buy", suit: 1 });
  }

  function restoreTutorial(target) {
    game.loadDeal({ inventories: deal, goalSuitIdx: 0, playerSpecs: specs });
    game.running = true;
    game.paused = true;
    game.revealGoal = false;
    game.lastActionMessage = "";
    game.humanPriceDrafts.fill(8);
    clearExplanation();
    if (target >= 3) {
      game.applyAction(0, { kind: "quote_bid", suit: 0, price: 8 });
      crossingBid();
    }
    if (target >= 5) {
      game.applyAction(0, { kind: "quote_ask", suit: 2, price: 8 });
      liftOffer();
      moveTape();
    }
    step = target;
    showStep();
  }

  function startTutorial() {
    marketModeSelect.value = "players";
    for (const id of Object.keys(PPO_SEATS)) byId("opponent" + id).checked = false;
    if (step >= 0) return;
    if (game.running) playBtn.click();
    dismissPrompt();
    playModeInput.checked = true;
    refreshModePreview();
    game.elapsedMs = 0;
    tutorial.hidden = false;
    [playBtn, pauseBtn, downloadBtn, playModeInput, watchModeInput, durationSelect, seedInput]
      .forEach((input) => { input.disabled = true; });
    for (const name of OPPONENT_IDS) byId("opponent" + name).disabled = true;
    restoreTutorial(0);
  }

  function stopTutorial() {
    if (step < 0) return false;
    step = -1;
    highlight?.classList.remove("tutorial-target");
    tutorial.hidden = true;
    game.stop(false);
    [playModeInput, watchModeInput, durationSelect, seedInput]
      .forEach((input) => { input.disabled = false; });
    for (const name of OPPONENT_IDS) byId("opponent" + name).disabled = false;
    refreshModePreview();
    byId("learnBasics").focus();
    return true;
  }

  function beforeAction(kind, suit) {
    if (step < 0) return true;
    const expected = step === 2 ? "quote_bid" : step === 4 ? "quote_ask" : null;
    const price = Number(document.querySelector?.(`.human-price[data-suit="${suit}"]`)?.value);
    if (kind === expected && suit === (step === 2 ? 0 : 2) && price === 8) return true;
    byId("tutorialHint").textContent = expected
      ? `Try the ${step === 2 ? "Spades Bid" : "Hearts Offer"} button with the price set to $8.`
      : "Use Continue when you are ready for the next step.";
    return false;
  }

  function afterAction() {
    if (step === 2) {
      crossingBid();
      step = 3;
      showStep();
    } else if (step === 4) {
      liftOffer();
      moveTape();
      step = 5;
      showStep();
    }
  }

  function nextStep() {
    if (step < 0 || [2, 4, 6].includes(step)) return;
    if (checks[step] && byId("tutorialCheck").value !== String(checks[step].correct)) {
      byId("tutorialHint").textContent = "Take another look at the highlighted area and try again.";
      byId("tutorialCheck").focus();
      return;
    }
    step += 1;
    if (step === 6) {
      game.stop(true);
      renderExplanation(game);
    }
    showStep();
  }

  function startFrontRound(seed) {
    marketModeSelect.value = "players";
    for (const id of Object.keys(PPO_SEATS)) byId("opponent" + id).checked = false;
    if (step >= 0) stopTutorial();
    else if (game.running) playBtn.click();
    playModeInput.checked = true;
    watchModeInput.checked = false;
    durationSelect.value = "60000";
    seedInput.value = seed;
    BOT_NAMES.forEach((name, index) => { byId("opponent" + name).checked = index < 3; });
    refreshModePreview();
    playBtn.click();
    byId("pokerTable")?.scrollIntoView?.({ block: "start" });
  }

  byId("playNow").addEventListener("click", () => startFrontRound(Math.floor(Math.random() * 2 ** 32)));

  function startRealRound() {
    stopTutorial();
    durationSelect.value = "60000";
    seedInput.value = Math.floor(Math.random() * 2147483647);
    playBtn.click();
  }

  prompt.hidden = load("promptDismissed", false) || new URL(window.location.href).search !== "";
  byId("learnBasics").addEventListener("click", startTutorial);
  byId("promptLearn").addEventListener("click", startTutorial);
  byId("dismissPrompt").addEventListener("click", dismissPrompt);
  byId("tutorialBack").addEventListener("click", () => { if (step > 0) restoreTutorial(step - 1); });
  byId("tutorialNext").addEventListener("click", nextStep);
  byId("tutorialSkip").addEventListener("click", stopTutorial);
  byId("tutorialPlay").addEventListener("click", startRealRound);
  byId("tutorialLesson").addEventListener("click", () => {
    stopTutorial();
    byId("lessonTitle").focus();
  });
  document.addEventListener?.("keydown", (event) => {
    if (step < 0) return;
    if (event.target === byId("tutorialCheck") && /^[12]$/.test(event.key)) {
      event.preventDefault();
      event.stopImmediatePropagation();
      byId("tutorialCheck").value = String(Number(event.key) - 1);
      return;
    }
    if (event.key === "Escape" || (event.key === "Enter" && [byId("tutorialTitle"), byId("tutorialCheck")].includes(event.target))) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (event.key === "Escape") stopTutorial();
      else nextStep();
    }
  }, true);

  const prediction = byId("predictionPick");
  const lock = byId("predictionLock");
  let lockedTick = null;
  const predictionResult = byId("predictionResult");
  const lessonStatus = byId("lessonStatus");
  const lessonCards = byId("lessonCards");
  const predictionStats = load("predictions", { correct: 0, total: 0 });
  const previousProgress = load("progress", {});
  const migratedProgress = Object.fromEntries(Object.keys(BOT_LESSONS).flatMap((id) => {
    const previous = previousProgress[id];
    if (!Number.isFinite(previous?.bestProfit)) return [];
    return [[id, { passed: id === "banker" && Boolean(previous.passed), bestProfit: previous.bestProfit }]];
  }));
  const progress = load("skillProgress", migratedProgress);
  const storedHistory = load("rounds", []);
  const history = Array.isArray(storedHistory) ? storedHistory.slice(-20) : [];
  let nextLesson = null;
  let activeLesson = null;

  function renderPrediction() {
    byId("goalPrediction").hidden = !isPlayMode() || step >= 0;
    prediction.disabled = !game.running || step >= 0 || lockedTick !== null;
    lock.disabled = prediction.disabled || prediction.value === "";
    const early = predictionStats.correct ? Math.round(100 * (predictionStats.earlyCorrect || 0) / predictionStats.correct) : 0;
    byId("predictionStats").textContent = `Goal predictions: ${predictionStats.correct} correct out of ${predictionStats.total} made. ${early}% of correct picks locked before halftime.`;
  }

  function renderProgress() {
    const recent = history.slice(-10);
    const count = recent.reduce((sum, round) => sum + round.trades, 0);
    const total = recent.reduce((sum, round) => sum + round.edge, 0);
    byId("edgeStats").textContent = count
      ? `Average hindsight edge per trade: ${coachMoney(total / count)} across the last ${recent.length} Play rounds (${count} trades).`
      : "Average hindsight edge per trade: no recent trades.";
    const profits = history.map((round) => round.profit);
    if (!profits.length) {
      byId("profitTrend").textContent = "";
      return;
    }
    const minimum = Math.min(0, ...profits);
    const maximum = Math.max(0, ...profits);
    const y = (profit) => 33 - 28 * (profit - minimum) / (maximum - minimum || 1);
    const points = profits.map((profit, i) => `${5 + i * 190 / Math.max(1, profits.length - 1)},${y(profit)}`).join(" ");
    const label = `Net profit over ${profits.length} Play rounds. Latest ${coachMoney(profits.at(-1))}.`;
    byId("profitTrend").innerHTML = `<p class="small">${label}</p>
      <svg class="profit-spark" viewBox="0 0 200 38" role="img" aria-label="${label}">
        <path class="odds-axis" d="M5 ${y(0)}H195"/>
        <polyline class="odds-series odds-1" points="${points}"/>
        <circle class="odds-trade" cx="${profits.length > 1 ? 195 : 5}" cy="${y(profits.at(-1))}" r="2"/>
      </svg>`;
  }

  function renderLessons() {
    lessonCards.innerHTML = Object.entries(BOT_LESSONS).map(([id, lesson]) => {
      const name = id[0].toUpperCase() + id.slice(1);
      const record = progress[id];
      return `<article id="lesson-${id}">
        <h3>${name}</h3><p>${lesson.brief}</p><p><strong>Pass:</strong> ${lesson.condition}</p>
        <p class="small">${record ? `${record.passed ? "Passed" : "Tried"} · Best profit $${Number(record.bestProfit).toFixed(2)}` : "Ready to try"}</p>
        <div class="teaching-actions">
          <button data-lesson="${id}" type="button">Start ${name} lesson</button>
          <button data-share-lesson="${id}" class="reset-btn" type="button">Share ${name} lesson</button>
        </div>
      </article>`;
    }).join("");
  }

  function prepareLesson(id) {
    marketModeSelect.value = "players";
    for (const id of Object.keys(PPO_SEATS)) byId("opponent" + id).checked = false;
    const lesson = BOT_LESSONS[id];
    if (step >= 0) stopTutorial();
    else if (game.running) playBtn.click();
    playModeInput.checked = true;
    watchModeInput.checked = false;
    seedInput.value = lesson.seed;
    durationSelect.value = "60000";
    for (const name of BOT_NAMES) byId("opponent" + name).checked = lesson.opponents.includes(name);
    refreshModePreview();
    lessonStatus.textContent = `Lesson ready. ${lesson.condition}`;
  }

  function startLesson(id) {
    prepareLesson(id);
    nextLesson = id;
    playBtn.click();
  }

  async function shareLesson(id) {
    const url = new URL(window.location.href);
    url.search = "";
    url.hash = "";
    url.searchParams.set("lesson", id);
    const field = byId("lessonLink");
    field.value = url.href;
    field.hidden = false;
    try {
      await navigator.clipboard.writeText(url.href);
      lessonStatus.textContent = "Lesson link copied.";
    } catch {
      lessonStatus.textContent = "Select and copy this lesson link.";
      field.focus();
      field.select();
    }
  }

  prediction.addEventListener("change", renderPrediction);
  lock.addEventListener("click", () => {
    if (lock.disabled) return;
    lockedTick = game.tick;
    predictionResult.textContent = `Locked in ${SUITS[Number(prediction.value)].name}.`;
    renderPrediction();
  });

  function roundStarted() {
    activeDaily = pendingDaily;
    pendingDaily = null;
    byId("dailyResult").hidden = true;
    lockedTick = null;
    activeLesson = nextLesson;
    nextLesson = null;
    prediction.value = "";
    predictionResult.textContent = "";
  }

  function renderCoach(seat) {
    const coach = byId("roundCoach");
    const trades = tradeHindsight(game, seat);
    const missed = missedEdges(game, seat);
    const totals = tradeReconciliation(game, seat, trades);
    const payout = payoutBreakdown(game, game.players[seat]);
    const rows = trades.map((trade) => [
      coachTime(game, trade.tick), trade.buy ? "Buy" : "Sell", SUITS[trade.suit].name,
      "$" + trade.price.toFixed(2), game.players[trade.buy ? trade.sellerIdx : trade.buyerIdx].name,
      coachMoney(trade.value), coachMoney(trade.edge),
    ]);
    const tone = (index) => trades[index].edge > 0 ? "pos" : trades[index].edge < 0 ? "neg" : "";
    byId("coachTrades").innerHTML = rows.length ? rows.map((row, index) => `<tr>${row.map((value, column) =>
      `<td class="${column === 6 ? tone(index) : ""}">${value}</td>`).join("")}</tr>`).join("")
      : '<tr><td colspan="7">You made no trades.</td></tr>';
    const labels = ["Time", "Side", "Suit", "Price", "Counterparty", "Value at settlement", "Edge"];
    byId("coachTradeCards").innerHTML = rows.length ? rows.map((row, index) => `<li><dl>${row.map((value, column) =>
      `<div><dt>${labels[column]}</dt><dd class="${column === 6 ? tone(index) : ""}">${value}</dd></div>`).join("")}</dl></li>`).join("")
      : "<li>You made no trades.</li>";
    byId("coachTotals").textContent = `Net profit ${coachMoney(totals.profit)} = no-trade baseline ${coachMoney(totals.baseline)} + trade edges (${coachMoney(totals.edge)}) + Combined majority effect (${coachMoney(totals.interaction)}).`;
    byId("coachInteraction").hidden = Math.abs(totals.interaction) < 1e-8;
    const goalTrades = trades.filter((trade) => trade.suit === game.goalSuitIdx);
    const marginalMajority = goalTrades.reduce((sum, trade) =>
      sum + (trade.buy ? 1 : -1) * (trade.value - game.goalCardValue), 0);
    const combinedMajority = marginalMajority + totals.interaction;
    const tied = game.winnerIdxs.includes(seat) && game.winnerIdxs.length > 1;
    byId("coachInteraction").textContent = `Your ${goalTrades.length} ${SUITS[game.goalSuitIdx].name} trades counted ${coachMoney(marginalMajority)} in majority changes individually, versus ${coachMoney(combinedMajority)} together, so the correction is ${coachMoney(totals.interaction)}.${tied ? ` You tied for the lead and received $${payout.majorityPayout.toFixed(2)} of the majority pot.` : ""}`;
    byId("coachPayouts").textContent = `Actual payouts: goal cards ${coachMoney(payout.goalCardPayout)} · majority ${coachMoney(payout.majorityPayout)}.`;
    byId("coachOdds").innerHTML = coachChart(game, seat, lockedTick);
    byId("coachMissed").innerHTML = missed.length ? missed.map((quote) => `<li>${coachTime(game, quote.tick)} · ${quote.buy ? "Buy" : "Sell"} ${SUITS[quote.suit].name} at $${quote.price} with ${game.players[quote.owner].name} · ${coachMoney(quote.edge)} in hindsight</li>`).join("") : "<li>No positive missed edges in the recorded quotes.</li>";
    byId("coachTakeaways").innerHTML = coachTakeaways(game, trades, missed).map((note) => `<li>${note}</li>`).join("");
    coach.hidden = false;
    return { edge: totals.edge, profit: totals.profit, trades: trades.length };
  }

  function roundEnded() {
    const seat = humanPlayerIndex();
    if (seat < 0 || step >= 0 || !game.revealGoal) return;
    history.push(renderCoach(seat));
    if (history.length > 20) history.shift();
    save("rounds", history);
    renderProgress();
    const picked = prediction.value !== "";
    const correct = picked && Number(prediction.value) === game.goalSuitIdx;
    if (picked) {
      predictionStats.total += 1;
      if (correct) {
        predictionStats.correct += 1;
        if (lockedTick !== null && lockedTick * game.tickMs < game.durationMs / 2) {
          predictionStats.earlyCorrect = (predictionStats.earlyCorrect || 0) + 1;
        }
      }
      save("predictions", predictionStats);
      predictionResult.textContent = `You picked ${SUITS[Number(prediction.value)].name}. ${correct ? "Correct!" : `The goal was ${SUITS[game.goalSuitIdx].name}.`}`;
    }
    if (activeDaily) finishDaily(seat, picked ? correct : null);
    renderFront();
    if (!activeLesson) return;
    const lesson = BOT_LESSONS[activeLesson];
    const profit = payoutBreakdown(game, game.players[seat]).netProfit;
    const passed = lessonPassed(activeLesson, game, seat, picked ? Number(prediction.value) : null, lockedTick);
    const previous = progress[activeLesson];
    progress[activeLesson] = {
      passed: passed || Boolean(previous?.passed),
      bestProfit: previous ? Math.max(profit, previous.bestProfit) : profit,
    };
    save("skillProgress", progress);
    lessonStatus.textContent = passed ? "Lesson passed." : `Try again. ${lesson.condition}`;
    activeLesson = null;
    renderLessons();
    renderFront();
  }

  byId("coachReplay").addEventListener("click", () => {
    if (!game.revealGoal || !game.humanSeated) return;
    const lineup = game.players.filter((player) => !player.isHuman).map((player) => player.policyId || player.name);
    playModeInput.checked = true;
    seedInput.value = game.seed;
    durationSelect.value = game.durationMs;
    for (const id of OPPONENT_IDS) byId("opponent" + id).checked = lineup.includes(id);
    refreshModePreview();
    playBtn.click();
  });
  byId("coachShare").addEventListener("click", () => byId("shareBtn").click());
  byId("resetCoachProgress").addEventListener("click", () => {
    if (!window.confirm("Reset local Play predictions, lesson results, and profit history?")) return;
    history.length = 0;
    Object.assign(predictionStats, { total: 0, correct: 0, earlyCorrect: 0 });
    for (const id of Object.keys(progress)) delete progress[id];
    save("rounds", history);
    save("predictions", predictionStats);
    save("skillProgress", progress);
    lessonStatus.textContent = "Play progress reset.";
    renderPrediction();
    renderProgress();
    renderLessons();
  });
  renderProgress();
  lessonCards.addEventListener("click", (event) => {
    const { lesson, shareLesson: share } = event.target.dataset;
    if (Object.hasOwn(BOT_LESSONS, lesson)) startLesson(lesson);
    if (Object.hasOwn(BOT_LESSONS, share)) shareLesson(share);
  });
  renderLessons();
  const shared = new URL(window.location.href).searchParams.get("lesson");
  if (Object.hasOwn(BOT_LESSONS, shared)) {
    prepareLesson(shared);
    byId("lesson-" + shared)?.scrollIntoView();
  }

  const dailyKey = "figgie.teaching.daily";
  const dailyQuery = new URL(window.location.href).searchParams.get("daily");
  function selectedDay(today) {
    if (!dailyQuery || !/^\d{4}-\d{2}-\d{2}$/.test(dailyQuery)) return today;
    const parsed = new Date(dailyQuery);
    return Number.isFinite(+parsed) && utcDay(parsed) === dailyQuery && dailyQuery <= today ? dailyQuery : today;
  }

  let days = {};
  let canStoreDaily = true;
  try {
    days = JSON.parse(localStorage.getItem(dailyKey)) || {};
    if (typeof days !== "object" || Array.isArray(days)) days = {};
  } catch { canStoreDaily = false; }
  let pendingDaily = null;
  let activeDaily = null;
  let result = null;

  function persistDaily() {
    if (!canStoreDaily) return;
    try { localStorage.setItem(dailyKey, JSON.stringify(days)); }
    catch { canStoreDaily = false; }
  }

  function renderFront() {
    const today = utcDay();
    const date = selectedDay(today);
    const record = days[date];
    const streak = dailyStreak(days, today);
    const status = date !== today ? "Practice deal" : !record ? "Not played"
      : record.firstProfit === null ? "Scored attempt used · practice available"
        : `Played: ${coachMoney(record.firstProfit)} · practice available`;
    byId("dailyTitle").textContent = date === today ? "Today’s deal" : "Daily practice";
    byId("dailyStatus").textContent = `${date} UTC · ${status} · ${streak.current}-day streak` +
      (canStoreDaily ? "" : " · Storage unavailable. Results won’t be saved.");
    const welcome = byId("welcomeBack");
    welcome.hidden = true;
    try {
      localStorage.getItem(dailyKey);
      const passed = Object.values(progress).filter((lesson) => lesson.passed).length;
      if (strengthTracker.rounds || passed || streak.current || streak.best) {
        welcome.hidden = false;
        welcome.textContent = `Welcome back · ${strengthTracker.rounds} rounds played · ${passed} lessons passed · ${streak.current}-day daily streak`;
      }
    } catch { /* Storage is unavailable. */ }
  }

  function startDaily() {
    const today = utcDay();
    const date = selectedDay(today);
    const scored = dailyAttempt(days, date, today);
    if (scored) {
      days[date] = { firstProfit: null, best: null, called: null };
      persistDaily();
    }
    pendingDaily = { date, scored, hideSeed: date === today };
    startFrontRound(dailySeed(date));
    renderFront();
  }

  function finishDaily(seat, called) {
    const { date, scored } = activeDaily;
    activeDaily = null;
    const profit = payoutBreakdown(game, game.players[seat]).netProfit;
    const record = days[date];
    if (record) {
      record.best = record.best === null ? profit : Math.max(record.best, profit);
      if (scored) Object.assign(record, { firstProfit: profit, called });
      persistDaily();
    }
    const streak = dailyStreak(days, utcDay());
    const edges = tradeHindsight(game, seat).map((trade) => trade.edge);
    result = { date, profit, called, practice: !scored, edges, streak: streak.current,
      lockedTime: lockedTick === null ? null : coachTime(game, lockedTick) };
    const best = edges.length ? coachMoney(Math.max(...edges)) : "None";
    byId("dailyResultTitle").textContent = `Daily ${date} · ${scored ? "Scored result" : "Practice result"}`;
    byId("dailyResultSummary").textContent = `Profit ${coachMoney(profit)} · ${edges.length} trades · Best trade edge ${best}`;
    byId("dailyResultPrediction").textContent = (called === null ? "No goal prediction." : called ? "Goal called." : "Goal missed.") +
      (result.lockedTime ? ` Locked at ${result.lockedTime}.` : called === null ? "" : " Pick wasn’t locked.");
    byId("dailyResultStreak").textContent = `Current: ${streak.current}-day streak · Best: ${streak.best}-day streak` +
      (canStoreDaily ? "" : " · Storage unavailable. This result wasn’t saved.");
    byId("dailyShareField").hidden = true;
    byId("dailyShareStatus").textContent = "";
    byId("dailyResult").hidden = false;
  }

  byId("playDaily").addEventListener("click", startDaily);
  byId("dailyShare").addEventListener("click", async () => {
    if (!result) return;
    const field = byId("dailyShareField");
    field.value = dailyShareText(result);
    field.hidden = false;
    try {
      await navigator.clipboard.writeText(field.value);
      byId("dailyShareStatus").textContent = "Result copied.";
    } catch {
      byId("dailyShareStatus").textContent = "Select and copy your result.";
      field.focus();
      field.select();
    }
  });
  renderFront();

  return { render, beforeAction, afterAction, stopTutorial, roundStarted, roundEnded };
})();
globalThis.figgieTeaching = arenaTeaching;
arenaTeaching.render();
