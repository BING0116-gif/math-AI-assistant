function drawStroke(context, stroke) {
  if (stroke.points.length < 2) return
  context.strokeStyle = stroke.color
  context.lineCap = 'round'; context.lineJoin = 'round'
  for (let i = 1; i < stroke.points.length; i += 1) {
    const previous = stroke.points[i - 1], point = stroke.points[i]
    context.beginPath(); context.lineWidth = stroke.width * (0.35 + point.pressure * 0.65)
    context.moveTo(previous.x, previous.y); context.lineTo(point.x, point.y)
    context.stroke()
  }
}
export function renderCanvas(canvas, strokes, viewport) {
  const rect = canvas.getBoundingClientRect(), ratio = window.devicePixelRatio || 1
  canvas.width = rect.width * ratio; canvas.height = rect.height * ratio
  const context = canvas.getContext('2d'); context.scale(ratio, ratio)
  context.clearRect(0, 0, rect.width, rect.height)
  context.save(); context.translate(viewport.x, viewport.y); context.scale(viewport.scale, viewport.scale)
  strokes.forEach((stroke) => drawStroke(context, stroke)); context.restore()
}
