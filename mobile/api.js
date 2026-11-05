// Phone copy of frontend/src/api.js.
// The website calls "/api" and Vite forwards that to the backend.
// This app calls the backend directly. EXPO_PUBLIC_API_URL is the full
// origin, for example http://192.168.1.20:8000. Set it in mobile/.env.
// This file never calls Finnhub and never reads an API key.

const BASE = (process.env.EXPO_PUBLIC_API_URL || "").replace(/\/$/, "");

async function request(path, options = {}) {
  if (!BASE) {
    throw new Error(
      "The API address is not set. In mobile/.env set EXPO_PUBLIC_API_URL to your Mac, then start Expo again."
    );
  }

  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
  } catch (_err) {
    throw new Error("Cannot reach the app server. Is the backend running?");
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") {
        detail = body.detail;
      }
    } catch (_err) {
      // Keep the status text.
    }
    const error = new Error(detail || "Request failed");
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export function getHealth() {
  return request("/health");
}

export function onboard(interests) {
  return request("/onboarding", {
    method: "POST",
    body: JSON.stringify({ interests }),
  });
}

export function getCards(userId, limit = 10) {
  const params = new URLSearchParams({ user_id: userId, limit: String(limit) });
  return request(`/cards?${params.toString()}`);
}

export function likeCompany(userId, ticker) {
  return request("/like", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, ticker }),
  });
}

export function unlikeCompany(userId, ticker) {
  return request("/unlike", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, ticker }),
  });
}

export function dislikeCompany(userId, ticker) {
  return request("/dislike", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, ticker }),
  });
}

export function getMatches(userId) {
  const params = new URLSearchParams({ user_id: userId });
  return request(`/matches?${params.toString()}`);
}
