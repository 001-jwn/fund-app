import assert from "node:assert/strict";
import test from "node:test";
import {
  GENERIC_ERROR,
  NETWORK_ERROR,
  getHealth,
  messageForHttpError,
} from "./api.js";

const CODES = {
  not_found: "We couldn't find that. Please try again.",
  bad_request: "That didn't work. Please try again.",
  rate_limited: "Lots of requests right now. Wait a moment and try again.",
  data_unavailable: "This information isn't available yet. Check back a little later.",
  server_error: "Something went wrong. Try again.",
};

test("a string detail is shown, and a code fills in only when detail is empty", () => {
  assert.deepEqual(messageForHttpError(404, { detail: "User not found.", code: "not_found" }), {
    message: "User not found.",
    network: false,
    specific: true,
  });
  for (const [code, message] of Object.entries(CODES)) {
    assert.equal(messageForHttpError(400, { code }).message, message, code);
    assert.equal(messageForHttpError(400, { detail: "  ", code }).message, message, code);
  }
  assert.equal(messageForHttpError(404, { detail: "Saved picks are missing." }).message, "Saved picks are missing.");
});

test("a list detail, an unknown code, or status text becomes the generic sentence", () => {
  const listBody = { detail: [{ loc: ["body", "interests"], msg: "field required", type: "missing" }] };
  const listResult = messageForHttpError(422, listBody);
  assert.equal(listResult.message, GENERIC_ERROR);
  assert.equal(listResult.specific, false);
  assert.equal(JSON.stringify(listResult).includes("field required"), false);
  assert.equal(JSON.stringify(listResult).includes("["), false);

  const unknown = messageForHttpError(400, { code: "teapot" });
  assert.equal(unknown.message, GENERIC_ERROR);
  assert.equal(unknown.message.includes("teapot"), false);
  assert.equal(unknown.message.includes("400"), false);

  assert.equal(messageForHttpError(404, null).message, GENERIC_ERROR);
  assert.equal(messageForHttpError(400, "Internal Server Error").message, GENERIC_ERROR);
});

test("a 5xx without a code is a network failure, even when detail is a string", () => {
  for (const body of [null, "Internal Server Error", { detail: "Internal Server Error" }, { detail: ["nope"] }, {}]) {
    const result = messageForHttpError(500, body);
    assert.equal(result.message, NETWORK_ERROR);
    assert.equal(result.network, true);
    assert.equal(result.message.includes("Internal Server Error"), false);
    assert.equal(result.message.includes("500"), false);
  }
});

test("a 5xx with a code shows detail, or the generic sentence when detail is missing", () => {
  assert.deepEqual(messageForHttpError(500, { detail: "The server had a problem.", code: "server_error" }), {
    message: "The server had a problem.",
    network: false,
    specific: true,
  });
  assert.equal(messageForHttpError(503, { code: "server_error" }).message, GENERIC_ERROR);
  assert.equal(messageForHttpError(500, { code: "rate_limited" }).message, GENERIC_ERROR);
  assert.equal(messageForHttpError(500, { code: "server_error" }).network, false);
});

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "Internal Server Error",
    json: async () => body,
  };
}

function textResponse(status) {
  return {
    ok: false,
    status,
    statusText: "Internal Server Error",
    json: async () => {
      throw new Error("not json");
    },
  };
}

test("request() uses the same sentences and never the status text", async (t) => {
  const original = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = original;
  });

  globalThis.fetch = async () => {
    throw new Error("connect ECONNREFUSED");
  };
  await assert.rejects(getHealth(), (err) => {
    assert.equal(err.message, NETWORK_ERROR);
    assert.equal(err.network, true);
    assert.equal(err.message.includes("ECONNREFUSED"), false);
    return true;
  });

  globalThis.fetch = async () => textResponse(500);
  await assert.rejects(getHealth(), (err) => {
    assert.equal(err.message, NETWORK_ERROR);
    assert.equal(err.network, true);
    assert.equal(err.status, 500);
    assert.equal(err.message.includes("Internal Server Error"), false);
    return true;
  });

  globalThis.fetch = async () => jsonResponse(500, { detail: "Internal Server Error" });
  await assert.rejects(getHealth(), (err) => {
    assert.equal(err.message, NETWORK_ERROR);
    assert.equal(err.network, true);
    return true;
  });

  globalThis.fetch = async () => jsonResponse(500, { detail: "Database is busy.", code: "server_error" });
  await assert.rejects(getHealth(), (err) => {
    assert.equal(err.message, "Database is busy.");
    assert.equal(err.specific, true);
    assert.equal(err.code, "server_error");
    assert.equal(err.network, false);
    return true;
  });

  globalThis.fetch = async () => jsonResponse(500, { code: "server_error" });
  await assert.rejects(getHealth(), (err) => {
    assert.equal(err.message, GENERIC_ERROR);
    assert.equal(err.specific, true);
    return true;
  });

  globalThis.fetch = async () => jsonResponse(429, { code: "rate_limited" });
  await assert.rejects(getHealth(), (err) => {
    assert.equal(err.message, CODES.rate_limited);
    assert.equal(err.network, false);
    return true;
  });

  globalThis.fetch = async () => jsonResponse(422, { detail: [{ msg: "bad" }] });
  await assert.rejects(getHealth(), (err) => {
    assert.equal(err.message, GENERIC_ERROR);
    assert.equal(err.specific, false);
    assert.equal(err.message.includes("bad"), false);
    return true;
  });
});

test("the phone client uses the same http sentences and its own missing-address line", async (t) => {
  const previous = process.env.EXPO_PUBLIC_API_URL;
  process.env.EXPO_PUBLIC_API_URL = "http://127.0.0.1:9";
  const phone = await import("../../mobile/api.js");
  t.after(() => {
    if (previous === undefined) delete process.env.EXPO_PUBLIC_API_URL;
    else process.env.EXPO_PUBLIC_API_URL = previous;
  });

  assert.equal(phone.NETWORK_ERROR, NETWORK_ERROR);
  assert.equal(phone.GENERIC_ERROR, GENERIC_ERROR);
  for (const [status, body] of [
    [500, { detail: "Internal Server Error" }],
    [500, { detail: "Database is busy.", code: "server_error" }],
    [500, { code: "server_error" }],
    [429, { code: "rate_limited" }],
    [422, { detail: [{ msg: "bad" }] }],
    [404, { detail: "User not found.", code: "not_found" }],
    [400, { code: "bad_request" }],
    [409, { code: "data_unavailable" }],
    [404, { code: "not_found" }],
  ]) {
    assert.deepEqual(phone.messageForHttpError(status, body), messageForHttpError(status, body));
  }

  const original = globalThis.fetch;
  t.after(() => {
    globalThis.fetch = original;
  });
  globalThis.fetch = async () => {
    throw new Error("failed");
  };
  await assert.rejects(phone.getHealth(), (err) => {
    assert.equal(err.message, NETWORK_ERROR);
    assert.equal(err.network, true);
    return true;
  });

  delete process.env.EXPO_PUBLIC_API_URL;
  await assert.rejects(phone.getHealth(), (err) => {
    assert.equal(
      err.message,
      "The server address isn't set. In mobile/.env, set EXPO_PUBLIC_API_URL to your Mac, then start Expo again."
    );
    return true;
  });
});
