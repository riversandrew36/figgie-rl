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

const BOT_LESSONS = {
  hunter: {
    seed: 5, opponents: ["Hunter", "Banker", "Detective"], condition: "Predict the goal before settlement.",
    brief: "Hunter spends early on the suit it rates highest from its hand. Notice which offers it lifts, then compare that activity with your own hand. You can sell into strong demand when the price is worth more to you than the card.",
    event: "prediction",
  },
  banker: {
    seed: 1, opponents: ["Hunter", "Banker", "Detective"], condition: "Finish with a profit above $0.",
    brief: "Banker rotates between bids and offers and adjusts its prices as its holdings change. Watch both sides before trading. If you disagree with its valuation, a resting quote can buy a cheap card or give you a good exit.",
    event: "profit",
  },
  detective: {
    seed: 19, opponents: ["Hunter", "Banker", "Detective"], condition: "Predict the goal before settlement.",
    brief: "Detective waits for aggressive buys, then puts more weight on the suits buyers are chasing. Compare early and late trades. A quote from Detective can give you a buyer when your own hand suggests the crowd is paying too much.",
    event: "prediction",
  },
  bluffer: {
    seed: 4, opponents: ["Hunter", "Banker", "Bluffer"], condition: "Sell at least one card to Bluffer.",
    brief: "Bluffer buys a low-belief suit early to make demand look stronger. Check the buyer on the tape before following a price move. You can offer cards from a suit you rate low and let Bluffer pay for them.",
    event: "sell",
  },
};

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
    globalThis.render();
    const targets = ["#marketGrid", "#yourRead", '[data-human-action="quote_bid"][data-suit="0"]',
      "#marketGrid", '[data-human-action="quote_ask"][data-suit="2"]', "#tapeItems", "#humanPayout"];
    highlight = document.querySelector?.(targets[step]);
    highlight?.classList.add("tutorial-target");
    if (step === 1) toggle.open = true;
    if (step === 2 || step === 4) {
      selectedSuitIdx = step === 2 ? 0 : 2;
      selectedQuoteSide = step === 2 ? "quote_bid" : "quote_ask";
    }
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
  const predictionResult = byId("predictionResult");
  const lessonStatus = byId("lessonStatus");
  const lessonCards = byId("lessonCards");
  const predictionStats = load("predictions", { correct: 0, total: 0 });
  const progress = load("progress", {});
  let nextLesson = null;
  let activeLesson = null;

  function renderPrediction() {
    byId("goalPrediction").hidden = !isPlayMode() || step >= 0;
    prediction.disabled = !game.running || step >= 0;
    byId("predictionStats").textContent = `Goal predictions: ${predictionStats.correct} correct out of ${predictionStats.total} made.`;
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

  function roundStarted() {
    activeLesson = nextLesson;
    nextLesson = null;
    prediction.value = "";
    predictionResult.textContent = "";
  }

  function roundEnded() {
    const seat = humanPlayerIndex();
    if (seat < 0 || step >= 0) return;
    const picked = prediction.value !== "";
    const correct = picked && Number(prediction.value) === game.goalSuitIdx;
    if (picked) {
      predictionStats.total += 1;
      if (correct) predictionStats.correct += 1;
      save("predictions", predictionStats);
      predictionResult.textContent = `You picked ${SUITS[Number(prediction.value)].name}. ${correct ? "Correct!" : `The goal was ${SUITS[game.goalSuitIdx].name}.`}`;
    }
    if (!activeLesson) return;
    const lesson = BOT_LESSONS[activeLesson];
    const profit = payoutBreakdown(game, game.players[seat]).netProfit;
    const soldToBluffer = game.roundLog.some((trade) =>
      trade.sellerIdx === seat && game.players[trade.buyerIdx].name === "Bluffer");
    const passed = lesson.event === "prediction" ? correct : lesson.event === "profit" ? profit > 0 : soldToBluffer;
    const previous = progress[activeLesson];
    progress[activeLesson] = {
      passed: passed || Boolean(previous?.passed),
      bestProfit: previous ? Math.max(profit, previous.bestProfit) : profit,
    };
    save("progress", progress);
    lessonStatus.textContent = passed ? "Lesson passed." : `Try again. ${lesson.condition}`;
    activeLesson = null;
    renderLessons();
  }

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

  return { render, beforeAction, afterAction, stopTutorial, roundStarted, roundEnded };
})();
globalThis.figgieTeaching = arenaTeaching;
arenaTeaching.render();
