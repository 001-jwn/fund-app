// Release decision for a card swipe SwipeableCard has already claimed.
// dx is the finger's horizontal travel in points.
// vx is PanResponder's horizontal velocity in points per millisecond.
// width is the card width in points (the screen width is a fine stand-in).
// Vertical travel is not an input. The |dx| > |dy| check is only for claiming
// the gesture. settle() calls swipeDecision and does not re-check it.

export const SWIPE_DISTANCE_FRACTION = 0.25;
export const SWIPE_FLICK_VELOCITY = 0.5;
export const SWIPE_MIN_FLICK_DISTANCE = 24;

export function swipeDecision(dx, vx, width) {
  if (!Number.isFinite(dx) || !Number.isFinite(vx) || !Number.isFinite(width) || width <= 0) {
    return "";
  }
  const distance = Math.abs(dx);
  if (distance === 0) return "";
  const direction = dx > 0 ? "like" : "dislike";
  if (distance >= width * SWIPE_DISTANCE_FRACTION) return direction;
  const movingSameWay = (dx > 0 && vx > 0) || (dx < 0 && vx < 0);
  if (
    movingSameWay &&
    distance >= SWIPE_MIN_FLICK_DISTANCE &&
    Math.abs(vx) >= SWIPE_FLICK_VELOCITY
  ) {
    return direction;
  }
  return "";
}

// Still-horizontal gate. A drag that is not mostly horizontal does not commit
// through this function. SwipeableCard does not call it from settle(): once
// the gesture is claimed, release and terminate use swipeDecision so a later
// vertical drift can still like or dislike.
export function horizontalSwipeAction(dx, dy, vx, width) {
  if (!Number.isFinite(dx) || !Number.isFinite(dy)) return "";
  if (!(Math.abs(dx) > Math.abs(dy))) return "";
  return swipeDecision(dx, vx, width);
}
