import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const assessmentApi = { readiness: vi.fn(), create: vi.fn() }
let streamEvents
vi.mock('@/api/assessment', () => ({
  assessmentApi,
  unwrapAssessment: (response) => response?.data?.data ?? response?.data,
  previewBlueprintStream: vi.fn(async (payload, handlers) => {
    streamEvents = { payload, handlers }
    for (const [event, data] of [
      ['meta', { planning_source: 'llm', model: 'qwen', total: 5 }],
      ['bucket', { quota_kind: 'weakness', knowledge_point_code: 'limit', count: 3, reason: '薄弱' }],
      ['bucket', { quota_kind: 'due_review', knowledge_point_code: 'deriv', count: 2, reason: '到期' }],
      ['done', { total: 5, planning_source: 'llm', quota_summary: { weakness: 3, due_review: 2 } }],
    ]) handlers.onEvent(event, data)
  }),
}))

const { useAssessmentStore } = await import('../assessmentStore')

describe('assessment blueprint preview §5.4', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    assessmentApi.create.mockReset()
  })

  it('streams meta/buckets progressively and marks done', async () => {
    const store = useAssessmentStore()
    store.readiness = { course_id: 'c1', version_id: 'v1' }
    store.config.goal = 'weakness_check'
    await store.previewBlueprint()
    expect(store.blueprint.streaming).toBe(false)
    expect(store.blueprint.done).toBe(true)
    expect(store.blueprint.meta.planning_source).toBe('llm')
    expect(store.blueprint.buckets.map((bucket) => bucket.count)).toEqual([3, 2])
    expect(streamEvents.payload.course_id).toBe('c1')
    // 流式期间 streaming 状态：meta 到达后仍在接收
    expect(store.blueprint.buckets.every((bucket) => bucket.original_count === bucket.count)).toBe(true)
  })

  it('clamps bucket adjustment to ±2 and floor of 1', () => {
    const store = useAssessmentStore()
    store.$patch(({ blueprint }) => {
      blueprint.done = true
      blueprint.buckets = [
        { quota_kind: 'weakness', knowledge_point_code: 'limit', count: 3, original_count: 3, adjust: 0 },
        { quota_kind: 'due_review', knowledge_point_code: 'deriv', count: 1, original_count: 1, adjust: 0 },
      ]
    })
    store.adjustBucket(0, 1); store.adjustBucket(0, 1); store.adjustBucket(0, 1)
    expect(store.blueprint.buckets[0].count).toBe(5) // 3 + 2，第三次被 ±2 限制拦截
    store.adjustBucket(1, -1)
    expect(store.blueprint.buckets[1].count).toBe(1) // 下限 1
    store.adjustBucket(1, -1); store.adjustBucket(1, -1)
    expect(store.blueprint.buckets[1].count).toBe(1)
    store.removeBucket(1)
    expect(store.blueprint.buckets).toHaveLength(1)
  })

  it('sends adjusted buckets on create and syncs question_count', async () => {
    const store = useAssessmentStore()
    store.readiness = { course_id: 'c1', version_id: 'v1' }
    store.$patch(({ blueprint }) => {
      blueprint.done = true
      blueprint.buckets = [
        { quota_kind: 'weakness', knowledge_point_code: 'limit', count: 5, original_count: 3, adjust: 2, difficulty_min: 1, difficulty_max: 5, reason_code: 'weak_mastery', reason: '薄弱' },
      ]
    })
    assessmentApi.create.mockResolvedValue({ data: { data: { session_id: 'a1' } } })
    await store.create()
    const payload = assessmentApi.create.mock.calls[0][0]
    expect(payload.blueprint_buckets).toEqual([
      { quota_kind: 'weakness', knowledge_point_code: 'limit', count: 5, difficulty_min: 1, difficulty_max: 5, reason_code: 'weak_mastery', reason: '薄弱' },
    ])
    expect(payload.question_count).toBe(5)
  })

  it('degrades to quick mode when stream errors', async () => {
    const { previewBlueprintStream } = await import('@/api/assessment')
    previewBlueprintStream.mockRejectedValueOnce(new Error('network down'))
    const store = useAssessmentStore()
    store.readiness = { course_id: 'c1', version_id: 'v1' }
    await expect(store.previewBlueprint()).rejects.toThrow('network down')
    expect(store.blueprint.streaming).toBe(false)
    expect(store.blueprint.error).toContain('network down')
  })
})
