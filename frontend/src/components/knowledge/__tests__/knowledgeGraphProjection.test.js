import { describe, expect, it } from 'vitest'
import { buildGraphElements, buildLocalProjection, flattenKnowledgeTree, searchKnowledgePoints } from '../knowledgeGraphProjection'

const tree = {
  chapters: [
    { id: 'chapter-a', name: '函数', children: [{ id: 'section-a', name: '基础', knowledge_points: [
      { id: 'p1', code: 'FUNC-01', name: '函数概念', aliases: ['映射'], prerequisites: [], related: [] },
      { id: 'p2', code: 'FUNC-02', name: '复合函数', prerequisites: ['FUNC-01'], related: [] }
    ] }] },
    { id: 'chapter-b', name: '极限', children: [{ id: 'section-b', name: '极限基础', knowledge_points: [
      { id: 'p3', code: 'LIMIT-01', name: '数列极限', prerequisites: ['FUNC-02'], related: ['FUNC-01'] }
    ] }] }
  ]
}

describe('knowledge graph projection', () => {
  it('flattens chapter ownership and preserves server mastery evidence', () => {
    const result = flattenKnowledgeTree(tree, { 'FUNC-01': { status: 'mastered' } })
    expect(result.points).toHaveLength(3)
    expect(result.points[0]).toMatchObject({ chapterId: 'chapter-a', status: 'mastered' })
    expect(result.points[1].status).toBe('untouched')
  })

  it('preserves the server locked state instead of recomputing prerequisites in the browser', () => {
    const result = flattenKnowledgeTree(tree, { 'FUNC-02': { status: 'locked', missing_prerequisites: ['FUNC-01'] } })
    expect(result.points[1].status).toBe('locked')
  })

  it('shows only the active chapter plus a necessary cross-chapter prerequisite', () => {
    const { points } = flattenKnowledgeTree(tree)
    const projection = buildLocalProjection(points, 'chapter-b', '', 18)
    expect(projection.points.map(point => point.id)).toEqual(['p3', 'p2'])
    expect(projection.points[1].isExternalPrerequisite).toBe(true)
  })

  it('caps an explicitly requested local graph at 18 readable nodes', () => {
    const points = Array.from({ length: 25 }, (_, index) => ({ id: `p${index}`, code: `P-${index}`, name: `知识点 ${index}`, chapterId: 'chapter' }))
    expect(buildLocalProjection(points, 'chapter', '', 18).points).toHaveLength(18)
  })

  it('builds solid prerequisite and dashed related edge semantics without duplicates', () => {
    const { points } = flattenKnowledgeTree(tree)
    const graph = buildGraphElements(points)
    expect(graph.edges.map(edge => edge.data.kind)).toEqual(['prereq', 'prereq', 'related'])
  })

  it('searches names, stable codes, and aliases', () => {
    const { points } = flattenKnowledgeTree(tree)
    expect(searchKnowledgePoints(points, '映射')[0].id).toBe('p1')
    expect(searchKnowledgePoints(points, 'limit-01')[0].id).toBe('p3')
  })
})
