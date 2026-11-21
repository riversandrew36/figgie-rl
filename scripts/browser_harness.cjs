const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const arena = path.resolve(__dirname, '../figgie_rl/arena');
function loadBrowser(policies = []) {
  const elements = new Map();
  function element(id) {
    if (!elements.has(id)) elements.set(id, { addEventListener() {}, value: '' });
    return elements.get(id);
  }
  const context = vm.createContext({
    URL, window: { location: { href: 'https://example.test/' } },
    document: { getElementById: element },
  });
  for (const file of ['figgie_lab_policy.js', 'figgie_arena.js', ...policies]) {
    vm.runInContext(fs.readFileSync(path.join(arena, file), 'utf8'), context);
  }
  return context;
}

module.exports = { arena, loadBrowser };
