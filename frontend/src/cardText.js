export function priceLine(card) {
  if (!card.price_available || card.current_price == null) {
    return "Price: unavailable";
  }
  const money = `US$${Number(card.current_price).toFixed(2)}`;
  if (card.price_change_percent == null) {
    return `Price: ${money}`;
  }
  const pct = Number(card.price_change_percent);
  const sign = pct > 0 ? "+" : "";
  return `Price: ${money} (${sign}${pct.toFixed(2)}% change)`;
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
