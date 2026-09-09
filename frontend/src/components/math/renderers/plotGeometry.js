export const SVG_WIDTH = 640
export const SVG_HEIGHT = 360
export const PADDING = 36

export function createProjector(viewport) {
  const width = SVG_WIDTH - PADDING * 2
  const height = SVG_HEIGHT - PADDING * 2
  const xSpan = viewport.x_max - viewport.x_min
  const ySpan = viewport.y_max - viewport.y_min
  return {
    x: (value) => PADDING + ((value - viewport.x_min) / xSpan) * width,
    y: (value) => SVG_HEIGHT - PADDING - ((value - viewport.y_min) / ySpan) * height,
  }
}

export function pointString(points, project) {
  return points.map(([x, y]) => `${project.x(x)},${project.y(y)}`).join(' ')
}

export function ticks(min, max, count = 4) {
  return Array.from({ length: count + 1 }, (_, index) => min + ((max - min) * index) / count)
}

export function formatTick(value) {
  if (Math.abs(value) < 1e-9) return '0'
  if (Math.abs(value) >= 10000 || Math.abs(value) < 0.001) return value.toExponential(1)
  return Number(value.toFixed(2)).toString()
}
