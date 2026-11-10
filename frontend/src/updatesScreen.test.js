import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  NO_LIKES_COPY,
  NO_NEWS_COPY,
  digestSectionFrom,
} from "./alertView.js";

const require = createRequire(import.meta.url);
const esbuild = require("esbuild");

const HEADER = "For you, Mon, Nov 9";
const QUIET =
  "Quiet one: no price moves of 2% or more and no new headlines for your liked stocks in the last day.";
const RBLX_LINE = "RBLX is up 6.0% (as of Nov 9), at US$40.00.";
const NVDA_LINE = "NVIDIA is up 3.0% (as of Nov 9), at US$123.45.";
const AMD_LINE = "AMD is up 2.5% (as of Nov 9), at US$50.00.";
const ALERT_LINE = "FIXTURE: RBLX is up 6.0% (as of Nov 9).";

function section(items, emptyLine) {
  return digestSectionFrom(
    {
      digest: {
        date: "2026-11-09",
        header: HEADER,
        items,
        empty_line: emptyLine,
      },
    },
    true
  );
}

const phoneStyles = {
  sectionLabel: {},
  row: {},
  alertCard: {},
  alertLabel: {},
  unseen: {},
  link: {},
  helper: {},
  card: {},
  company: {},
};

function visibleText(html) {
  return html
    .replace(/<[^>]+>/g, "\n")
    .split("\n")
    .map((line) => line
      .replace(/&#x27;/g, "'")
      .replace(/&quot;/g, '"')
      .replace(/&amp;/g, "&")
      .trim())
    .filter(Boolean);
}

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

async function loadFeed(which) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "fund-feed-"));
  const outfile = path.join(dir, "feed.mjs");
  const alias = {};
  let entry = path.join(repoRoot, "frontend/src/UpdatesFeed.jsx");
  if (which === "phone") {
    const shim = path.join(dir, "react-native.mjs");
    fs.writeFileSync(
      shim,
      `import { createElement } from "react";
export const View = (props) => createElement("div", props, props.children);
export const Text = (props) => createElement("span", props, props.children);
export const Pressable = (props) => createElement("button", props, props.children);
export const Linking = { openURL: async () => {} };
export const StyleSheet = { create: (styles) => styles };
`
    );
    entry = path.join(repoRoot, "mobile/UpdatesFeed.js");
    alias["react-native"] = shim;
  }
  await esbuild.build({
    absWorkingDir: repoRoot,
    entryPoints: [entry],
    bundle: true,
    format: "esm",
    platform: "node",
    jsx: "automatic",
    loader: { ".js": "jsx" },
    nodePaths: [path.join(repoRoot, "frontend/node_modules")],
    outfile,
    alias,
  });
  const loaded = await import(pathToFileURL(outfile).href);
  const { createElement } = await import("react");
  const { renderToStaticMarkup } = await import("react-dom/server");
  return function render(props) {
    const feedProps = which === "phone"
      ? { ...props, styles: phoneStyles, onLinkError: () => {} }
      : props;
    return visibleText(renderToStaticMarkup(createElement(loaded.default, feedProps)));
  };
}

function assertQuiet(lines) {
  assert.deepEqual(lines, [HEADER, QUIET]);
  assert.equal(lines.filter((line) => line === QUIET).length, 1);
  assert.equal(lines.includes(NO_NEWS_COPY), false);
  assert.equal(lines.includes("Daily updates"), false);
  assert.equal(lines.includes("Alerts"), false);
}

function assertNoLikes(lines) {
  assert.deepEqual(lines, [NO_LIKES_COPY]);
  assert.equal(lines.filter((line) => line === NO_LIKES_COPY).length, 1);
  assert.equal(lines.includes(HEADER), false);
  assert.equal(lines.includes("Quiet one:"), false);
  assert.equal(lines.includes("Daily updates"), false);
}

test("website and iPhone Updates feeds render the same quiet, empty, and mixed states", async () => {
  const web = await loadFeed("web");
  const phone = await loadFeed("phone");
  const quietDigest = section([], QUIET);
  const populated = section(
    [
      { ticker: "NVDA", short_name: "NVIDIA", line: NVDA_LINE },
      { ticker: "AMD", short_name: "AMD", line: AMD_LINE },
    ],
    null
  );
  const cases = [
    {
      name: "quiet likes",
      props: { updates: [], alerts: [], hasLikes: true, digest: quietDigest, helpers: {} },
      check: assertQuiet,
    },
    {
      name: "no likes",
      props: {
        updates: [],
        alerts: [],
        hasLikes: false,
        digest: { header: HEADER, lines: [], emptyLine: QUIET },
        helpers: {},
      },
      check: assertNoLikes,
    },
    {
      name: "missing digest",
      props: { updates: [], alerts: [], hasLikes: true, digest: null, helpers: {} },
      check(lines) {
        assert.deepEqual(lines, [NO_NEWS_COPY]);
        assert.equal(lines.includes("Daily updates"), false);
        assert.equal(lines.includes(HEADER), false);
      },
    },
    {
      name: "null digest field",
      props: { updates: [], alerts: [], hasLikes: true, digest: null, helpers: {} },
      check(lines) {
        assert.deepEqual(lines, [NO_NEWS_COPY]);
      },
    },
    {
      name: "populated digest",
      props: {
        updates: [
          { ticker: "AMD", lines: [AMD_LINE], news_url: null },
          { ticker: "NVDA", lines: [NVDA_LINE], news_url: null },
        ],
        alerts: [],
        hasLikes: true,
        digest: populated,
        helpers: {},
      },
      check(lines) {
        assert.deepEqual(lines.slice(0, 3), [HEADER, NVDA_LINE, AMD_LINE]);
        assert.equal(lines.includes("Daily updates"), true);
        assert.equal(lines.includes(NO_NEWS_COPY), false);
        assert.ok(lines.indexOf("Daily updates") > lines.indexOf(AMD_LINE));
      },
    },
    {
      name: "alert only",
      props: {
        updates: [],
        alerts: [{ id: 1, ticker: "RBLX", kind: "price", line: ALERT_LINE, seen: false }],
        hasLikes: true,
        digest: quietDigest,
        helpers: { price: true, earnings: false },
      },
      check(lines) {
        assert.equal(lines.includes("Alerts"), true);
        assert.equal(lines.includes(ALERT_LINE), true);
        assert.equal(lines.includes(QUIET), true);
        assert.equal(lines.includes("Daily updates"), false);
        assert.equal(lines.includes(NO_NEWS_COPY), false);
      },
    },
    {
      name: "daily only",
      props: {
        updates: [{ ticker: "RBLX", lines: [RBLX_LINE], news_url: null }],
        alerts: [],
        hasLikes: true,
        digest: quietDigest,
        helpers: {},
      },
      check(lines) {
        assert.equal(lines.includes(QUIET), true);
        assert.equal(lines.includes("Daily updates"), true);
        assert.equal(lines.includes(RBLX_LINE), true);
        assert.equal(lines.includes("Alerts"), false);
        assert.equal(lines.includes(NO_NEWS_COPY), false);
      },
    },
    {
      name: "mixed alert and daily",
      props: {
        updates: [{ ticker: "RBLX", lines: [RBLX_LINE], news_url: "https://example.com/rblx-fixture" }],
        alerts: [{ id: 2, ticker: "RBLX", kind: "news", line: ALERT_LINE, seen: true, url: "https://example.com/rblx-fixture" }],
        hasLikes: true,
        digest: section([{ ticker: "RBLX", short_name: "Roblox", line: RBLX_LINE }], null),
        helpers: {},
      },
      check(lines) {
        assert.equal(lines.includes(HEADER), true);
        assert.equal(lines.includes(RBLX_LINE), true);
        assert.equal(lines.includes("Alerts"), true);
        assert.equal(lines.includes(ALERT_LINE), true);
        assert.equal(lines.includes("Daily updates"), true);
        assert.ok(lines.indexOf("Alerts") < lines.indexOf("Daily updates"));
        assert.equal(lines.includes(NO_NEWS_COPY), false);
        assert.equal(lines.includes(QUIET), false);
      },
    },
  ];

  for (const render of [web, phone]) {
    let populated = null;
    for (const item of cases) {
      const lines = render(item.props);
      item.check(lines);
      if (item.name === "populated digest") populated = lines;
    }
    const afterUnlike = render({
      updates: [{ ticker: "NVDA", lines: [NVDA_LINE], news_url: null }],
      alerts: [],
      hasLikes: true,
      digest: section([{ ticker: "NVDA", short_name: "NVIDIA", line: NVDA_LINE }], null),
      helpers: {},
    });
    assert.equal(populated.includes(AMD_LINE), true);
    assert.equal(afterUnlike.includes(AMD_LINE), false);
    assert.equal(afterUnlike.includes(NVDA_LINE), true);
    assert.equal(afterUnlike.filter((line) => line === "Daily updates").length, 1);
  }
});
