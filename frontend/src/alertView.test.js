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
  updatesEmptyCopy,
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
  assert.equal(showDailySection({ updates: [], alerts: [], hasLikes: true }), true);
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

test("web and phone render the same digest above alerts", () => {
  const web = fs.readFileSync(new URL("./App.jsx", import.meta.url), "utf8");
  const phone = fs.readFileSync(new URL("../../mobile/App.js", import.meta.url), "utf8");
  const view = fs.readFileSync(new URL("./alertView.js", import.meta.url), "utf8");
  for (const source of [web, phone, view]) {
    assert.equal(source.includes("Quiet one:"), false);
    assert.equal(source.includes("For you,"), false);
    assert.equal(source.includes("more_line"), false);
  }
  for (const source of [web, phone]) {
    assert.match(source, /setDigest\(digestSectionFrom\(data, likes\)\)/);
    assert.match(source, /\{!loading \? <DigestSection digest=\{digest\} \/> : null\}/);
    const digestAt = source.indexOf("<DigestSection digest={digest} />");
    const alertsAt = source.includes("<h3>Alerts</h3>")
      ? source.indexOf("<h3>Alerts</h3>")
      : source.indexOf(">Alerts</Text>");
    const dailyAt = source.indexOf("Daily updates");
    assert.ok(digestAt !== -1 && alertsAt !== -1 && dailyAt !== -1);
    assert.ok(digestAt < alertsAt);
    assert.ok(digestAt < dailyAt);
  }
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
