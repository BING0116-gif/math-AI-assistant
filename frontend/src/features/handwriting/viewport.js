export const defaultViewport = () => ({ x: 0, y: 0, scale: 1 })

export function pan(viewport, dx, dy) {
  return { ...viewport, x: viewport.x + dx, y: viewport.y + dy }
}

export function pinch(viewport, previous, current) {
  const previousDistance = Math.hypot(previous.b.x - previous.a.x, previous.b.y - previous.a.y)
  const currentDistance = Math.hypot(current.b.x - current.a.x, current.b.y - current.a.y)
  if (!previousDistance || !currentDistance) return viewport
  const scale = Math.max(0.25, Math.min(4, viewport.scale * currentDistance / previousDistance))
  const oldCenter = { x: (previous.a.x + previous.b.x) / 2, y: (previous.a.y + previous.b.y) / 2 }
  const newCenter = { x: (current.a.x + current.b.x) / 2, y: (current.a.y + current.b.y) / 2 }
  return { scale, x: newCenter.x - (oldCenter.x - viewport.x) * (scale / viewport.scale), y: newCenter.y - (oldCenter.y - viewport.y) * (scale / viewport.scale) }
}
