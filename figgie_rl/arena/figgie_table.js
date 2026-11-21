// Poker-table view of the arena. It is a presentation layer only: it reads the
// shared `game` state and sends your actions through `performHumanAction`, so
// rules, validation and seeded play are identical to the classic arena layout.
// The view turns on at play.html (Pages) or with ?view=table (local file).
(() => {
  const url = new URL(window.location.href);
  const tableView = /\/play(\.html)?$/.test(url.pathname) || url.searchParams.get("view") === "table";
  if (!tableView) return;

  document.documentElement.classList.add("table-view");
  const byId = (id) => document.getElementById(id);
  const tableEl = byId("pokerTable");
  const shell = document.querySelector("main.shell");
  if (!tableEl || !shell) return;
  tableEl.hidden = false;
  const feedPanel = byId("tableFeedPanel");
  if (feedPanel) feedPanel.hidden = false;

  // The lobby is this same page without the table switch.
  const lobby = new URL(url.href);
  lobby.hash = "";
  lobby.searchParams.delete("view");
  if (/\/play(\.html)?$/.test(lobby.pathname)) lobby.pathname = lobby.pathname.replace(/play(\.html)?$/, "");
  for (const link of tableEl.querySelectorAll("[data-lobby-link]")) link.href = lobby.href;
  const lessonLink = byId("tutorialLesson");
  if (lessonLink) lessonLink.href = `${lobby.href.split("#")[0]}#lessons`;

  // Arrange the existing panels around the table. Moving nodes keeps their ids
  // and listeners, so the teaching, coach and daily-deal code keeps working.
  const layout = document.createElement("div");
  layout.className = "table-layout";
  const mainColumn = document.createElement("div");
  mainColumn.className = "table-main";
  const side = document.createElement("aside");
  side.className = "table-side";
  side.setAttribute("aria-label", "Round tools");
  shell.insertBefore(layout, shell.firstChild);
  layout.append(mainColumn, side);
  for (const id of ["arena", "pokerTable", "dailyResult", "roundCoach", "round-explanation"]) {
    const node = byId(id);
    if (node) mainColumn.append(node);
  }
  for (const id of ["learnPrompt", "tutorial", "goalPrediction", "yourRead", "tableFeedPanel"]) {
    const node = byId(id);
    if (node) side.append(node);
  }

  const seatEls = {
    bottom: byId("seatBottom"), left: byId("seatLeft"), top: byId("seatTop"), right: byId("seatRight"),
  };
  const bookEl = byId("tableBook");
  const centerEl = byId("tableCenter");
  const handEl = byId("tableHand");
  const actionsEl = byId("tableActions");
  const feedEl = byId("tableFeed");
  const priceInput = byId("tablePrice");
  const statusEls = {
    timer: byId("tableTimer"), pot: byId("tablePot"), goal: byId("tableGoal"), majority: byId("tableMajority"),
  };
  const RED = new Set([2, 3]);
  const money = (value) => `$${Number(value).toFixed(0)}`;
  const signed = (value) => `${value >= 0 ? "+" : "−"}$${Math.abs(value).toFixed(0)}`;
  const suitMark = (suit) => `<span class="${RED.has(suit) ? "suit-red" : "suit-black"}" aria-hidden="true">${SUITS[suit].symbol}</span>`;
  let lastTradeId = -1;
  let flashUntilTick = -1;

  // Bottom is you in Play, or seat 0 in Watch; the rest go clockwise.
  function seatOrder() {
    const me = humanPlayerIndex();
    const bottom = me >= 0 ? me : 0;
    return [bottom, (bottom + 1) % 4, (bottom + 2) % 4, (bottom + 3) % 4];
  }

  function hiddenFromYou(player) {
    return game.humanSeated && !game.revealGoal && !player.isHuman;
  }

  function seatMarkup(idx) {
    const player = game.players[idx];
    if (!player) return "";
    const hidden = hiddenFromYou(player);
    const cards = player.inventory.reduce((sum, count) => sum + count, 0);
    const quotes = SUITS.map((_, suit) => [
      Number.isFinite(player.bidQuotes[suit]) ? `Bid ${suitMark(suit)} ${money(player.bidQuotes[suit])}` : "",
      Number.isFinite(player.askQuotes[suit]) ? `Offer ${suitMark(suit)} ${money(player.askQuotes[suit])}` : "",
    ]).flat().filter(Boolean);
    const recent = game.tradeTape.find((trade) => trade.buyerIdx === idx || trade.sellerIdx === idx);
    const fresh = recent && game.tick - recent.tick <= 8;
    const bubble = fresh
      ? `${recent.buyerIdx === idx ? "Bought" : "Sold"} ${suitMark(recent.suit)} ${money(recent.price)}`
      : "";
    const winner = game.revealGoal && game.winnerIdxs?.includes(idx);
    const profit = player.cash - game.startingCash;
    const stats = hidden
      ? `${cards} cards · ${player.trades} trades`
      : `${money(player.cash)} · ${cards} cards · ${player.trades} trades`;
    const hand = !hidden && !player.isHuman
      ? `<div class="seat-hand">${SUITS.map((_, suit) => `<span>${suitMark(suit)}${player.inventory[suit]}</span>`).join("")}</div>`
      : "";
    return `
      <div class="seat-name">${player.isHuman ? "You" : player.name}${winner ? ' <span class="seat-badge">Majority</span>' : ""}</div>
      <div class="seat-stats">${stats}</div>
      ${hand}
      <div class="seat-quotes">${quotes.length ? quotes.join(" · ") : "No quotes"}</div>
      ${game.revealGoal ? `<div class="seat-result ${profit >= 0 ? "pos" : "neg"}">${signed(profit)}</div>` : ""}
      <div class="seat-bubble" ${bubble ? "" : "hidden"}>${bubble}</div>`;
  }

  function renderSeats(newTrade) {
    const order = seatOrder();
    ["bottom", "left", "top", "right"].forEach((position, slot) => {
      const idx = order[slot];
      const el = seatEls[position];
      const player = game.players[idx];
      const markup = seatMarkup(idx);
      if (el.dataset.markup !== markup) {
        el.innerHTML = markup;
        el.dataset.markup = markup;
      }
      el.classList.toggle("seat-me", Boolean(player?.isHuman));
      el.classList.toggle("seat-winner", Boolean(game.revealGoal && game.winnerIdxs?.includes(idx)));
      const involved = newTrade && (newTrade.buyerIdx === idx || newTrade.sellerIdx === idx);
      el.classList.toggle("seat-flash", Boolean(involved) || (el.classList.contains("seat-flash") && game.tick <= flashUntilTick));
      el.setAttribute("aria-label", player ? `${player.isHuman ? "You" : player.name}` : "Empty seat");
    });
  }

  function bookMarkup(seat) {
    const interactive = game.humanSeated && seat >= 0;
    return SUITS.map((suit, idx) => {
      const bid = game.bestBid(idx, -1);
      const ask = game.bestAsk(idx, -1);
      const owner = (who) => (who === null ? "" : who === seat ? "You" : game.players[who].name);
      const bidText = Number.isFinite(bid.price) ? `${money(bid.price)} <small>${owner(bid.buyer)}</small>` : "—";
      const askText = Number.isFinite(ask.price) ? `${money(ask.price)} <small>${owner(ask.seller)}</small>` : "—";
      const last = game.lastTradePrice[idx] && game.tradeTape.some((trade) => trade.suit === idx)
        ? `Last ${money(game.lastTradePrice[idx])} ${game.lastTradeSignedVolume[idx] > 0 ? "↑" : game.lastTradeSignedVolume[idx] < 0 ? "↓" : ""}`
        : "No trades";
      const goal = game.revealGoal && game.goalSuitIdx === idx;
      const selected = interactive && idx === selectedSuitIdx;
      const flash = game.tradeTape[0]?.suit === idx && game.tick <= flashUntilTick;
      const classes = `book-tile${selected ? " selected" : ""}${goal ? " goal" : ""}${flash ? " flash" : ""}`;
      const label = `${suit.name}: bid ${Number.isFinite(bid.price) ? money(bid.price) : "none"}, ask ${Number.isFinite(ask.price) ? money(ask.price) : "none"}`;
      const body = `
        <span class="book-suit">${suitMark(idx)} ${suit.name}${goal ? ' <span class="goal-tag">Goal</span>' : ""}</span>
        <span class="book-row"><span>Bid</span><strong>${bidText}</strong></span>
        <span class="book-row"><span>Ask</span><strong>${askText}</strong></span>
        <span class="book-last">${last}</span>`;
      return interactive
        ? `<button type="button" class="${classes}" data-table-suit="${idx}" aria-pressed="${selected}" aria-label="${label}">${body}</button>`
        : `<div class="${classes}" role="group" aria-label="${label}">${body}</div>`;
    }).join("");
  }

  function handMarkup(seat) {
    if (seat < 0) return "";
    const player = game.players[seat];
    const read = typeof estimateRead === "function"
      ? estimateRead(player.initialInventory, player.inventory, game.roundLog, seat) : null;
    return SUITS.map((suit, idx) => {
      const selected = idx === selectedSuitIdx;
      const goal = game.revealGoal && game.goalSuitIdx === idx;
      const odds = read && !game.revealGoal ? `<small>${Math.round(100 * read[idx].tapeOdds)}% goal</small>` : goal ? "<small>Goal</small>" : "<small>&nbsp;</small>";
      return `<button type="button" class="hand-card${selected ? " selected" : ""}${goal ? " goal" : ""}" data-table-suit="${idx}" aria-pressed="${selected}" aria-label="${suit.name}: you hold ${player.inventory[idx]}">
        <span class="hand-suit">${suitMark(idx)}</span><span class="hand-count">${player.inventory[idx]}</span>${odds}</button>`;
    }).join("");
  }

  function hiddenButton(kind, suit) {
    return document.querySelector(`#marketGrid [data-human-action="${kind}"][data-suit="${suit}"]`);
  }

  function renderActions(seat) {
    actionsEl.hidden = seat < 0 || !game.running;
    if (actionsEl.hidden) return;
    const suit = selectedSuitIdx;
    byId("tableActionSuit").innerHTML = `${suitMark(suit)} ${SUITS[suit].name}`;
    const ask = game.bestAsk(suit, seat);
    const bid = game.bestBid(suit, seat);
    for (const kind of ["buy", "sell", "quote_bid", "quote_ask", "cancel"]) {
      const button = actionsEl.querySelector(`[data-table-action="${kind}"]`);
      const source = hiddenButton(kind, suit);
      button.disabled = !source || source.disabled;
      button.title = source?.title || "";
    }
    actionsEl.querySelector('[data-table-action="buy"]').textContent = ask.seller !== null ? `Buy at ${money(ask.price)}` : "Buy";
    actionsEl.querySelector('[data-table-action="sell"]').textContent = bid.buyer !== null ? `Sell at ${money(bid.price)}` : "Sell";
    const draft = String(game.humanPriceDrafts[suit]);
    if (document.activeElement !== priceInput && priceInput.value !== draft) priceInput.value = draft;
    byId("tableActionHelp").textContent = game.lastActionMessage?.replace(/\bYou's\b/g, "Your")
      || `You hold ${game.players[seat].inventory[suit]} ${SUITS[suit].name}. Quotes must be backed by cash or a card.`;
  }

  function renderCenter(seat) {
    let markup;
    if (game.running) {
      markup = "";
    } else if (game.revealGoal) {
      const me = seat >= 0 ? game.players[seat] : null;
      markup = `<p class="center-title">Goal: ${suitMark(game.goalSuitIdx)} ${SUITS[game.goalSuitIdx].name}</p>
        <p>Majority: ${game.winnerLabel}${me ? ` · You ${signed(me.cash - game.startingCash)}` : ""}</p>
        <div class="center-actions">
          ${me && !byId("roundCoach")?.hidden ? '<button type="button" data-table-center="review">Review your round</button>' : ""}
          <button type="button" data-table-center="again" class="reset-btn">Play again</button>
        </div>`;
    } else {
      const play = isPlayMode();
      markup = `<p class="center-title">${play ? "Take your seat" : "Watch the bots"}</p>
        <div class="center-actions"><button type="button" data-table-center="deal">${play ? "Deal me in" : "Start the round"}</button></div>`;
    }
    if (centerEl.dataset.markup !== markup) {
      centerEl.innerHTML = markup;
      centerEl.dataset.markup = markup;
    }
    centerEl.hidden = markup === "";
  }

  function feedLine(trade, seat) {
    const name = (idx) => (idx === -1 ? "Market" : idx === seat ? "You" : game.players[idx].name);
    const mine = trade.buyerIdx === seat || trade.sellerIdx === seat;
    const time = formatTime(Math.max(0, trade.tick * game.tickMs));
    return `<li class="${mine ? "mine" : ""}"><span class="feed-time">${time}</span>
      ${name(trade.buyerIdx)} bought ${suitMark(trade.suit)} ${money(trade.price)} from ${name(trade.sellerIdx)}</li>`;
  }

  function renderStatus() {
    statusEls.timer.textContent = formatTime(game.timeRemainingMs());
    statusEls.pot.textContent = `Pot ${money(game.antePot)}`;
    statusEls.goal.innerHTML = game.revealGoal
      ? `Goal ${suitMark(game.goalSuitIdx)} ${SUITS[game.goalSuitIdx].name}` : "Goal hidden";
    statusEls.majority.textContent = game.revealGoal ? `Majority: ${game.winnerLabel}` : (game.paused ? "Paused" : game.running ? "Trading" : "Ready");
  }

  function render() {
    const seat = humanPlayerIndex();
    const newest = game.tradeTape[0];
    const newTrade = newest && newest.id !== lastTradeId ? newest : null;
    if (newTrade) {
      lastTradeId = newTrade.id;
      flashUntilTick = game.tick + 3;
    }
    if (!game.tradeTape.length) lastTradeId = -1;
    tableEl.classList.toggle("is-play", seat >= 0);
    tableEl.classList.toggle("is-settled", Boolean(game.revealGoal));
    renderStatus();
    renderSeats(newTrade);
    const focusedSuit = document.activeElement?.dataset?.tableSuit;
    const focusedIn = document.activeElement?.closest?.("#tableBook") ? "book" : document.activeElement?.closest?.("#tableHand") ? "hand" : "";
    const book = bookMarkup(seat);
    if (bookEl.dataset.markup !== book) {
      bookEl.innerHTML = book;
      bookEl.dataset.markup = book;
    }
    const hand = handMarkup(seat);
    if (handEl.dataset.markup !== hand) {
      handEl.innerHTML = hand;
      handEl.dataset.markup = hand;
    }
    handEl.hidden = seat < 0;
    if (focusedSuit !== undefined && focusedIn) {
      const container = focusedIn === "book" ? bookEl : handEl;
      container.querySelector(`[data-table-suit="${focusedSuit}"]`)?.focus();
    }
    renderCenter(seat);
    renderActions(seat);
    const feed = game.tradeTape.slice(0, 30).map((trade) => feedLine(trade, seat)).join("")
      || '<li class="feed-empty">Trades appear here.</li>';
    if (feedEl.dataset.markup !== feed) {
      feedEl.innerHTML = feed;
      feedEl.dataset.markup = feed;
    }
  }

  function selectSuit(event) {
    const target = event.target.closest?.("[data-table-suit]");
    if (!target || humanPlayerIndex() < 0) return;
    selectedSuitIdx = Number(target.dataset.tableSuit);
    render();
  }
  bookEl.addEventListener("click", selectSuit);
  handEl.addEventListener("click", selectSuit);

  actionsEl.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-table-action], [data-table-step]");
    if (!button) return;
    if (button.dataset.tableStep) {
      const next = Number(game.humanPriceDrafts[selectedSuitIdx]) + Number(button.dataset.tableStep);
      game.humanPriceDrafts[selectedSuitIdx] = Math.min(PRICE_CAP, Math.max(PRICE_FLOOR, next));
      render();
      return;
    }
    if (button.dataset.tableAction === "quote_bid" || button.dataset.tableAction === "quote_ask") {
      // performHumanAction reads the price from the classic board's input.
      const source = document.querySelector(`#marketGrid .human-price[data-suit="${selectedSuitIdx}"]`);
      if (source) source.value = String(game.humanPriceDrafts[selectedSuitIdx]);
    }
    performHumanAction(button.dataset.tableAction, selectedSuitIdx);
  });

  priceInput.addEventListener("change", () => {
    const value = Math.round(Number(priceInput.value));
    if (Number.isFinite(value)) {
      game.humanPriceDrafts[selectedSuitIdx] = Math.min(PRICE_CAP, Math.max(PRICE_FLOOR, value));
    }
    priceInput.value = String(game.humanPriceDrafts[selectedSuitIdx]);
    render();
  });

  centerEl.addEventListener("click", (event) => {
    const action = event.target.closest?.("[data-table-center]")?.dataset.tableCenter;
    if (action === "deal" || action === "again") {
      byId("playBtn").click();
      if (humanPlayerIndex() >= 0) handEl.querySelector(`[data-table-suit="${selectedSuitIdx}"]`)?.focus();
    } else if (action === "review") {
      byId("roundCoach")?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    }
  });

  globalThis.figgieTable = { render };
  render();
})();
