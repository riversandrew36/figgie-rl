(() => {
  const data = JSON.parse(document.getElementById("rlShowcaseData").textContent);
  const labels = ["Goal + odds", "Odds only", "No aids"];
  const signed = (n) => (n >= 0 ? "+" : "−") + Math.abs(n).toFixed(2);
  const svg = (label, body, height) =>
    `<svg class="research-chart" viewBox="0 0 400 ${height}" role="img" aria-label="${label}">${body}</svg>`;
  const table = (caption, columns, rows) => `<table class="sr-only"><caption>${caption}</caption>
    <thead><tr>${columns.map((column) => `<th scope="col">${column}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const text = (x, y, value, anchor = "start") =>
    `<text x="${x}" y="${y}" text-anchor="${anchor}">${value}</text>`;
  const axis = (x1, y1, x2, y2, cls = "chart-grid") =>
    `<line class="${cls}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`;
  const [goal, odds, plain] = data.steps;
  const delta = plain.mean - data.baselines.Hold;
  document.getElementById("rlSummary").innerHTML = `
    <strong>Show the goal.</strong> PPO finished at ${signed(goal.mean)} chips per round on average.
    <strong>Hide the goal.</strong> With hand odds alone, profit fell to ${signed(odds.mean)}, close to Hold (${signed(data.baselines.Hold)}).
    Inference from cards and public trades is the hard part.
    <strong>Remove both aids.</strong> The best no-aid stage averaged ${signed(plain.mean)}, about ${Math.round(delta)} chips above Hold and below Bayesian, Hunter, and Bluffer.`;

  const y = (value) => 216 - (value + 10) * 3.2;
  const x = (index) => 78 + index * 86;
  const reference = Object.entries(data.baselines).sort((a, b) => b[1] - a[1]);
  let last = 150;
  const lines = reference.map(([name, profit]) => {
    const row = y(profit);
    const label = Math.max(row, last + 14);
    last = label;
    return axis(36, row, 288, row, "chart-reference") +
      axis(288, row, 298, label - 4, "chart-reference") + text(300, label, `${name} ${signed(profit)}`);
  }).join("");
  const groups = data.steps.map((step, index) =>
    step.final.map((value, seed) => `<circle class="chart-seed seed-${seed}" cx="${x(index) - 12 + 12 * seed}" cy="${y(value)}" r="4"/>`).join("") +
    axis(x(index) - 23, y(step.mean), x(index) + 23, y(step.mean), "chart-mean") +
    text(x(index), 249, labels[index], "middle")).join("");
  const ladderLabel = "Final profit is high when PPO sees the goal and close to Hold when the goal is hidden.";
  document.getElementById("rlLadder").innerHTML =
    "<h3>Final profit by training stage</h3><p class='small'>Chips per round · dots show training seeds · gold bars show means</p>" +
    svg(ladderLabel, [-10, 10, 30, 50].map((tick) =>
      axis(36, y(tick), 288, y(tick)) + text(28, y(tick) + 4, tick, "end")).join("") + lines + groups, 262) +
    table("Final profit by stage and baseline", ["Stage or baseline", "Seed", "Chips per round"],
      data.steps.flatMap((step, index) => step.series.map((line, seed) => [labels[index], line.seed, signed(step.final[seed])])
        .concat([[labels[index], "Mean", signed(step.mean)]]))
        .concat(reference.map(([name, profit]) => [name, "Baseline", signed(profit)])));

  document.getElementById("rlCurves").innerHTML = data.steps.map((step, index) => {
    const values = step.series.flatMap((line) => line.points.map((point) => point[1]));
    const min = 10 * Math.floor(Math.min(0, ...values) / 10);
    const max = 10 * Math.ceil(Math.max(0, ...values) / 10);
    const end = Math.max(...step.series.flatMap((line) => line.points.map((point) => point[0])));
    const cy = (value) => 112 - 90 * (value - min) / (max - min);
    const cx = (tick) => 40 + 340 * tick / end;
    const takeaway = [
      "All three seeds improve strongly with the goal shown.",
      "The odds-only seeds finish with negative profit.",
      "The no-aid seeds improve modestly and finish below zero.",
    ][index];
    const artwork = [min, 0, max].filter((value, i, all) => all.indexOf(value) === i)
      .map((value) => axis(40, cy(value), 380, cy(value)) + text(34, cy(value) + 4, value, "end")).join("") +
      step.series.map((line, seed) => `<polyline class="chart-curve seed-${seed}" points="${line.points.map(([tick, profit]) => `${cx(tick)},${cy(profit)}`).join(" ")}"/>`).join("") +
      text(40, 131, "0") + text(380, 131, end.toLocaleString("en-US"), "end") +
      text(210, 147, "Training steps", "middle");
    return `<article><h4>${labels[index]}</h4>${svg(takeaway, artwork, 154)}
      <p class="small">${step.series.map((line, seed) => `<span class="seed-key seed-${seed}">Seed ${line.seed}</span>`).join(" · ")}</p>
      ${table(`${labels[index]} learning curve`, ["Seed", "Training steps", "Profit"],
        step.series.flatMap((line) => line.points.map(([tick, profit]) => [line.seed, tick, signed(profit)])))}</article>`;
  }).join("");
  document.getElementById("rlProvenance").textContent =
    `Study ${data.study} · development seeds ${data.evaluation_seeds.join("–")}. These results are from Python and are not a held-out final test.`;
  const browserResults = JSON.parse(document.getElementById("labBenchmarkData").textContent);
  if (browserResults.length) {
    document.getElementById("labBenchmark").innerHTML =
      '<h3>Browser Lab results</h3><p>Each bot took seat one against Hunter, Banker, and Detective ' +
      'on seeds 1–200. The intervals summarize mean profit over these deals. ' +
      'The browser uses its own deals and ports of the Python scripted bots.</p>' +
      '<div class="table-scroll" tabindex="0" role="region" aria-label="Scrollable browser Lab benchmark">' +
      '<table><caption>Chips per round, with 95% intervals</caption>' +
      '<thead><tr><th scope="col">Seat</th><th scope="col">Mean</th><th scope="col">95% interval</th></tr></thead><tbody>' +
      browserResults.map(({ name, mean, low, high }) =>
        `<tr><th scope="row">${name}</th><td>${mean}</td><td>[${low}, ${high}]</td></tr>`).join("") +
      "</tbody></table></div>";
  }
})();
