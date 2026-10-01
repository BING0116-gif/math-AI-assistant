export function createHistory(strokes = []) {
  return { strokes, undo: [], redo: [] }
}

export function commit(history, nextStrokes) {
  return { strokes: nextStrokes, undo: [...history.undo, history.strokes], redo: [] }
}

export function undo(history) {
  if (!history.undo.length) return history
  const strokes = history.undo.at(-1)
  return { strokes, undo: history.undo.slice(0, -1), redo: [...history.redo, history.strokes] }
}

export function redo(history) {
  if (!history.redo.length) return history
  const strokes = history.redo.at(-1)
  return { strokes, undo: [...history.undo, history.strokes], redo: history.redo.slice(0, -1) }
}
