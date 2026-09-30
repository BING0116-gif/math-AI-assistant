export function toInkPoint(event, bounds) {
  return {
    x: event.clientX - bounds.left,
    y: event.clientY - bounds.top,
    pressure: Number.isFinite(event.pressure) ? event.pressure : 0.5,
    timestamp: Number.isFinite(event.timeStamp) ? event.timeStamp : Date.now(),
    tiltX: Number.isFinite(event.tiltX) ? event.tiltX : 0,
    tiltY: Number.isFinite(event.tiltY) ? event.tiltY : 0,
  }
}

export function collectInkPoints(event, bounds) {
  const events = typeof event.getCoalescedEvents === 'function' ? event.getCoalescedEvents() : []
  return (events.length ? events : [event]).map((item) => toInkPoint(item, bounds))
}

export function createStroke(event, point, color = '#172554', width = 3) {
  return { id: crypto.randomUUID(), pointerId: event.pointerId, pointerType: event.pointerType, color, width, points: [point] }
}

export function strokeHitsPoint(stroke, point, radius) {
  return stroke.points.some((sample) => Math.hypot(sample.x - point.x, sample.y - point.y) <= radius + stroke.width / 2)
}
