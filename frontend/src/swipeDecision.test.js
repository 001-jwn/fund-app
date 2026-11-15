import assert from "node:assert/strict";
import test from "node:test";
import {
  SWIPE_DISTANCE_FRACTION,
  SWIPE_FLICK_VELOCITY,
  SWIPE_MIN_FLICK_DISTANCE,
  swipeDecision,
} from "../../mobile/swipeDecision.js";

// 360pt card: a quarter is exactly 90pt. 0.25 is a dyadic rational, so this is exact.
const CARD_WIDTH = 360;
const DISTANCE = CARD_WIDTH * SWIPE_DISTANCE_FRACTION;

test("thresholds are a quarter of the card plus a flick past a short dead zone", () => {
  assert.equal(SWIPE_DISTANCE_FRACTION, 0.25);
  assert.equal(SWIPE_FLICK_VELOCITY, 0.5);
  assert.equal(SWIPE_MIN_FLICK_DISTANCE, 24);
  assert.equal(DISTANCE, 90);
});

test("a normal distance swipe right likes and left dislikes", () => {
  assert.equal(swipeDecision(140, 0.1, CARD_WIDTH), "like");
  assert.equal(swipeDecision(-140, -0.1, CARD_WIDTH), "dislike");
  assert.equal(swipeDecision(140, 0, CARD_WIDTH), "like");
  assert.equal(swipeDecision(-140, 0, CARD_WIDTH), "dislike");
});

test("a fast short flick right likes and left dislikes", () => {
  assert.equal(swipeDecision(40, 0.8, CARD_WIDTH), "like");
  assert.equal(swipeDecision(-40, -0.9, CARD_WIDTH), "dislike");
});

test("a slow short drag does not like or dislike", () => {
  assert.equal(swipeDecision(40, 0.1, CARD_WIDTH), "");
  assert.equal(swipeDecision(-50, -0.05, CARD_WIDTH), "");
  assert.equal(swipeDecision(DISTANCE - 0.001, 0, CARD_WIDTH), "");
});

test("tiny jitter does not count even when velocity is high", () => {
  assert.equal(swipeDecision(8, 3, CARD_WIDTH), "");
  assert.equal(swipeDecision(-10, -4, CARD_WIDTH), "");
  assert.equal(swipeDecision(SWIPE_MIN_FLICK_DISTANCE - 0.001, 2, CARD_WIDTH), "");
  assert.equal(swipeDecision(-(SWIPE_MIN_FLICK_DISTANCE - 0.001), -2, CARD_WIDTH), "");
});

test("exact distance boundary commits and the point just below it does not", () => {
  assert.equal(swipeDecision(DISTANCE, 0, CARD_WIDTH), "like");
  assert.equal(swipeDecision(-DISTANCE, 0, CARD_WIDTH), "dislike");
  assert.equal(swipeDecision(DISTANCE - 0.001, 0, CARD_WIDTH), "");
  assert.equal(swipeDecision(-(DISTANCE - 0.001), 0, CARD_WIDTH), "");
});

test("exact flick boundary commits and the point just below it does not", () => {
  assert.equal(swipeDecision(SWIPE_MIN_FLICK_DISTANCE, SWIPE_FLICK_VELOCITY, CARD_WIDTH), "like");
  assert.equal(
    swipeDecision(-SWIPE_MIN_FLICK_DISTANCE, -SWIPE_FLICK_VELOCITY, CARD_WIDTH),
    "dislike"
  );
  assert.equal(
    swipeDecision(SWIPE_MIN_FLICK_DISTANCE, SWIPE_FLICK_VELOCITY - 0.001, CARD_WIDTH),
    ""
  );
  assert.equal(
    swipeDecision(-SWIPE_MIN_FLICK_DISTANCE, -(SWIPE_FLICK_VELOCITY - 0.001), CARD_WIDTH),
    ""
  );
  assert.equal(swipeDecision(SWIPE_MIN_FLICK_DISTANCE - 0.001, SWIPE_FLICK_VELOCITY, CARD_WIDTH), "");
  assert.equal(
    swipeDecision(-(SWIPE_MIN_FLICK_DISTANCE - 0.001), -SWIPE_FLICK_VELOCITY, CARD_WIDTH),
    ""
  );
});

test("a short move whose velocity points the other way is not a flick", () => {
  assert.equal(swipeDecision(40, -1.5, CARD_WIDTH), "");
  assert.equal(swipeDecision(-40, 1.5, CARD_WIDTH), "");
});

test("a release past the distance line still counts when velocity has reversed", () => {
  assert.equal(swipeDecision(DISTANCE, -1, CARD_WIDTH), "like");
  assert.equal(swipeDecision(-DISTANCE, 1, CARD_WIDTH), "dislike");
});

test("a tap, a zero-width card, and non-finite input do nothing", () => {
  assert.equal(swipeDecision(0, 2, CARD_WIDTH), "");
  assert.equal(swipeDecision(0, 0, CARD_WIDTH), "");
  assert.equal(swipeDecision(200, 1, 0), "");
  assert.equal(swipeDecision(200, 1, -360), "");
  assert.equal(swipeDecision(Number.NaN, 1, CARD_WIDTH), "");
  assert.equal(swipeDecision(200, Number.NaN, CARD_WIDTH), "");
  assert.equal(swipeDecision(200, 0, Number.POSITIVE_INFINITY), "");
});
