import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const esbuild = require("esbuild");
const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

function visibleText(html) {
  return html
    .replace(/<[^>]+>/g, "\n")
    .split("\n")
    .map((line) => line.replace(/&#x27;/g, "'").replace(/&amp;/g, "&").trim())
    .filter(Boolean);
}

async function loadCard() {
  const outfile = path.join(repoRoot, "frontend/src/.company-card-render.mjs");
  await esbuild.build({
    absWorkingDir: repoRoot,
    entryPoints: [path.join(repoRoot, "frontend/src/App.jsx")],
    bundle: true,
    format: "esm",
    platform: "node",
    jsx: "automatic",
    loader: { ".js": "jsx" },
    external: ["react", "react-dom", "react/jsx-runtime", "react/jsx-dev-runtime"],
    nodePaths: [path.join(repoRoot, "frontend/node_modules")],
    outfile,
  });
  const loaded = await import(pathToFileURL(outfile).href);
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  return (props) => {
    const html = renderToStaticMarkup(createElement(loaded.CompanyCard, props));
    return visibleText(html);
  };
}

function baseCard(overrides) {
  return {
    ticker: "NVDA",
    short_name: "NVIDIA",
    company_name: "NVIDIA Corporation",
    why_line: "Games use these chips.",
    short_description: "Designs graphics chips.",
    current_price: 210.5,
    price_change_percent: 1.25,
    price_available: true,
    news_available: true,
    news_status: "ready",
    latest_news_headline: "NVIDIA ships a new chip",
    latest_news_summary: "The chip is for games.",
    news_date_label: "Nov 5",
    quarterly_summary: "Revenue rose.",
    quarter_label: "Quarter ended Oct 26",
    ...overrides,
  };
}

test("the swipe card renders with news and without news", async () => {
  const outfile = path.join(repoRoot, "frontend/src/.company-card-render.mjs");
  let render;
  try {
  render = await loadCard();
  const withNews = render({ card: baseCard(), showNews: true });
  assert.equal(withNews.includes("NVIDIA (NVDA)"), true);
  assert.equal(withNews.includes("NVIDIA ships a new chip"), true);
  assert.equal(withNews.includes("The chip is for games."), true);
  assert.equal(withNews.includes("Nov 5"), true);
  assert.equal(withNews.includes("Price: US$210.50, up 1.3%"), true);

  const quiet = render({
    card: baseCard({
      ticker: "AMD",
      short_name: "AMD",
      company_name: "Advanced Micro Devices, Inc.",
      news_status: "none",
      news_available: false,
      latest_news_headline: null,
      latest_news_summary: null,
      news_date_label: null,
      news_message: "No recent news about this company yet.",
      current_price: null,
      price_change_percent: null,
      price_available: false,
    }),
    showNews: true,
  });
  assert.equal(quiet.includes("No recent news about this company yet."), true);
  assert.equal(quiet.includes("AMD"), true);
  assert.equal(quiet.includes("AMD (AMD)"), false);
  assert.equal(quiet.includes("Price:"), false);
  assert.equal(quiet.includes("Price: not available"), false);

  const missing = render({
    card: baseCard({
      news_available: false,
      news_status: "unavailable",
      latest_news_headline: null,
      latest_news_summary: null,
      news_date_label: null,
    }),
    showNews: true,
  });
  assert.equal(missing.join(" ").includes("Latest news: not available"), true);
  assert.equal(missing.includes("NVIDIA ships a new chip"), false);
  } finally {
    fs.rmSync(outfile, { force: true });
  }
});
