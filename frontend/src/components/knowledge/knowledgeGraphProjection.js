export const LOCAL_POINT_LIMIT = 12

export function flattenKnowledgeTree(tree, mastery = {}) {
  const points = []
  const chapters = []

  for (const [chapterIndex, chapter] of (tree?.chapters || []).entries()) {
    const chapterPoints = []
    for (const bucket of [chapter, ...(chapter.children || [])]) {
      for (const point of (bucket.knowledge_points || [])) {
        const item = {
          ...point,
          chapterId: chapter.id,
          chapterName: chapter.name,
          sectionId: bucket.id,
          sectionName: bucket.name,
          status: mastery?.[point.code]?.status || 'untouched'
        }
        points.push(item)
        chapterPoints.push(item)
      }
    }
    chapters.push({ ...chapter, index: chapterIndex, points: chapterPoints })
  }

  return { points, chapters }
}

export function getDefaultChapterId(chapters) {
  return chapters.find(chapter => chapter.points.length)?.id || chapters[0]?.id || ''
}

export function buildLocalProjection(points, chapterId, selectedPointId, limit = LOCAL_POINT_LIMIT) {
  const byCode = new Map(points.filter(point => point.code).map(point => [point.code, point]))
  const selected = points.find(point => point.id === selectedPointId)
  const activeChapterId = selected?.chapterId || chapterId
  const local = points.filter(point => point.chapterId === activeChapterId)
  const included = new Map(local.slice(0, limit).map(point => [point.id, point]))

  for (const point of [...included.values()]) {
    for (const code of point.prerequisites || []) {
      const prerequisite = byCode.get(code)
      if (prerequisite && !included.has(prerequisite.id) && included.size < limit) {
        included.set(prerequisite.id, { ...prerequisite, isExternalPrerequisite: true })
      }
    }
  }

  if (selected && !included.has(selected.id)) included.set(selected.id, selected)
  return { activeChapterId, points: [...included.values()].slice(0, limit) }
}

export function buildGraphElements(points) {
  const byCode = new Map(points.filter(point => point.code).map(point => [point.code, point.id]))
  const nodes = points.map(point => ({ data: {
    id: point.id,
    code: point.code,
    label: point.name,
    status: point.status,
    chapterName: point.chapterName,
    external: Boolean(point.isExternalPrerequisite)
  } }))
  const edges = []
  const seen = new Set()

  for (const point of points) {
    for (const code of point.prerequisites || []) {
      const source = byCode.get(code)
      const id = `prereq:${source}->${point.id}`
      if (source && source !== point.id && !seen.has(id)) {
        seen.add(id)
        edges.push({ data: { id, source, target: point.id, kind: 'prereq' } })
      }
    }
    for (const code of point.related || []) {
      const source = byCode.get(code)
      const pair = [source, point.id].sort()
      const id = `related:${pair.join('-')}`
      if (source && source !== point.id && !seen.has(id)) {
        seen.add(id)
        edges.push({ data: { id, source, target: point.id, kind: 'related' } })
      }
    }
  }
  return { nodes, edges }
}

export function searchKnowledgePoints(points, query, limit = 8) {
  const normalized = query.trim().toLocaleLowerCase()
  if (!normalized) return []
  return points.filter(point => [point.name, point.code, ...(point.aliases || [])]
    .some(value => String(value || '').toLocaleLowerCase().includes(normalized)))
    .slice(0, limit)
}
