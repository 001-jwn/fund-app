import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
  FILING_LINK_LABEL,
  NO_LIKES_COPY,
  NO_NEWS_COPY,
  OUTLOOK_HELPER,
  SEC_FILING_HELPER,
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
const NVDA_FILING = "NVIDIA shared its latest quarterly results in an SEC filing on Nov 5.";
const AMD_FILING = "AMD reported a major deal in an SEC filing on Nov 4. The filing has the details.";
const NVDA_URL = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/0001045810-26-000010-index.html";
const AMD_URL = "https://www.sec.gov/Archives/edgar/data/2488/000000248826000020/0000002488-26-000020-index.html";

function anchorsFrom(html) {
  const found = [];
  const re = /<a\b([^>]*)>([^<]*)<\/a>/gi;
  let match;
  while ((match = re.exec(html))) {
    const attrs = match[1];
    const href = /href="([^"]*)"/.exec(attrs);
    const target = /target="([^"]*)"/.exec(attrs);
    const rel = /rel="([^"]*)"/.exec(attrs);
    found.push({
      text: match[2].replace(/&amp;/g, "&"),
      href: href ? href[1].replace(/&amp;/g, "&") : "",
      target: target ? target[1] : "",
      rel: rel ? rel[1] : "",
    });
  }
  return found;
}

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
  function markup(props) {
    const feedProps = which === "phone"
      ? { ...props, styles: phoneStyles, onLinkError: () => {} }
      : props;
    return renderToStaticMarkup(createElement(loaded.default, feedProps));
  }
  function render(props) {
    return visibleText(markup(props));
  }
  render.markup = markup;
  return render;
}

function assertQuiet(lines) {
  assert.deepEqual(lines, [HEADER, QUIET]);
  assert.equal(lines.filter((line) => line === QUIET).length, 1);
  assert.equal(lines.includes(NO_NEWS_COPY), false);
  assert.equal(lines.includes("Daily updates"), false);
  assert.equal(lines.includes("Alerts"), false);
  assert.equal(lines.includes("SEC filings"), false);
  assert.equal(lines.includes(SEC_FILING_HELPER), false);
  assert.equal(lines.includes(OUTLOOK_HELPER), false);
  assert.equal(lines.includes(FILING_LINK_LABEL), false);
}

function assertNoLikes(lines) {
  assert.deepEqual(lines, [NO_LIKES_COPY]);
  assert.equal(lines.filter((line) => line === NO_LIKES_COPY).length, 1);
  assert.equal(lines.includes(HEADER), false);
  assert.equal(lines.includes("Quiet one:"), false);
  assert.equal(lines.includes("Daily updates"), false);
  assert.equal(lines.includes("SEC filings"), false);
  assert.equal(lines.includes(SEC_FILING_HELPER), false);
  assert.equal(lines.includes(OUTLOOK_HELPER), false);
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
      name: "filings in server order",
      props: {
        updates: [],
        alerts: [],
        hasLikes: true,
        digest: quietDigest,
        helpers: {},
        filings: [
          {
            ticker: "AMD",
            short_name: "AMD",
            accession: "0000002488-26-000020",
            date_ny: "2026-11-01",
            line: AMD_FILING,
            filing_url: AMD_URL,
          },
          {
            ticker: "NVDA",
            short_name: "NVIDIA",
            accession: "0001045810-26-000010",
            date_ny: "2026-11-09",
            line: NVDA_FILING,
            filing_url: NVDA_URL,
          },
        ],
      },
      check(lines) {
        assert.deepEqual(lines.slice(0, 2), [HEADER, QUIET]);
        assert.deepEqual(
          lines.filter((line) => (
            line === "SEC filings"
            || line === SEC_FILING_HELPER
            || line === "AMD"
            || line === "NVIDIA"
            || line === AMD_FILING
            || line === NVDA_FILING
            || line === FILING_LINK_LABEL
            || line === OUTLOOK_HELPER
          )),
          [
            "SEC filings",
            SEC_FILING_HELPER,
            "AMD",
            AMD_FILING,
            FILING_LINK_LABEL,
            "NVIDIA",
            NVDA_FILING,
            FILING_LINK_LABEL,
          ]
        );
        assert.equal(lines.filter((line) => line === SEC_FILING_HELPER).length, 1);
        assert.equal(lines.indexOf(SEC_FILING_HELPER), lines.indexOf("SEC filings") + 1);
        assert.equal(lines.includes(OUTLOOK_HELPER), false);
        assert.equal(lines.includes("Daily updates"), false);
        assert.equal(lines.includes("Alerts"), false);
        assert.equal(lines.includes(NO_NEWS_COPY), false);
        assert.equal(lines.includes("2026-11-01"), false);
        assert.equal(lines.includes("2026-11-09"), false);
        assert.ok(lines.indexOf("SEC filings") > lines.indexOf(QUIET));
      },
    },
    {
      name: "filings above daily lines",
      props: {
        updates: [{ ticker: "RBLX", lines: [RBLX_LINE], news_url: null }],
        alerts: [{ id: 4, ticker: "RBLX", kind: "price", line: ALERT_LINE, seen: false }],
        hasLikes: true,
        digest: quietDigest,
        helpers: {},
        filings: [
          {
            ticker: "NVDA",
            short_name: "NVIDIA",
            date_ny: "2026-11-05",
            line: NVDA_FILING,
            filing_url: NVDA_URL,
          },
        ],
      },
      check(lines) {
        assert.equal(lines.includes(QUIET), true);
        assert.equal(lines.includes("Alerts"), true);
        assert.equal(lines.includes("SEC filings"), true);
        assert.equal(lines.includes(NVDA_FILING), true);
        assert.equal(lines.includes("Daily updates"), true);
        assert.equal(lines.includes(RBLX_LINE), true);
        assert.ok(lines.indexOf("Alerts") < lines.indexOf("SEC filings"));
        assert.ok(lines.indexOf("SEC filings") < lines.indexOf("Daily updates"));
        assert.equal(lines.filter((line) => line === "Daily updates").length, 1);
        assert.equal(lines.filter((line) => line === "SEC filings").length, 1);
      },
    },
    {
      name: "null filings",
      props: { updates: [], alerts: [], hasLikes: true, digest: quietDigest, filings: null, helpers: {} },
      check: assertQuiet,
    },
    {
      name: "empty filings",
      props: { updates: [], alerts: [], hasLikes: true, digest: quietDigest, filings: [], helpers: {} },
      check: assertQuiet,
    },
    {
      name: "filings not a list",
      props: { updates: [], alerts: [], hasLikes: true, digest: quietDigest, filings: { line: NVDA_FILING }, helpers: {} },
      check: assertQuiet,
    },
    {
      name: "malformed filings",
      props: {
        updates: [],
        alerts: [],
        hasLikes: true,
        digest: quietDigest,
        helpers: {},
        filings: [null, { ticker: "NVDA", short_name: "NVIDIA", line: 4, filing_url: NVDA_URL }, { ticker: "AMD" }],
      },
      check: assertQuiet,
    },
    {
      name: "no likes with empty filings",
      props: {
        updates: [],
        alerts: [],
        hasLikes: false,
        digest: { header: HEADER, lines: [], emptyLine: QUIET },
        filings: [],
        helpers: {},
      },
      check: assertNoLikes,
    },
    {
      name: "filing without a link still shows the line",
      props: {
        updates: [],
        alerts: [],
        hasLikes: true,
        digest: null,
        helpers: {},
        filings: [{ ticker: "NVDA", short_name: "NVIDIA", line: NVDA_FILING, filing_url: null, date_ny: "2026-11-05" }],
      },
      check(lines) {
        assert.equal(lines.includes("SEC filings"), true);
        assert.equal(lines.includes("NVIDIA"), true);
        assert.equal(lines.includes(NVDA_FILING), true);
        assert.equal(lines.includes(FILING_LINK_LABEL), false);
        assert.equal(lines.includes(SEC_FILING_HELPER), true);
        assert.equal(lines.indexOf(SEC_FILING_HELPER), lines.indexOf("SEC filings") + 1);
        assert.equal(lines.includes(OUTLOOK_HELPER), false);
        assert.equal(lines.includes(NO_NEWS_COPY), false);
        assert.equal(lines.includes("Daily updates"), false);
        assert.equal(lines.includes("2026-11-05"), false);
      },
    },
    {
      name: "outlook helper under the first outlook row",
      props: {
        updates: [],
        alerts: [],
        hasLikes: true,
        digest: quietDigest,
        helpers: {},
        filings: [
          {
            ticker: "SONY",
            short_name: "Sony",
            line: "Sony raised its Outlook for the next quarter, according to an SEC filing on Nov 3.",
            filing_url: "https://example.com/sony",
          },
          {
            ticker: "NVDA",
            short_name: "NVIDIA",
            line: "NVIDIA confirmed its earlier outlook, according to an SEC filing on Nov 5.",
            filing_url: NVDA_URL,
          },
          {
            ticker: "AMD",
            short_name: "AMD",
            line: "AMD updated its outlook for the full year, according to an SEC filing on Nov 4.",
            filing_url: AMD_URL,
          },
        ],
      },
      check(lines) {
        const earlier = "NVIDIA confirmed its earlier outlook, according to an SEC filing on Nov 5.";
        const later = "AMD updated its outlook for the full year, according to an SEC filing on Nov 4.";
        assert.equal(lines.filter((line) => line === SEC_FILING_HELPER).length, 1);
        assert.equal(lines.filter((line) => line === OUTLOOK_HELPER).length, 1);
        assert.equal(lines.filter((line) => line === FILING_LINK_LABEL).length, 3);
        assert.equal(lines.indexOf(SEC_FILING_HELPER), lines.indexOf("SEC filings") + 1);
        assert.ok(lines.indexOf(SEC_FILING_HELPER) < lines.indexOf("Sony"));
        assert.ok(lines.indexOf(earlier) < lines.indexOf(OUTLOOK_HELPER));
        assert.ok(lines.indexOf(OUTLOOK_HELPER) < lines.indexOf(later));
        assert.equal(lines.includes("Daily updates"), false);
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
    const filingProps = cases.find((item) => item.name === "filings in server order").props;
    const filingHtml = render.markup(filingProps);
    const filingAnchors = anchorsFrom(filingHtml).filter((anchor) => anchor.text === FILING_LINK_LABEL);
    if (filingHtml.includes("<a ")) {
      assert.deepEqual(filingAnchors.map((anchor) => anchor.href), [AMD_URL, NVDA_URL]);
      for (const anchor of filingAnchors) {
        assert.equal(anchor.target, "_blank");
        assert.match(anchor.rel, /noopener/);
      }
    } else {
      assert.equal(filingAnchors.length, 0);
      assert.equal(filingHtml.includes(NVDA_URL), false);
      assert.equal(filingHtml.includes(FILING_LINK_LABEL), true);
      assert.equal(filingHtml.includes(SEC_FILING_HELPER), true);
      assert.equal(filingHtml.includes("Linking"), false);
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
