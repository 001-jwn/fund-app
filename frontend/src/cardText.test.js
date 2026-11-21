import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import {
  LIVE_DATA_BANNER,
  PRICE_UNAVAILABLE,
  liveDataMissing,
  priceLine,
  roundHalfUpOneDecimal,
  showLiveDataBanner,
} from "./cardText.js";

test("the website and iPhone price helpers stay the same", () => {
  const web = fs.readFileSync(new URL("./cardText.js", import.meta.url), "utf8");
  const phone = fs.readFileSync(new URL("../../mobile/cardText.js", import.meta.url), "utf8");
  assert.equal(web, phone);
});

test("half-up rounding matches one decimal, including the edges toFixed gets wrong", () => {
  const cases = [
    [0.05, "0.1"],
    [-0.05, "-0.1"],
    [1.25, "1.3"],
    [1.35, "1.4"],
    [2.35, "2.4"],
    [2.675, "2.7"],
    [0.04999, "0.0"],
    [0.04, "0.0"],
    [-0.04, "0.0"],
    [0, "0.0"],
    [1.26, "1.3"],
    [-2.04, "-2.0"],
    [9.95, "10.0"],
    [0.15, "0.2"],
    [-0.15, "-0.2"],
    [1.15, "1.2"],
    [-1.25, "-1.3"],
    [2.5, "2.5"],
  ];
  for (const [value, expected] of cases) {
    assert.equal(roundHalfUpOneDecimal(value), expected, String(value));
  }
  assert.equal(roundHalfUpOneDecimal(Number.NaN), null);
  assert.equal(roundHalfUpOneDecimal(Number.POSITIVE_INFINITY), null);
  assert.equal((1.25).toFixed(1) === "1.3" || (0.15).toFixed(1) !== "0.2", true);
  assert.notEqual((0.15).toFixed(1), roundHalfUpOneDecimal(0.15));
});

function card(overrides) {
  return {
    price_available: true,
    current_price: 50,
    price_change_percent: 1.25,
    ...overrides,
  };
}

test("the price line says up, down, or about flat at the same threshold", () => {
  assert.equal(priceLine(card({ price_change_percent: 0.05 })), "Price: US$50.00, up 0.1%");
  assert.equal(priceLine(card({ price_change_percent: -0.05 })), "Price: US$50.00, down 0.1%");
  assert.equal(priceLine(card({ price_change_percent: 1.25 })), "Price: US$50.00, up 1.3%");
  assert.equal(priceLine(card({ price_change_percent: 1.35 })), "Price: US$50.00, up 1.4%");
  assert.equal(priceLine(card({ price_change_percent: 2.675 })), "Price: US$50.00, up 2.7%");
  assert.equal(priceLine(card({ price_change_percent: -2.04, current_price: 100 })), "Price: US$100.00, down 2.0%");
  assert.equal(priceLine(card({ price_change_percent: 0.04 })), "Price: US$50.00, about flat");
  assert.equal(priceLine(card({ price_change_percent: -0.04 })), "Price: US$50.00, about flat");
  assert.equal(priceLine(card({ price_change_percent: 0 })), "Price: US$50.00, about flat");
  assert.equal(priceLine(card({ price_change_percent: 0.04999 })), "Price: US$50.00, about flat");
  assert.equal(priceLine(card()).includes("change"), false);
});

test("a missing price, a non-positive price, or a non-finite percent is not available", () => {
  assert.equal(PRICE_UNAVAILABLE, "Price: not available");
  assert.equal(priceLine(card({ current_price: null })), PRICE_UNAVAILABLE);
  assert.equal(priceLine(card({ current_price: undefined })), PRICE_UNAVAILABLE);
  assert.equal(priceLine(card({ current_price: 0 })), PRICE_UNAVAILABLE);
  assert.equal(priceLine(card({ current_price: -5 })), PRICE_UNAVAILABLE);
  assert.equal(priceLine(card({ price_change_percent: null })), PRICE_UNAVAILABLE);
  assert.equal(priceLine(card({ price_change_percent: Number.NaN })), PRICE_UNAVAILABLE);
  assert.equal(priceLine(card({ price_change_percent: Number.POSITIVE_INFINITY })), PRICE_UNAVAILABLE);
  assert.equal(priceLine(card({ price_available: false })), PRICE_UNAVAILABLE);
  assert.equal(priceLine(null), PRICE_UNAVAILABLE);
});

test("a card with no quote-date field still shows the price, and a missing date hides it", () => {
  const shown = card();
  assert.equal(Object.prototype.hasOwnProperty.call(shown, "latest_quote_at"), false);
  assert.equal(priceLine(shown), "Price: US$50.00, up 1.3%");
  assert.equal(priceLine(card({ latest_quote_at: null })), "");
  assert.equal(priceLine(card({ latest_quote_at: "" })), "");
  assert.equal(priceLine(card({ latest_quote_at: "not-a-date" })), "");
  assert.equal(priceLine(card({ latest_quote_at: "1970-01-01T00:00:00Z" })), "");
  assert.equal(
    priceLine(card({ latest_quote_at: "2026-11-03T16:00:00Z" })),
    "Price: US$50.00, up 1.3%"
  );
});

test("the data banner is only for a price or news gap that is actually on screen", () => {
  const ready = {
    current_price: 50,
    latest_news_headline: "A real headline",
    news_message: null,
  };
  const noNewsYet = {
    current_price: 40,
    latest_news_headline: null,
    news_message: "No recent news about this company yet.",
  };
  const missingNews = {
    current_price: 40,
    latest_news_headline: "",
    news_message: "",
  };
  const missingPrice = {
    current_price: null,
    latest_news_headline: "A real headline",
  };
  assert.equal(liveDataMissing(ready), false);
  assert.equal(liveDataMissing(noNewsYet), false);
  assert.equal(liveDataMissing(missingNews), true);
  assert.equal(liveDataMissing(missingPrice), true);
  assert.equal(liveDataMissing({ current_price: 0, latest_news_headline: "Headline" }), true);
  assert.equal(liveDataMissing(missingNews, { includeNews: false }), false);
  assert.equal(showLiveDataBanner({ screen: "swipe", card: ready }), false);
  assert.equal(showLiveDataBanner({ screen: "swipe", card: missingNews }), true);
  assert.equal(showLiveDataBanner({ screen: "swipe", card: null }), false);
  assert.equal(showLiveDataBanner({ screen: "matches", matches: [ready, noNewsYet] }), false);
  assert.equal(showLiveDataBanner({ screen: "matches", matches: [ready, missingPrice] }), true);
  assert.equal(showLiveDataBanner({ screen: "updates", card: missingPrice, matches: [missingPrice] }), false);
  assert.equal(LIVE_DATA_BANNER, "Live prices and news aren't available right now.");
  assert.equal(LIVE_DATA_BANNER.toLowerCase().includes("key"), false);
});
