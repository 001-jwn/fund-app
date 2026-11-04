const BASE = "/api";

async function request(path, options = {}) {
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
