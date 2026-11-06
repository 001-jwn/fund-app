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
