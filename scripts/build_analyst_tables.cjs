// Sample goal-card allocations conditional on your holding k of the D cards.
// From your own hand, the remaining cards are exchangeable across three
// ten-card hands. This assumes no extra opponent-hand information.
const fs = require('node:fs');
const path = require('node:path');
const arena = path.join(__dirname, '../figgie_rl/arena/figgie_arena.js');

function majorityTable(samples = 30000) {
  let state = 517893;
  const next = () => ((state = (Math.imul(state, 1664525) + 1013904223) >>> 0) / 2 ** 32);
  return [8,10].map(total => Array.from({length:total+1}, (_, held) => {
    const counts = [0,0,0,0];
    const slots = Array.from({length:30}, (_, slot) => Math.floor(slot/10));
    for (let sample = 0; sample < samples; sample++) {
      const other = [0,0,0];
      for (let slot = 0; slot < total-held; slot++) {
        const pick = slot + Math.floor(next() * (30-slot));
        [slots[slot], slots[pick]] = [slots[pick], slots[slot]];
        other[slots[slot]]++;
      }
      if (other.every(value => value <= held)) counts[other.filter(value => value === held).length]++;
    }
    return counts.map(count => Number((count/samples).toFixed(6)));
  }));
}
module.exports = { majorityTable };
if (require.main === module) {
  const source = fs.readFileSync(arena, 'utf8');
  const marker = /const ANALYST_MAJORITY = \[.*\];/;
  if (!marker.test(source)) throw Error('Missing Analyst table marker');
  fs.writeFileSync(arena, source.replace(marker, 'const ANALYST_MAJORITY = '+JSON.stringify(majorityTable())+';'));
}
