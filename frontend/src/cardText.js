export const LIVE_DATA_BANNER = "Live prices and news aren't available right now.";

export const PRICE_UNAVAILABLE = "Price: not available";

// Round a finite number to one decimal place, half away from zero.
// Matches Python Decimal(str(value)).quantize(Decimal("0.1"), ROUND_HALF_UP).
// JS Number#toFixed is not that rule. This works on the decimal string.
// Returns a one-decimal string such as "1.3", "-0.1", or "0.0", or null.
export function roundHalfUpOneDecimal(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const text = Object.is(value, -0) ? "-0.0" : String(value);
  const tenths = tenthsFromDecimalString(text);
  if (tenths === null) return null;
  return formatTenths(tenths);
}

function tenthsFromDecimalString(text) {
  let raw = String(text).trim();
  if (!raw) return null;
  let sign = 1;
  if (raw[0] === "+") raw = raw.slice(1);
  else if (raw[0] === "-") {
    sign = -1;
    raw = raw.slice(1);
  }
  const plain = expandScientific(raw);
  if (!/^\d+(\.\d+)?$/.test(plain)) return null;
  const parts = plain.split(".");
  const whole = parts[0];
  const frac = parts[1] || "";
  const tenthsDigit = frac[0] || "0";
  const rest = frac.slice(1);
  let digits = `${whole}${tenthsDigit}`.replace(/^0+(?=\d)/, "");
  if (rest.length > 0 && rest[0] >= "5") digits = incrementDigits(digits);
  const abs = Number(digits);
  if (!Number.isSafeInteger(abs)) return null;
  const tenths = sign * abs;
  return tenths === 0 ? 0 : tenths;
}

function expandScientific(unsigned) {
  const match = /^(\d+)(?:\.(\d+))?[eE]([+-]?\d+)$/.exec(unsigned);
  if (!match) return unsigned;
  const digits = `${match[1]}${match[2] || ""}`;
  const exp = Number(match[3]);
  if (!Number.isFinite(exp)) return unsigned;
  const point = match[1].length + exp;
  if (point <= 0) return `0.${"0".repeat(-point)}${digits}`;
  if (point >= digits.length) return digits + "0".repeat(point - digits.length);
  return `${digits.slice(0, point)}.${digits.slice(point)}`;
}

function incrementDigits(digits) {
  const chars = digits.split("");
  let index = chars.length - 1;
  while (index >= 0 && chars[index] === "9") {
    chars[index] = "0";
    index -= 1;
  }
  if (index < 0) return `1${chars.join("")}`;
  chars[index] = String(Number(chars[index]) + 1);
  return chars.join("");
}

function formatTenths(tenths) {
  const abs = Math.abs(tenths);
  const text = `${Math.trunc(abs / 10)}.${abs % 10}`;
  if (tenths < 0) return `-${text}`;
  return text;
}

function priceNumber(value) {
  if (typeof value === "boolean" || value == null) return null;
  const price = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(price)) return null;
  return price;
}

function percentNumber(value) {
  if (typeof value === "boolean" || value == null || value === "") return null;
  const pct = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(pct)) return null;
  return pct;
}

// Updates omits a price when the quote date is missing. Cards from the API
// have no quote-date field, so a missing field keeps today's card behavior.
function quoteDateBlocks(card) {
  if (!Object.prototype.hasOwnProperty.call(card, "latest_quote_at")) return false;
  return !quoteDateUsable(card.latest_quote_at);
}

function quoteDateUsable(value) {
  if (value == null || value === "") return false;
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return false;
  let yearText = "";
  try {
    yearText = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      year: "numeric",
    }).format(date);
  } catch (_err) {
    return false;
  }
  const year = Number(yearText);
  return Number.isFinite(year) && year >= 1971;
}

export function priceLine(card) {
  if (!card || typeof card !== "object") return PRICE_UNAVAILABLE;
  const price = priceNumber(card.current_price);
  if (price === null || price <= 0) return "";
  if (card.price_available === false) return PRICE_UNAVAILABLE;
  const pct = percentNumber(card.price_change_percent);
  if (pct === null) return PRICE_UNAVAILABLE;
  if (quoteDateBlocks(card)) return "";
  const money = `US$${price.toFixed(2)}`;
  const rounded = roundHalfUpOneDecimal(pct);
  if (!rounded || rounded === "0.0" || rounded === "-0.0") {
    return `Price: ${money}, about flat`;
  }
  const shown = rounded.startsWith("-") ? rounded.slice(1) : rounded;
  if (rounded.startsWith("-")) return `Price: ${money}, down ${shown}%`;
  return `Price: ${money}, up ${shown}%`;
}

function textOf(value) {
  return typeof value === "string" ? value.trim() : "";
}

export function liveDataMissing(card, options = {}) {
  if (!card || typeof card !== "object") return false;
  const includeNews = options.includeNews !== false;
  const price = priceNumber(card.current_price);
  const priceMissing = price === null || price <= 0;
  if (priceMissing) return true;
  if (!includeNews) return false;
  const headline = textOf(card.latest_news_headline);
  const message = textOf(card.news_message);
  return !headline && !message;
}

export function showLiveDataBanner({ screen, card, matches } = {}) {
  if (screen === "swipe") return Boolean(card) && liveDataMissing(card, { includeNews: true });
  if (screen === "matches") {
    return Array.isArray(matches) && matches.some((item) => liveDataMissing(item, { includeNews: false }));
  }
  return false;
}

export function becauseLikedText(card) {
  if (!card || typeof card.because_liked !== "string") return "";
  const name = card.because_liked.trim();
  if (!name) return "";
  return `Because you liked ${name}`;
}

// The server list replaces the queue after a like. The liked ticker is
// dropped, and repeated tickers are dropped. If the card that was about
// to be shown is missing from this page, it stays at the front.
export function nextQueueAfterLike(queue, likedTicker, freshCards) {
  const upcoming = Array.isArray(queue) ? queue[1] : undefined;
  const seen = new Set();
  if (likedTicker) seen.add(likedTicker);
  const fresh = [];
  for (const card of freshCards || []) {
    if (!card || !card.ticker || seen.has(card.ticker)) continue;
    seen.add(card.ticker);
    fresh.push(card);
  }
  if (!upcoming || !upcoming.ticker || upcoming.ticker === likedTicker || seen.has(upcoming.ticker)) {
    return fresh;
  }
  return [upcoming, ...fresh];
}
