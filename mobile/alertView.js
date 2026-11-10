// Same file in frontend/src and mobile. Keep the two copies identical.

export const NO_LIKES_COPY =
  "Like a few stocks and their daily updates will show up here.";

export const NO_NEWS_COPY =
  "No big news on your liked stocks right now. We'll flag big price moves, upcoming results and fresh headlines here.";

export const PRICE_HELPER =
  "We flag a liked stock when its price moves 5% or more in a day.";

export const EARNINGS_HELPER = "Companies share their results every three months.";

export const SEC_FILING_HELPER =
  "An SEC filing is a report a company must send to the US regulator, the Securities and Exchange Commission.";

export const OUTLOOK_HELPER =
  "An outlook is the company's own estimate of what it expects. It is not a promise.";

export const FILING_LINK_LABEL = "Read the filing";

const KIND_LABELS = {
  price: "Price",
  earnings: "Earnings",
  news: "News",
};

export function updatesFrom(data) {
  if (!data || !Array.isArray(data.updates)) return [];
  return data.updates;
}

export function alertsFrom(data) {
  if (!data || !Array.isArray(data.alerts)) return [];
  return data.alerts.filter((alert) => alert && typeof alert === "object");
}

export function unseenCountFrom(data) {
  const count = Number(data && data.unseen_count);
  if (!Number.isFinite(count) || count <= 0) return 0;
  return Math.floor(count);
}

export function updatesNavLabel(unseenCount) {
  const count = unseenCountFrom({ unseen_count: unseenCount });
  if (count <= 0) return "Updates";
  return `Updates (${count})`;
}

export function alertKindLabel(kind) {
  if (typeof kind !== "string" || !kind) return "Alert";
  return KIND_LABELS[kind] || kind;
}

export function newsAlertUrl(alert) {
  if (!alert || alert.kind !== "news") return "";
  if (typeof alert.url !== "string") return "";
  return alert.url.trim();
}

export function helperStorageKey(kind, userId) {
  return `fund_alert_helper_${kind}:${userId}`;
}

export function helperForAlert(alert, alerts, flags) {
  if (!alert || !flags || flags[alert.kind] !== true) return "";
  if (!Array.isArray(alerts)) return "";
  const first = alerts.find((item) => item && item.kind === alert.kind);
  if (!first || first.id !== alert.id) return "";
  if (alert.kind === "price") return PRICE_HELPER;
  if (alert.kind === "earnings") return EARNINGS_HELPER;
  return "";
}

// Server order and the server sentence. A missing, null, or non-array list is
// not a section. An entry without a string line is skipped. The filing date is unused.
export function filingsFrom(data) {
  const raw = data && data.filings;
  if (!Array.isArray(raw)) return [];
  const rows = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    if (typeof item.line !== "string") continue;
    let name = "";
    if (typeof item.short_name === "string" && item.short_name.length > 0) {
      name = item.short_name;
    } else if (typeof item.ticker === "string") {
      name = item.ticker;
    }
    const url = typeof item.filing_url === "string" && item.filing_url.trim().length > 0
      ? item.filing_url.trim()
      : "";
    rows.push({ name, line: item.line, url });
  }
  return rows;
}

// Shown on every render. Nothing is stored. The SEC line sits under the
// heading when any row is visible. The outlook line sits under the first row
// whose sentence contains the lowercase substring "outlook".
export function filingHelpers(rows) {
  const list = Array.isArray(rows) ? rows : [];
  let outlookIndex = -1;
  for (let index = 0; index < list.length; index += 1) {
    const row = list[index];
    const line = row && row.line;
    if (typeof line === "string" && line.includes("outlook")) {
      outlookIndex = index;
      break;
    }
  }
  if (list.length === 0) {
    return { sec: "", outlook: "", outlookIndex: -1 };
  }
  return {
    sec: SEC_FILING_HELPER,
    outlook: outlookIndex >= 0 ? OUTLOOK_HELPER : "",
    outlookIndex,
  };
}

// What the Updates tab shows. digest is the result of digestSectionFrom.
// A quiet digest replaces the old empty sentence and the empty Daily updates heading.
// Lines and alerts that are actually present stay on screen.
export function updatesFeed({ updates, alerts, hasLikes, digest, filings }) {
  const updateList = Array.isArray(updates) ? updates : [];
  const alertList = Array.isArray(alerts)
    ? alerts.filter((alert) => alert && typeof alert === "object")
    : [];
  const digestLines = hasLikes === true ? digestBlocks(digest) : [];
  const filingList = filingsFrom({ filings });
  let emptyText = "";
  if (updateList.length === 0 && alertList.length === 0) {
    if (hasLikes === false) emptyText = NO_LIKES_COPY;
    else if (hasLikes === true && digestLines.length === 0 && filingList.length === 0) {
      emptyText = NO_NEWS_COPY;
    }
  }
  return {
    digest: digestLines,
    alerts: alertList,
    filings: filingList,
    daily: updateList,
    emptyText,
  };
}

export function updatesEmptyCopy(input) {
  return updatesFeed(input).emptyText;
}

export function showDailySection(input) {
  return updatesFeed(input).daily.length > 0;
}

// Server copy only. A header with no lines and no quiet line is not a section,
// including when the server still sends a header for someone with no likes.
export function digestSectionFrom(data, hasLikes) {
  if (hasLikes !== true) return null;
  const raw = data && data.digest;
  if (!raw || typeof raw !== "object") return null;
  const header = typeof raw.header === "string" && raw.header.length > 0 ? raw.header : null;
  const items = Array.isArray(raw.items) ? raw.items : [];
  const lines = [];
  for (const item of items) {
    if (!item || typeof item !== "object") continue;
    if (typeof item.line !== "string") continue;
    lines.push(item.line);
  }
  if (lines.length > 0) {
    return { header, lines, emptyLine: null };
  }
  const emptyLine = typeof raw.empty_line === "string" && raw.empty_line.length > 0
    ? raw.empty_line
    : null;
  if (!emptyLine) return null;
  return { header, lines: [], emptyLine };
}

export function digestBlocks(section) {
  if (!section || typeof section !== "object") return [];
  const lines = Array.isArray(section.lines)
    ? section.lines.filter((line) => typeof line === "string")
    : [];
  let body = lines.map((text) => ({ role: "line", text }));
  if (body.length === 0 && typeof section.emptyLine === "string" && section.emptyLine.length > 0) {
    body = [{ role: "empty", text: section.emptyLine }];
  }
  if (body.length === 0) return [];
  if (typeof section.header === "string" && section.header.length > 0) {
    return [{ role: "header", text: section.header }, ...body];
  }
  return body;
}

export async function claimHelperFlags(userId, alerts, storage) {
  const flags = { price: false, earnings: false };
  if (!userId || !storage || !Array.isArray(alerts)) return flags;
  for (const kind of ["price", "earnings"]) {
    if (!alerts.some((alert) => alert && alert.kind === kind)) continue;
    const key = helperStorageKey(kind, userId);
    const existing = await storage.getItem(key);
    if (existing === "1") continue;
    await storage.setItem(key, "1");
    flags[kind] = true;
  }
  return flags;
}
