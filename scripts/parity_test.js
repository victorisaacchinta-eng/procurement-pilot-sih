// Runs the frontend's offline engine against the backend's own results.
// Usage: python scripts/dump_backend.py > /tmp/backend.json && node scripts/parity_test.js /tmp/backend.json
const fs = require('fs');
const path = require('path');
const html = fs.readFileSync(path.join(__dirname, '..', 'frontend', 'index.html'), 'utf8');
const seed = html.match(/<script type="application\/json" id="pp-seed">([\s\S]*?)<\/script>/)[1];
const engineSrc = html.match(/\/\* ENGINE START[\s\S]*?\*\/([\s\S]*?)\/\* ENGINE END \*\//)[1];
const document = { getElementById: () => ({ textContent: seed }) };
const PPEngine = new Function('document', engineSrc + '; return PPEngine;')(document);
const expected = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
let fails = 0, n = 0;
for (const [key, want] of Object.entries(expected)) {
  n++;
  if (key.startsWith('col|')) {
    const got = PPEngine.screen(key.slice(4)).findings.map(f => [f.signal, f.severity]);
    if (JSON.stringify(got) !== JSON.stringify(want)) { fails++; console.log('MISMATCH', key, got, want); }
    continue;
  }
  const [tid, name] = key.split('|');
  const r = PPEngine.evaluate(tid, name, []);
  const got = { score: r.compliance_score, verdict: r.verdict, st: r.checks.map(c => c.status), names: r.checks.map(c => c.name) };
  if (JSON.stringify(got) !== JSON.stringify(want)) { fails++; console.log('MISMATCH', key, JSON.stringify(got), JSON.stringify(want)); }
}
console.log(`${n - fails}/${n} cases match the backend`);
process.exit(fails ? 1 : 0);
