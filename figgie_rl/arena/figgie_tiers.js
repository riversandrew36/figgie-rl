(() => {
  const byId = (id) => document.getElementById(id);
  const data = JSON.parse(byId("tierRatingsData").textContent);
  if (!data.lineups || typeof refreshModePreview !== "function" || typeof game === "undefined") return;
  const { lineups } = data;
  // Advanced opens only when its bots beat Intermediate on held-out deals.
  // Until then the tier is shown as coming soon and never seats a player.
  // The pre-registered confirmation run decides when it exists.
  const advancedReady = Boolean((data.confirmation || data.heldOut).advancedPass);
  const titles = {
    beginner: "Beginner", intermediate: "Intermediate",
    advanced: advancedReady ? "Advanced" : "Advanced · coming soon", custom: "Custom",
  };
  const descriptions = {
    beginner: "Slower scripted bots with noisy prices and no tape reading.",
    intermediate: "The original scripted styles, with their usual strategies.",
    advanced: "Analysts value each card by how much it adds to their chance of winning the majority.",
    custom: "Choose your opponents, including the optional Lab policies.",
  };
  const ids = advancedReady ? ["beginner", "intermediate", "advanced", "custom"] : ["beginner", "intermediate", "custom"];
  const radio = (id) => byId("tier" + id[0].toUpperCase() + id.slice(1));
  const params = new URL(window.location.href).searchParams;
  const preset = byId("battlePreset");
  const matches = {
    intermediate: () => lineups.intermediate,
    // Three Advanced bots fill the Play table; Watch adds Bluffer as the fourth seat.
    advanced: () => [...lineups.advanced, lineups.intermediate[3]].slice(0, 4),
    "advanced-v-intermediate": () => [lineups.advanced[0], lineups.intermediate[0], lineups.advanced[2], lineups.intermediate[1]],
    "intermediate-v-beginner": () => [lineups.intermediate[0], lineups.beginner[0], lineups.intermediate[1], lineups.beginner[1]],
    everyone: () => [lineups.beginner[0], lineups.intermediate[0], lineups.advanced[0], lineups.intermediate[3]],
  };
  if (!advancedReady) {
    for (const key of ["advanced", "advanced-v-intermediate", "everyone"]) delete matches[key];
  }
  for (const option of [...(preset.options || [])]) {
    if (option.value !== "custom" && !matches[option.value]) option.remove();
  }
  const dailyBattle = advancedReady ? "advanced-v-intermediate" : "intermediate-v-beginner";
  function load(key, fallback) {
    try { return JSON.parse(localStorage.getItem("figgie.tiers." + key)) ?? fallback; }
    catch { return fallback; }
  }
  function save(key, value) {
    try { localStorage.setItem("figgie.tiers." + key, JSON.stringify(value)); }
    catch { /* Play remains available without storage. */ }
  }
  const stored = load("selection", "beginner");
  const requested = params.get("tier");
  // A link made while Advanced was open falls back to the closest open tier.
  const incoming = requested === "advanced" && !advancedReady ? "intermediate" : requested;
  let tier = ids.includes(incoming) ? incoming
    : params.size ? "custom" : ids.includes(stored) ? stored : "beginner";
  const past = load("progress", {});
  if (!isPlayMode() && Object.hasOwn(matches, params.get("battle"))) preset.value = params.get("battle");

  function useCustom() {
    tier = "custom";
    if (preset.value !== "custom") preset.value = "custom";
  }

  function specs(play) {
    if (!play) return matches[preset.value]?.();
    if (tier === "custom") return undefined;
    return [{name: "You", strategy: -1, isHuman: true}, ...lineups[tier].slice(0, 3)];
  }

  function showSettings() {
    const play = isPlayMode();
    byId("tierPicker").hidden = !play;
    byId("battleSettings").hidden = play;
    byId("opponentPicker").hidden = play ? tier !== "custom" : preset.value !== "custom";
    if (byId("tierDescription").textContent !== descriptions[tier]) byId("tierDescription").textContent = descriptions[tier];
    for (const id of ids) {
      radio(id).checked = id === tier;
      radio(id).disabled = game.running;
    }
    if (!advancedReady) {
      radio("advanced").checked = false;
      radio("advanced").disabled = true;
    }
    preset.disabled = game.running;
    byId("battleDaily").disabled = game.running;
    byId("battleBatch").disabled = game.running || batching || !matches[preset.value];
  }

  function badge(player) {
    if (!player || player.isHuman) return "";
    const label = player.tier ? titles[player.tier] : player.policyId ? "Trained" : "Intermediate";
    return ` <span class="tier-badge" title="${label}">${label === "Advanced (preview)" ? "Advanced*" : label}</span>`;
  }

  const profit = (number) => (number >= 0 ? "+" : "−") + Math.abs(number).toFixed(2);
  let batching = false;
  let activeTier = null;
  let activeBattle = null;
  function started() {
    activeTier = isPlayMode() && tier !== "custom" ? tier : null;
    activeBattle = !isPlayMode() && matches[preset.value] ? preset.value : null;
    byId("battleResults").hidden = true;
  }

  function renderProgress() {
    byId("tierProgress").innerHTML = Object.keys(lineups).filter((key) => past[key]?.rounds)
      .map((key) => {
        const row = past[key];
        return `<p class="small">${titles[key]} · ${row.rounds} rounds · average ${profit(row.total / row.rounds)} · best ${profit(row.best)}</p>`;
      }).join("");
  }

  function ended() {
    if (activeTier) {
      const player = game.players.find((seat) => seat.isHuman);
      const value = player.cash - game.startingCash;
      const row = past[activeTier] || {rounds:0,total:0,best:-Infinity};
      past[activeTier] = {rounds:row.rounds+1,total:row.total+value,best:Math.max(value,row.best)};
      save("progress", past);
      renderProgress();
    }
    if (activeBattle) {
      byId("battleResultRows").innerHTML = game.players.map((player) =>
        `<li>${player.name}${badge(player)} <strong>${profit(player.cash - game.startingCash)}</strong></li>`).join("");
      byId("battleResults").hidden = false;
    }
  }

  function batchRound(seed, players) {
    const round = new FiggieViewerGame();
    round.reset(60000, seed, { marketMode:"players", playerSpecs:players });
    for (; round.tick < 240; round.tick += 1) {
      round.elapsedMs = round.tick * round.tickMs;
      round.ageAndExpireQuotes();
      for (let seat = 0; seat < 4; seat += 1) round.applyAction(seat, round.pickAction(seat));
    }
    round.settleRound();
    const profits = {};
    for (const player of round.players) (profits[player.tier] ??= []).push(player.cash - round.startingCash);
    return Object.fromEntries(Object.entries(profits).map(([key, values]) =>
      [key, values.reduce((sum, n)=>sum+n,0) / values.length]));
  }

  function startBatch() {
    const players = matches[preset.value]?.();
    if (!players || batching || game.running || isPlayMode()) return;
    const base = Number(seedInput.value) || 7;
    const results = {};
    let count = 0;
    batching = true;
    byId("battleBatchResults").hidden = false;
    byId("battleBatchRows").innerHTML = "";
    byId("battleBatchStatus").textContent = "Running 20 battles…";
    showSettings();
    function chunk() {
      const round = batchRound(base + count, players);
      for (const [key, value] of Object.entries(round)) (results[key] ??= []).push(value);
      count += 1;
      if (count < 20) {
        byId("battleBatchStatus").textContent = `Completed ${count} of 20 battles`;
        setTimeout(chunk, 0);
        return;
      }
      byId("battleBatchStatus").textContent = `20 battles complete · seeds ${base}–${base+19}`;
      byId("battleBatchRows").innerHTML = Object.entries(results).map(([key, values]) => {
        const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
        const variance = values.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (values.length - 1);
        const half = 1.96 * Math.sqrt(variance / values.length);
        return `<li>${titles[key]} · mean ${profit(mean)} · 95% interval [${profit(mean-half)}, ${profit(mean+half)}]</li>`;
      }).join("");
      batching = false;
      showSettings();
    }
    setTimeout(chunk, 0);
  }

  for (const id of ids) radio(id).addEventListener("change", () => {
    if (!radio(id).checked || game.running) return;
    tier = id;
    save("selection", tier);
    refreshModePreview();
  });
  preset.addEventListener("change", () => refreshModePreview());
  byId("battleBatch").addEventListener("click", startBatch);
  byId("battleDaily").addEventListener("click", () => {
    if (isPlayMode() || game.running || typeof dailySeed !== "function" || typeof utcDay !== "function") return;
    preset.value = dailyBattle;
    seedInput.value = dailySeed(utcDay());
    durationSelect.value = "60000";
    refreshModePreview();
    playBtn.click();
  });
  byId("tierAdvancedLabel").textContent = titles.advanced;
  byId("tierResearch").innerHTML = "<h3>How bot tiers are rated</h3><p>All three tiers use scripted bots. " +
    "The rating run compares candidates on the same seeds against the same reference table. " +
    "Held-out deals decide promotion, using paired 95% intervals. PPO seats remain available in Custom Lab rounds.</p>" +
    (advancedReady ? "" : "<p>Advanced is coming soon. The full lineup did not clear the held-out bar. " +
      "The tier opens when all four beat the best Intermediate on held-out deals.</p>");
  globalThis.figgieTiers = {
    badge, specs, useCustom, showSettings, started, ended,
    forcesPlayers: (play) => play ? tier !== "custom" : Boolean(matches[preset.value]),
    tableTitle: () => isPlayMode() ? `${titles[tier]} table` : matches[preset.value] ? "Bot battle" : "Watch the bots",
    share: (url) => {
      if (game.humanSeated) url.searchParams.set("tier", game.running || game.revealGoal ? activeTier || "custom" : tier);
      else {
        url.searchParams.set("tier", "custom");
        if (matches[preset.value]) url.searchParams.set("battle", preset.value);
      }
    },
    restore: (round) => {
      const value = round.players.find((player) => player.tier)?.tier;
      tier = ids.includes(value) && round.humanSeated ? value : "custom";
    },
  };
  renderProgress();
  refreshModePreview();
})();
