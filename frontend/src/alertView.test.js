import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import {
  EARNINGS_HELPER,
  NO_LIKES_COPY,
  NO_NEWS_COPY,
  PRICE_HELPER,
  alertsFrom,
  claimHelperFlags,
  digestBlocks,
  digestSectionFrom,
  helperForAlert,
  newsAlertUrl,
  showDailySection,
  unseenCountFrom,
  filingsFrom,
  updatesEmptyCopy,
  updatesFeed,
  updatesFrom,
  updatesNavLabel,
} from "./alertView.js";

test("the website and iPhone copies of alertView stay the same", () => {
  const web = fs.readFileSync(new URL("./alertView.js", import.meta.url), "utf8");
  const phone = fs.readFileSync(new URL("../../mobile/alertView.js", import.meta.url), "utf8");
  assert.equal(web, phone);
});

test("updates nav label hides a zero count", () => {
  assert.equal(updatesNavLabel(0), "Updates");
  assert.equal(updatesNavLabel(undefined), "Updates");
  assert.equal(updatesNavLabel(3), "Updates (3)");
});

test("payload helpers keep the backend lists and unseen count", () => {
  const data = {
    updates: [{ ticker: "SNE", lines: ["flat"] }],
    alerts: [{ id: 1, kind: "news" }, null],
    unseen_count: 2,
  };
  assert.deepEqual(updatesFrom(data), data.updates);
  assert.deepEqual(alertsFrom(data), [{ id: 1, kind: "news" }]);
  assert.equal(unseenCountFrom(data), 2);
  assert.equal(unseenCountFrom({ unseen_count: 0 }), 0);
  assert.deepEqual(updatesFrom({}), []);
  assert.deepEqual(alertsFrom({}), []);
});

test("empty copy follows likes, alerts, and daily lines", () => {
  assert.equal(
    updatesEmptyCopy({ updates: [], alerts: [], hasLikes: false }),
    NO_LIKES_COPY
  );
  assert.equal(
    updatesEmptyCopy({ updates: [], alerts: [], hasLikes: true }),
    NO_NEWS_COPY
  );
  assert.equal(updatesEmptyCopy({ updates: [], alerts: [], hasLikes: null }), "");
  assert.equal(
    updatesEmptyCopy({ updates: [{ ticker: "SNE" }], alerts: [], hasLikes: true }),
    ""
  );
  assert.equal(
    updatesEmptyCopy({ updates: [], alerts: [{ id: 1 }], hasLikes: true }),
    ""
  );
  assert.equal(showDailySection({ updates: [], alerts: [], hasLikes: false }), false);
  assert.equal(showDailySection({ updates: [], alerts: [], hasLikes: true }), false);
  assert.equal(showDailySection({ updates: [], alerts: [{ id: 1 }], hasLikes: true }), false);
  assert.equal(showDailySection({ updates: [{ ticker: "SNE" }], alerts: [], hasLikes: true }), true);
});

test("news alerts with a url are the only linked lines", () => {
  assert.equal(newsAlertUrl({ kind: "news", url: " https://example.com/a " }), "https://example.com/a");
  assert.equal(newsAlertUrl({ kind: "news", url: null }), "");
  assert.equal(newsAlertUrl({ kind: "price", url: "https://example.com/a" }), "");
  assert.equal(newsAlertUrl({ kind: "news", url: "  " }), "");
});

test("helper text is only under the first alert of that kind", () => {
  const alerts = [
    { id: 3, kind: "news" },
    { id: 2, kind: "price" },
    { id: 1, kind: "price" },
    { id: 4, kind: "earnings" },
  ];
  const flags = { price: true, earnings: true };
  assert.equal(helperForAlert(alerts[1], alerts, flags), PRICE_HELPER);
  assert.equal(helperForAlert(alerts[2], alerts, flags), "");
  assert.equal(helperForAlert(alerts[3], alerts, flags), EARNINGS_HELPER);
  assert.equal(helperForAlert(alerts[0], alerts, flags), "");
  assert.equal(helperForAlert(alerts[1], alerts, { price: false, earnings: false }), "");
});

const HEADER = "For you, Thu, Nov 6";
const QUIET =
  "Quiet one: no price moves of 2% or more and no new headlines for your liked stocks in the last day.";
const NVDA_LINE = "NVIDIA is up 3.0% (as of Nov 5), at US$210.50.";
const SONY_LINE = 'In the news for Sony: "Sony ships a new headset" (Example Wire, Nov 5).';

function digestPayload(items, emptyLine) {
  return {
    updates: [],
    alerts: [],
    unseen_count: 0,
    digest: {
      date: "2026-11-06",
      header: HEADER,
      items,
      empty_line: emptyLine,
      intro: "DO NOT SHOW INTRO",
      more_line: "DO NOT SHOW MORE",
    },
  };
}

function shown(data, hasLikes) {
  return digestBlocks(digestSectionFrom(data, hasLikes));
}

test("a populated digest keeps the server header and line order", () => {
  const blocks = shown(
    digestPayload(
      [
        { ticker: "NVDA", short_name: "NVIDIA", line: NVDA_LINE },
        { ticker: "SONY", short_name: "Sony", line: SONY_LINE },
      ],
      null
    ),
    true
  );
  assert.deepEqual(blocks, [
    { role: "header", text: HEADER },
    { role: "line", text: NVDA_LINE },
    { role: "line", text: SONY_LINE },
  ]);
  assert.equal(JSON.stringify(blocks).includes("DO NOT SHOW"), false);
  assert.equal(JSON.stringify(blocks).includes("2026-11-06"), false);
});

test("a quiet day with likes shows the header and empty line once", () => {
  const blocks = shown(digestPayload([], QUIET), true);
  assert.deepEqual(blocks, [
    { role: "header", text: HEADER },
    { role: "empty", text: QUIET },
  ]);
  assert.equal(blocks.filter((block) => block.role === "empty").length, 1);
});

test("no likes keeps only the existing empty line and hides a server header", () => {
  const data = digestPayload([], null);
  assert.equal(digestSectionFrom(data, false), null);
  assert.deepEqual(shown(data, false), []);
  assert.equal(
    updatesEmptyCopy({ updates: [], alerts: [], hasLikes: false }),
    NO_LIKES_COPY
  );
  assert.equal(shown(data, null).length, 0);
});

test("a missing or null digest adds no section", () => {
  assert.equal(digestSectionFrom({}, true), null);
  assert.equal(digestSectionFrom({ digest: null }, true), null);
  assert.equal(digestSectionFrom(null, true), null);
  assert.deepEqual(shown({ digest: { header: null, items: null, empty_line: null } }, true), []);
  const lineOnly = shown(
    {
      digest: {
        items: [null, { ticker: "NVDA" }, { line: 3 }, { ticker: "SONY", short_name: "Sony", line: SONY_LINE }],
      },
    },
    true
  );
  assert.deepEqual(lineOnly, [{ role: "line", text: SONY_LINE }]);
  const quietWithoutHeader = shown(
    { digest: { header: null, items: [], empty_line: QUIET } },
    true
  );
  assert.deepEqual(quietWithoutHeader, [{ role: "empty", text: QUIET }]);
});

test("the next updates payload replaces digest lines", () => {
  let digest = shown(
    digestPayload(
      [
        { ticker: "NVDA", short_name: "NVIDIA", line: NVDA_LINE },
        { ticker: "SONY", short_name: "Sony", line: SONY_LINE },
      ],
      null
    ),
    true
  );
  digest = shown(
    digestPayload([{ ticker: "SONY", short_name: "Sony", line: SONY_LINE }], null),
    true
  );
  assert.deepEqual(
    digest.map((block) => block.text),
    [HEADER, SONY_LINE]
  );
  digest = shown(digestPayload([], null), false);
  assert.deepEqual(digest, []);
  assert.equal(
    updatesEmptyCopy({ updates: [], alerts: [], hasLikes: false }),
    NO_LIKES_COPY
  );
});

test("a header without lines or a quiet line is not its own section", () => {
  assert.equal(digestSectionFrom(digestPayload([], null), true), null);
  assert.deepEqual(digestBlocks({ header: HEADER, lines: [], emptyLine: null }), []);
});

test("a quiet digest replaces the old empty sentence and empty daily heading", () => {
  const section = digestSectionFrom(digestPayload([], QUIET), true);
  const quiet = updatesFeed({ updates: [], alerts: [], hasLikes: true, digest: section });
  assert.deepEqual(quiet.digest.map((block) => block.text), [HEADER, QUIET]);
  assert.equal(quiet.emptyText, "");
  assert.deepEqual(quiet.daily, []);
  assert.deepEqual(quiet.alerts, []);
  assert.equal(showDailySection({ updates: [], alerts: [], hasLikes: true, digest: section }), false);

  const withDaily = updatesFeed({
    updates: [{ ticker: "RBLX", lines: ["RBLX is about flat (as of Nov 9), at US$40.00."] }],
    alerts: [],
    hasLikes: true,
    digest: section,
  });
  assert.equal(withDaily.daily.length, 1);
  assert.equal(withDaily.emptyText, "");
  assert.equal(withDaily.digest.some((block) => block.text === QUIET), true);

  const withAlert = updatesFeed({
    updates: [],
    alerts: [{ id: 9, ticker: "RBLX", kind: "price", line: "FIXTURE alert", seen: false }],
    hasLikes: true,
    digest: section,
  });
  assert.equal(withAlert.alerts.length, 1);
  assert.deepEqual(withAlert.daily, []);
  assert.equal(withAlert.emptyText, "");
});

test("missing and null digests keep the old no-news sentence and no empty heading", () => {
  for (const digest of [null, undefined]) {
    const feed = updatesFeed({ updates: [], alerts: [], hasLikes: true, digest });
    assert.deepEqual(feed.digest, []);
    assert.equal(feed.emptyText, NO_NEWS_COPY);
    assert.deepEqual(feed.daily, []);
  }
  const headerOnly = updatesFeed({
    updates: [],
    alerts: [],
    hasLikes: true,
    digest: digestSectionFrom(digestPayload([], null), true),
  });
  assert.deepEqual(headerOnly.digest, []);
  assert.equal(headerOnly.emptyText, NO_NEWS_COPY);
});

test("no likes stays a single sentence even if a digest section is passed", () => {
  const feed = updatesFeed({
    updates: [],
    alerts: [],
    hasLikes: false,
    digest: { header: HEADER, lines: [], emptyLine: QUIET },
  });
  assert.deepEqual(feed.digest, []);
  assert.equal(feed.emptyText, NO_LIKES_COPY);
  assert.deepEqual(feed.daily, []);
  assert.deepEqual(feed.alerts, []);
});

test("web and phone screens render UpdatesFeed from the latest digest", () => {
  const web = fs.readFileSync(new URL("./App.jsx", import.meta.url), "utf8");
  const phone = fs.readFileSync(new URL("../../mobile/App.js", import.meta.url), "utf8");
  const webFeed = fs.readFileSync(new URL("./UpdatesFeed.jsx", import.meta.url), "utf8");
  const phoneFeed = fs.readFileSync(new URL("../../mobile/UpdatesFeed.js", import.meta.url), "utf8");
  const view = fs.readFileSync(new URL("./alertView.js", import.meta.url), "utf8");
  for (const source of [web, phone, view, webFeed, phoneFeed]) {
    assert.equal(source.includes("Quiet one:"), false);
    assert.equal(source.includes("For you,"), false);
    assert.equal(source.includes("more_line"), false);
  }
  for (const source of [web, phone]) {
    assert.match(source, /setDigest\(digestSectionFrom\(data, likes\)\)/);
    assert.match(source, /<UpdatesFeed/);
    assert.equal(source.includes("Daily updates"), false);
  }
  for (const source of [webFeed, phoneFeed]) {
    assert.match(source, /updatesFeed\(/);
    const digestAt = source.indexOf("feed.digest");
    const alertsAt = source.indexOf(">Alerts<");
    const filingsAt = source.indexOf(">SEC filings<");
    const dailyAt = source.indexOf("Daily updates");
    assert.ok(digestAt !== -1 && alertsAt !== -1 && filingsAt !== -1 && dailyAt !== -1);
    assert.ok(digestAt < alertsAt);
    assert.ok(alertsAt < filingsAt);
    assert.ok(filingsAt < dailyAt);
  }
});

const NVDA_FILING = "NVIDIA shared its latest quarterly results in an SEC filing on Nov 5.";
const AMD_FILING = "AMD reported a major deal in an SEC filing on Nov 4. The filing has the details.";
const NVDA_URL = "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000010/0001045810-26-000010-index.html";
const AMD_URL = "https://www.sec.gov/Archives/edgar/data/2488/000000248826000020/0000002488-26-000020-index.html";

function filingRow(overrides) {
  return {
    ticker: "NVDA",
    short_name: "NVIDIA",
    accession: "0001045810-26-000010",
    date_ny: "2026-11-05",
    line: NVDA_FILING,
    filing_url: NVDA_URL,
    ...overrides,
  };
}

test("filings stay in server order with the line and link untouched", () => {
  const spaced = ` ${AMD_FILING} `;
  const data = {
    filings: [
      filingRow({
        ticker: "AMD",
        short_name: "AMD",
        accession: "0000002488-26-000020",
        date_ny: "2026-11-01",
        line: spaced,
        filing_url: ` ${AMD_URL} `,
      }),
      filingRow(),
    ],
  };
  const rows = filingsFrom(data);
  assert.deepEqual(rows, [
    { name: "AMD", line: spaced, url: AMD_URL },
    { name: "NVIDIA", line: NVDA_FILING, url: NVDA_URL },
  ]);
  assert.equal(JSON.stringify(rows).includes("2026-11-01"), false);
  assert.equal(JSON.stringify(rows).includes("2026-11-05"), false);
  assert.deepEqual(Object.keys(rows[0]).sort(), ["line", "name", "url"]);
  const section = digestSectionFrom(digestPayload([], QUIET), true);
  const feed = updatesFeed({
    updates: [],
    alerts: [],
    hasLikes: true,
    digest: section,
    filings: data.filings,
  });
  assert.deepEqual(feed.filings, rows);
  assert.deepEqual(feed.digest.map((block) => block.text), [HEADER, QUIET]);
  assert.equal(feed.emptyText, "");
  assert.deepEqual(feed.daily, []);
  assert.deepEqual(feed.alerts, []);
  assert.equal(showDailySection({
    updates: [],
    alerts: [],
    hasLikes: true,
    digest: section,
    filings: data.filings,
  }), false);

  const replaced = filingsFrom({ filings: [filingRow()] });
  assert.deepEqual(replaced, [{ name: "NVIDIA", line: NVDA_FILING, url: NVDA_URL }]);
  assert.deepEqual(filingsFrom({}), []);
});

test("a filing with no short name uses the ticker and still keeps a missing link off", () => {
  assert.deepEqual(
    filingsFrom({
      filings: [
        { ticker: "NVDA", line: NVDA_FILING, filing_url: NVDA_URL, date_ny: "2026-11-05" },
        { ticker: "AMD", short_name: "", line: AMD_FILING, filing_url: null, date_ny: "2026-11-04" },
        { ticker: "SONY", short_name: "Sony", line: SONY_LINE, filing_url: "   " },
      ],
    }),
    [
      { name: "NVDA", line: NVDA_FILING, url: NVDA_URL },
      { name: "AMD", line: AMD_FILING, url: "" },
      { name: "Sony", line: SONY_LINE, url: "" },
    ]
  );
});

test("missing, null, empty, and malformed filings add no section", () => {
  assert.deepEqual(filingsFrom(null), []);
  assert.deepEqual(filingsFrom(undefined), []);
  assert.deepEqual(filingsFrom({}), []);
  assert.deepEqual(filingsFrom({ filings: null }), []);
  assert.deepEqual(filingsFrom({ filings: {} }), []);
  assert.deepEqual(filingsFrom({ filings: "nope" }), []);
  assert.deepEqual(filingsFrom({ filings: [] }), []);
  assert.deepEqual(
    filingsFrom({
      filings: [
        null,
        { ticker: "NVDA", short_name: "NVIDIA", line: 3, filing_url: NVDA_URL },
        { ticker: "AMD", short_name: "AMD", filing_url: AMD_URL },
        "bad",
        { ticker: "SONY", short_name: "Sony", line: SONY_LINE, filing_url: AMD_URL, date_ny: "2026-11-02" },
      ],
    }),
    [{ name: "Sony", line: SONY_LINE, url: AMD_URL }]
  );

  const quietSection = digestSectionFrom(digestPayload([], QUIET), true);
  for (const filings of [undefined, null, [], "nope", {}]) {
    const quiet = updatesFeed({
      updates: [],
      alerts: [],
      hasLikes: true,
      digest: quietSection,
      filings,
    });
    assert.deepEqual(quiet.filings, []);
    assert.deepEqual(quiet.digest.map((block) => block.text), [HEADER, QUIET]);
    assert.equal(quiet.emptyText, "");
    assert.deepEqual(quiet.daily, []);
    assert.deepEqual(quiet.alerts, []);

    const noLikes = updatesFeed({
      updates: [],
      alerts: [],
      hasLikes: false,
      digest: { header: HEADER, lines: [NVDA_LINE], emptyLine: QUIET },
      filings,
    });
    assert.deepEqual(noLikes.filings, []);
    assert.deepEqual(noLikes.digest, []);
    assert.equal(noLikes.emptyText, NO_LIKES_COPY);
    assert.deepEqual(noLikes.daily, []);
    assert.deepEqual(noLikes.alerts, []);

    const noNews = updatesFeed({
      updates: [],
      alerts: [],
      hasLikes: true,
      digest: null,
      filings,
    });
    assert.deepEqual(noNews.filings, []);
    assert.deepEqual(noNews.digest, []);
    assert.equal(noNews.emptyText, NO_NEWS_COPY);
    assert.deepEqual(noNews.daily, []);
  }
});

test("filing lines do not replace a quiet digest or invent a daily heading", () => {
  const section = digestSectionFrom(digestPayload([], QUIET), true);
  const feed = updatesFeed({
    updates: [{ ticker: "RBLX", lines: ["RBLX is about flat (as of Nov 9), at US$40.00."] }],
    alerts: [{ id: 9, ticker: "RBLX", kind: "price", line: "FIXTURE alert", seen: false }],
    hasLikes: true,
    digest: section,
    filings: [filingRow()],
  });
  assert.deepEqual(feed.digest.map((block) => block.text), [HEADER, QUIET]);
  assert.equal(feed.filings.length, 1);
  assert.equal(feed.filings[0].line, NVDA_FILING);
  assert.equal(feed.alerts.length, 1);
  assert.equal(feed.daily.length, 1);
  assert.equal(feed.emptyText, "");

  const filingsOnly = updatesFeed({
    updates: [],
    alerts: [],
    hasLikes: true,
    digest: null,
    filings: [filingRow()],
  });
  assert.deepEqual(filingsOnly.digest, []);
  assert.equal(filingsOnly.emptyText, "");
  assert.deepEqual(filingsOnly.daily, []);
  assert.equal(filingsOnly.filings[0].line, NVDA_FILING);
});

test("the clients pass filings through and do not format a filing date", () => {
  const web = fs.readFileSync(new URL("./App.jsx", import.meta.url), "utf8");
  const phone = fs.readFileSync(new URL("../../mobile/App.js", import.meta.url), "utf8");
  const webFeed = fs.readFileSync(new URL("./UpdatesFeed.jsx", import.meta.url), "utf8");
  const phoneFeed = fs.readFileSync(new URL("../../mobile/UpdatesFeed.js", import.meta.url), "utf8");
  const view = fs.readFileSync(new URL("./alertView.js", import.meta.url), "utf8");
  for (const source of [web, phone]) {
    assert.match(source, /setFilings\(data \? data\.filings : null\)/);
    assert.match(source, /filings=\{filings\}/);
    assert.equal(source.includes("date_ny"), false);
    assert.equal(source.includes("sec.gov"), false);
  }
  for (const source of [webFeed, phoneFeed, view]) {
    assert.equal(source.includes("date_ny"), false);
    assert.equal(source.includes(".sort("), false);
  }
  assert.match(webFeed, /target="_blank"/);
  assert.match(webFeed, /rel="noopener/);
  assert.match(phoneFeed, /Linking\.openURL\(filing\.url\)/);
  const filingsFn = view.slice(view.indexOf("export function filingsFrom"), view.indexOf("export function updatesFeed"));
  assert.equal(filingsFn.includes("Date"), false);
  assert.equal(filingsFn.includes("new "), false);
});

test("helper flags are stored once per user", async () => {
  const saved = new Map();
  const storage = {
    getItem: async (key) => (saved.has(key) ? saved.get(key) : null),
    setItem: async (key, value) => {
      saved.set(key, value);
    },
  };
  const alerts = [
    { id: 1, kind: "price" },
    { id: 2, kind: "earnings" },
  ];
  assert.deepEqual(await claimHelperFlags("user-a", alerts, storage), {
    price: true,
    earnings: true,
  });
  assert.deepEqual(await claimHelperFlags("user-a", alerts, storage), {
    price: false,
    earnings: false,
  });
  assert.deepEqual(await claimHelperFlags("user-b", [{ id: 3, kind: "price" }], storage), {
    price: true,
    earnings: false,
  });
});
