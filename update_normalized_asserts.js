const fs = require("fs");
const path = require("path");

const FILE = path.join(__dirname, "results.models_normalized.json");

const parseExpr =
  "const data = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim());";

function js(value) {
  return { type: "javascript", value };
}

const ASSERTS = {
  0: [
    js(
      "(() => { try { const data = typeof output === 'string' ? JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()) : output; return data && typeof data === 'object' && !Array.isArray(data) && data.flagship && typeof data.flagship === 'object' && data.flagship.stats && typeof data.flagship.stats === 'object'; } catch { return false; } })()"
    ),
    js(`(() => { ${parseExpr} return data.faction === 'The Federation of Sol'; })()`),
    js(`(() => { ${parseExpr} return data.expansion === 'Base Game'; })()`),
    js(`(() => { ${parseExpr} return data.flagship.name === 'Genesis'; })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.cost === 8; })()`),
    js(`(() => { ${parseExpr} return /^5\\s*\\(x2\\)$|^5x2$/i.test(data.flagship.stats.combat); })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.move === 1; })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.capacity === 12; })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.sustainDamage === true; })()`),
    js(`(() => { ${parseExpr} return typeof data.flagship.ability === 'string' && data.flagship.ability.toLowerCase().includes('place 1 infantry'); })()`),
    js(`(() => { ${parseExpr} return typeof data.flagship.ability === 'string' && data.flagship.ability.toLowerCase().includes('status phase'); })()`),
    js(`(() => { ${parseExpr} return typeof data.flagship.ability === 'string' && data.flagship.ability.toLowerCase().includes('space area'); })()`),
  ],
  1: [
    js(
      "(() => { try { const data = typeof output === 'string' ? JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()) : output; return data && typeof data === 'object' && !Array.isArray(data) && data.flagship && typeof data.flagship === 'object' && data.flagship.stats && typeof data.flagship.stats === 'object'; } catch { return false; } })()"
    ),
    js(`(() => { ${parseExpr} return data.faction === 'The Argent Flight'; })()`),
    js(`(() => { ${parseExpr} return data.expansion === 'Prophecy of Kings'; })()`),
    js(`(() => { ${parseExpr} return data.flagship.name === 'Quetzecoatl'; })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.cost === 8; })()`),
    js(`(() => { ${parseExpr} return /^7\\s*\\(x2\\)$|^7x2$/i.test(data.flagship.stats.combat); })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.move === 1; })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.capacity === 3; })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.sustainDamage === true; })()`),
    js(`(() => { ${parseExpr} return typeof data.flagship.ability === 'string' && data.flagship.ability.toLowerCase().includes('cannot use space cannon'); })()`),
    js(`(() => { ${parseExpr} return typeof data.flagship.ability === 'string' && data.flagship.ability.toLowerCase().includes('your ships in this system'); })()`),
  ],
  2: [
    js(
      "(() => { try { const data = typeof output === 'string' ? JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()) : output; return data && typeof data === 'object' && !Array.isArray(data) && data.flagship && typeof data.flagship === 'object' && data.flagship.stats && typeof data.flagship.stats === 'object'; } catch { return false; } })()"
    ),
    js(`(() => { ${parseExpr} return data.faction === 'The Crimson Rebellion'; })()`),
    js(`(() => { ${parseExpr} return data.expansion === 'Thunders Edge'; })()`),
    js(`(() => { ${parseExpr} return data.flagship.name === 'Quietus'; })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.cost === 8; })()`),
    js(`(() => { ${parseExpr} return /^5\\s*\\(x2\\)$|^5x2$/i.test(data.flagship.stats.combat); })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.move === 1; })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.capacity === 3; })()`),
    js(`(() => { ${parseExpr} return data.flagship.stats.sustainDamage === true; })()`),
    js(`(() => { ${parseExpr} return typeof data.flagship.ability === 'string' && data.flagship.ability.toLowerCase().includes('active breach'); })()`),
    js(`(() => { ${parseExpr} return typeof data.flagship.ability === 'string' && data.flagship.ability.toLowerCase().includes('lose all their unit abilities'); })()`),
  ],
  3: [
    js(
      "(() => { try { const data = typeof output === 'string' ? JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()) : output; return data && typeof data === 'object' && !Array.isArray(data); } catch { return false; } })()"
    ),
    js(
      "(() => { const data = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return JSON.stringify(Object.keys(data).sort()) === JSON.stringify(['base_game', 'pok', 'thunders_edge']) && Array.isArray(data.base_game) && data.base_game.length === 17 && Array.isArray(data.pok) && data.pok.length === 7 && Array.isArray(data.thunders_edge) && data.thunders_edge.length === 5; })()"
    ),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thearborec'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thebaronyofletnev'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theclanofsaar'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theembersofmuaat'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theemiratesofhacan'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thefederationofsol'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theghostsofcreuss'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thel1z1xmindnet'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thementakcoalition'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thenaalucollective'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thenekrovirus'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theuniversitiesofjolnar'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thewinnu'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thexxchakingdom'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theyinbrotherhood'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theyssariltribes'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.base_game.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'sardakknorr'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.pok.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theargentflight'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.pok.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theempyrean'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.pok.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'themahactgenesorcerers'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.pok.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thenaazrokhaalliance'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.pok.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thenomad'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.pok.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thetitansoful'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.pok.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thevuilraithcabal'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.thunders_edge.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'lastbastion'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.thunders_edge.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thecrimsonrebellion'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.thunders_edge.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thedeepwroughtscholarate'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.thunders_edge.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'thefirmamenttheobsidian'); })()"),
    js("(() => { const d = JSON.parse(output.replace(/^```json\\s*|^```\\s*|\\s*```$/g, '').trim()); return d.thunders_edge.some((s) => String(s).replace(/[\\W_]/g, '').toLowerCase() === 'theralnelconsortium'); })()"),
  ],
};

function main() {
  const data = JSON.parse(fs.readFileSync(FILE, "utf8"));
  for (const entry of data.results.results) {
    entry.testCase.assert = ASSERTS[entry.testIdx];
  }
  fs.writeFileSync(FILE, `${JSON.stringify(data, null, 2)}\n`, "utf8");
  console.log(`Updated normalized asserts in ${FILE}`);
}

main();
