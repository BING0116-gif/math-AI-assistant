import Konva from 'konva'

export function renderKonva(container, strokes, viewport) {
  const width = container.clientWidth, height = container.clientHeight
  const stage = new Konva.Stage({ container, width, height })
  const layer = new Konva.Layer({ x: viewport.x, y: viewport.y, scaleX: viewport.scale, scaleY: viewport.scale })
  strokes.forEach((stroke) => layer.add(new Konva.Line({ points: stroke.points.flatMap((point) => [point.x, point.y]), stroke: stroke.color, strokeWidth: stroke.width, lineCap: 'round', lineJoin: 'round', listening: false })))
  stage.add(layer)
  return stage
}
