/**
 * Copies third-party browser assets out of node_modules into static/vendor/ so
 * Django serves them itself. Keeps node_modules out of the deploy and removes
 * the runtime dependency on any external CDN.
 *
 * Run via `npm run build` (or `npm run build:vendor`) after `npm install`.
 */
const fs = require("fs");
const path = require("path");

const ASSETS = [
  ["highcharts/highcharts.js", "highcharts/highcharts.js"],
  ["highcharts/modules/accessibility.js", "highcharts/accessibility.js"],
  ["sortablejs/Sortable.min.js", "sortablejs/Sortable.min.js"],
];

const root = path.join(__dirname, "..");
let copied = 0;

for (const [from, to] of ASSETS) {
  const src = path.join(root, "node_modules", from);
  const dest = path.join(root, "static", "vendor", to);
  if (!fs.existsSync(src)) {
    console.error(`missing: ${from} — run npm install`);
    process.exitCode = 1;
    continue;
  }
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
  console.log(`vendor: ${to} (${fs.statSync(dest).size.toLocaleString()} bytes)`);
  copied += 1;
}

console.log(`${copied}/${ASSETS.length} vendor asset(s) copied.`);
