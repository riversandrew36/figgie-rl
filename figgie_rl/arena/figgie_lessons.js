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
      const evidence = flow ? `others initiated ${Math.abs(flow)} more ${flow > 0 ? "buys than sells" : "sells than buys"} in this suit` : "net aggressive buying here is zero";
      return `<li><strong>${SUITS[suit].name} ${SUITS[suit].symbol}</strong>
        <span>Hand odds ${percent(handOdds)} · Tape-adjusted odds ${percent(tapeOdds)} · Rough value ≈ $${value.toFixed(2)}</span>
        <small>Odds ${direction}. ${evidence.charAt(0).toUpperCase() + evidence.slice(1)}.</small></li>`;
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
    "Hunter offered below your bid. The trade printed at your resting $8 bid, and every other quote cleared.",
    "Hearts looks less likely from this hand. Offer a Heart at $8 to turn a card into cash. Banker will lift your offer.",
    "Watch the tape. Hunter just bought Clubs aggressively. Compare the tape-adjusted odds to your hand odds.",
    "Each goal card pays $10. Players tied for the most goal cards split what remains. See Your settlement for your result.",
  ];
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
    byId("tutorialBack").disabled = step === 0;
    byId("tutorialNext").hidden = [2, 4, 6].includes(step);
    byId("tutorialFinish").hidden = step !== 6;
    renderArena();
    const targets = ["#marketGrid", "#yourRead", '[data-human-action="quote_bid"][data-suit="0"]',
      "#marketGrid", '[data-human-action="quote_ask"][data-suit="2"]', "#tapeItems", "#humanPayout"];
    highlight = document.querySelector?.(targets[step]);
    highlight?.classList.add("tutorial-target");
    if (step === 1) toggle.open = true;
    if (step === 2 || step === 4) {
      selectedSuitIdx = step === 2 ? 0 : 2;
      selectedQuoteSide = step === 2 ? "quote_bid" : "quote_ask";
    }
    (step === 2 || step === 4 ? highlight : byId("tutorialTitle"))?.focus();
  }

  function renderArena() { globalThis.render(); }

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
    if (step >= 0) return;
    if (game.running) playBtn.click();
    dismissPrompt();
    playModeInput.checked = true;
    refreshModePreview();
    game.elapsedMs = 0;
    tutorial.hidden = false;
    [playBtn, pauseBtn, downloadBtn, playModeInput, watchModeInput, durationSelect, seedInput]
      .forEach((input) => { input.disabled = true; });
    for (const name of BOT_NAMES) byId("opponent" + name).disabled = true;
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
    for (const name of BOT_NAMES) byId("opponent" + name).disabled = false;
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
    step += 1;
    if (step === 6) {
      game.stop(true);
      renderExplanation(game);
    }
    showStep();
  }

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
  byId("tutorialLesson").addEventListener("click", stopTutorial);
  document.addEventListener?.("keydown", (event) => {
    if (step < 0) return;
    if (event.key === "Escape" || (event.key === "Enter" && event.target === byId("tutorialTitle"))) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (event.key === "Escape") stopTutorial();
      else nextStep();
    }
  }, true);

  return { render, load, save, beforeAction, afterAction, stopTutorial,
    roundStarted() {}, roundEnded() {} };
})();
globalThis.figgieTeaching = arenaTeaching;
arenaTeaching.render();
