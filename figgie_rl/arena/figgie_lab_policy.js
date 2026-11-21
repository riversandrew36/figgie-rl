// The learner chooses from the observation before quote ageing, as in Python.
// Its action is then applied at its seat's position in the current lab step.
function labObservation(round, seat, hiddenBlocks) {
  const player = round.players[seat];
  const bids = SUITS.map((_, suit) => round.bestBid(suit, seat));
  const asks = SUITS.map((_, suit) => round.bestAsk(suit, seat));
  const scalePrices = (values) => values.map((value) => Number.isFinite(value) ? Math.fround(value) / 20 : 0);
  const belief = [0, 0, 0, 0];
  const aggression = round.players.map(() => [0, 0, 0, 0]);
  for (const trade of round.roundLog) {
    const buy = trade.aggressorSide === "buy";
    for (let suit = 0; suit < 4; suit += 1) belief[suit] *= 0.85;
    belief[trade.suit] += buy ? 1 : -1;
    aggression[buy ? trade.buyerIdx : trade.sellerIdx][trade.suit] += buy ? 1 : -1;
  }
  const clipped = belief.map((value) => Math.max(-3, Math.min(3, value)));
  const min = Math.min(...clipped);
  const range = Math.max(...clipped) - min + 1e-6;
  const clockwise = [1, 2, 3].map((offset) => (seat + offset) % 4);
  const fraction = round.tick / LAB_STEPS;
  return Float32Array.from([
    ...player.inventory.map((count) => count / 20), player.cash / 200,
    ...scalePrices(bids.map((quote) => quote.price)), ...scalePrices(asks.map((quote) => quote.price)),
    ...scalePrices(player.bidQuotes), ...scalePrices(player.askQuotes), ...scalePrices(round.lastTradePrice),
    ...round.lastTradeSignedVolume, 1 - fraction, fraction,
    ...clipped.map((value) => (value - min) / range),
    ...(hiddenBlocks.includes("goal_suit_posterior") ? [0, 0, 0, 0] : goalSuitPosterior(player.initialInventory)),
    ...bids.map((quote) => Number(quote.buyer !== null)), ...asks.map((quote) => Number(quote.seller !== null)),
    ...clockwise.flatMap((other) => round.players[other].inventory.map((count, suit) =>
      (count - round.players[other].initialInventory[suit]) / 10)),
    ...clockwise.flatMap((other) => aggression[other].map((flow) => flow / 5)),
    ...SUITS.map((_, suit) => Number(!hiddenBlocks.includes("goal_oracle") && suit === round.goalSuitIdx)),
  ]);
}

function labActionMask(round, seat, actions) {
  const player = round.players[seat];
  return actions.map(({ kind, suit, price }) => {
    switch (kind) {
      case "quote_bid": return player.cash >= price;
      case "quote_ask": return player.inventory[suit] > 0;
      case "buy": {
        const ask = round.bestAsk(suit, seat);
        return ask.seller !== null && player.cash >= ask.price;
      }
      case "sell": return player.inventory[suit] > 0 && round.bestBid(suit, seat).buyer !== null;
      default: return true;
    }
  });
}

const labCompiledActors = new WeakMap();
function labActor(layers, observation) {
  let compiled = labCompiledActors.get(layers);
  if (!compiled) {
    compiled = layers.map((layer) => layer.type === "linear" ? {
      type: layer.type,
      weights: layer.weights.map((row) => Float32Array.from(row)),
      bias: Float32Array.from(layer.bias),
    } : layer);
    labCompiledActors.set(layers, compiled);
  }
  let values = observation;
  for (const layer of compiled) {
    if (layer.type === "tanh") values = Float32Array.from(values, Math.tanh);
    else if (layer.type === "relu") values = Float32Array.from(values, (value) => Math.max(0, value));
    else values = Float32Array.from(layer.weights, (row, i) => {
      let sum = layer.bias[i];
      for (let j = 0; j < row.length; j += 1) sum += row[j] * values[j];
      return sum;
    });
  }
  return values;
}

function labMaskedArgmax(logits, mask) {
  let best = -1;
  for (let i = 0; i < logits.length; i += 1) {
    if (mask[i] && (best === -1 || logits[i] > logits[best])) best = i;
  }
  return best;
}

function labPolicyAction(round, seat, id) {
  const actor = globalThis.figgiePolicies[id];
  const observation = labObservation(round, seat, actor.hidden_blocks);
  const mask = labActionMask(round, seat, actor.actions);
  return actor.actions[labMaskedArgmax(labActor(actor.layers, observation), mask)];
}

// Resolve relative to this script for both Pages prefixes and direct file use.
const labPolicyBase = typeof document !== "undefined" && document.currentScript?.src;
const labPolicyLoads = new Map();
function loadLabPolicy(id) {
  if (globalThis.figgiePolicies?.[id]) return Promise.resolve();
  if (labPolicyLoads.has(id)) return labPolicyLoads.get(id);
  const load = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = new URL("policies/" + id + ".js", labPolicyBase).href;
    script.onload = () => globalThis.figgiePolicies?.[id] ? resolve() : reject(Error("Missing actor"));
    script.onerror = () => reject(Error("Actor could not load"));
    document.head.append(script);
  }).catch((error) => {
    labPolicyLoads.delete(id);
    throw error;
  });
  labPolicyLoads.set(id, load);
  return load;
}
