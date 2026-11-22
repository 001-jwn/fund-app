const BASE = "/api";

export const NETWORK_ERROR = "Can't reach the server right now. Check your connection and try again.";

export const GENERIC_ERROR = "Something went wrong. Try again.";

const CODE_FALLBACKS = {
  not_found: "We couldn't find that. Please try again.",
  bad_request: "That didn't work. Please try again.",
  rate_limited: "Lots of requests right now. Wait a moment and try again.",
  data_unavailable: "This information isn't available yet. Check back a little later.",
  server_error: GENERIC_ERROR,
};

// Today's errors are {"detail": string}. Newer errors add "code".
// A 5xx with no string code is the Vite proxy (or a dead server), not a real error body.
export function messageForHttpError(status, body) {
  const statusCode = Number(status);
  const is5xx = statusCode >= 500 && statusCode <= 599;
  const record = body && typeof body === "object" && !Array.isArray(body) ? body : null;
  const detail = record && typeof record.detail === "string" ? record.detail.trim() : "";
  const code = record && typeof record.code === "string" ? record.code.trim() : "";
  if (is5xx && !code) {
    return { message: NETWORK_ERROR, network: true, specific: false };
  }
  if (detail) {
    return { message: detail, network: false, specific: true };
  }
  if (is5xx && code) {
    return { message: GENERIC_ERROR, network: false, specific: true };
  }
  if (code && Object.prototype.hasOwnProperty.call(CODE_FALLBACKS, code)) {
    return { message: CODE_FALLBACKS[code], network: false, specific: true };
  }
  return { message: GENERIC_ERROR, network: false, specific: false };
}

function errorFromResponse(status, body) {
  const resolved = messageForHttpError(status, body);
  const error = new Error(resolved.message);
  error.status = status;
  error.network = resolved.network;
  error.specific = resolved.specific;
  const code = body && typeof body === "object" && !Array.isArray(body) && typeof body.code === "string"
    ? body.code.trim()
    : "";
  if (code) error.code = code;
  return error;
}

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
    const error = new Error(NETWORK_ERROR);
    error.network = true;
    error.specific = false;
    throw error;
  }

  if (!response.ok) {
    let body = null;
    try {
      body = await response.json();
    } catch (_err) {
      body = null;
    }
    throw errorFromResponse(response.status, body);
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

export function getUpdates(userId) {
  const params = new URLSearchParams({ user_id: userId });
  return request(`/updates?${params.toString()}`);
}

export function markAlertsSeen(userId) {
  return request("/alerts/seen", {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}
