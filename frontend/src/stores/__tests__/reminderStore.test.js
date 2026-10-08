/**
 * 提醒中心 store 回归测试。
 *
 * 锁住三条真实约束（都是这个功能最容易退化的地方）：
 * - 失败静默：提醒拉不到绝不能影响主流程，也不能留下上一次的错误角标；
 * - 60s 去抖：面板反复打开 / 轮询叠加时不得形成请求风暴；
 * - 账号隔离：数据绑定 ownerId，切换账号后旧提醒立刻不可见。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const learningApi = {
  getReminders: vi.fn(),
  deferReview: vi.fn(),
}
vi.mock('@/api/learning', () => learningApi)

const { useReminderStore, DEFAULT_DEFER_HOURS, FETCH_DEBOUNCE_MS } = await import('../reminderStore')
const { useAuthStore } = await import('../authStore')

function payload(overrides = {}) {
  return {
    data: {
      generated_at: '2024-05-10T12:00:00Z',
      version: 'reminders-derived-v1',
      counts: { overdue: 2, today: 1, upcoming: 3, total: 6 },
      items: [
        { key: 'review_schedule:1', bucket: 'overdue', source: 'knowledge_point', schedule_id: 1, knowledge_point_code: 'LIMIT', title: '复习 数列极限', hint: '逾期 3 天', can_defer: true },
        { key: 'review_schedule:2', bucket: 'today', source: 'knowledge_point', schedule_id: 2, knowledge_point_code: 'CONT', title: '复习 连续函数', hint: '今日到期', can_defer: true },
        { key: 'error_review:7', bucket: 'today', source: 'error_item', schedule_id: null, error_item_id: 'err-7', title: '重练错题 数列极限', hint: '今日到期', can_defer: false, defer_disabled_reason: '错题复习节奏由错题本自动排期，暂不支持单独稍后提醒' },
        { key: 'review_schedule:3', bucket: 'upcoming', source: 'knowledge_point', schedule_id: 3, knowledge_point_code: 'SERIES', title: '复习 级数', hint: '6 小时后到期', can_defer: true },
      ],
      primary: { id: 'review:LIMIT', title: '数列极限', start: { route: '/apply/practice', query: { knowledge_point: 'LIMIT' } } },
      ...overrides,
    },
  }
}

describe('reminderStore', () => {
  let store
  let auth

  beforeEach(() => {
    setActivePinia(createPinia())
    for (const mock of Object.values(learningApi)) mock.mockReset()
    localStorage.clear()
    localStorage.setItem('auth_token', 't1')
    localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
    auth = useAuthStore()
    auth.restoreSession()
    store = useReminderStore()
    learningApi.getReminders.mockResolvedValue(payload())
  })

  it('loads server counts and derives the badge from overdue + today only', async () => {
    expect(await store.fetch()).toBe(true)
    expect(store.badge).toBe(3)
    expect(store.counts.total).toBe(6)
    expect(store.primary.id).toBe('review:LIMIT')
    // 面板只列紧迫项（最多 5 条）与即将到期（最多 3 条），upcoming 不进角标
    expect(store.urgent.map(item => item.key)).toEqual(['review_schedule:1', 'review_schedule:2', 'error_review:7'])
    expect(store.upcoming.map(item => item.key)).toEqual(['review_schedule:3'])
  })

  it('debounces repeat fetches inside the window but honours force', async () => {
    await store.fetch()
    await store.fetch()
    await store.fetch()
    expect(learningApi.getReminders).toHaveBeenCalledTimes(1)
    expect(await store.fetch({ force: true })).toBe(true)
    expect(learningApi.getReminders).toHaveBeenCalledTimes(2)
    expect(FETCH_DEBOUNCE_MS).toBeGreaterThanOrEqual(60_000)
  })

  it('stays silent on failure and keeps the bell usable', async () => {
    learningApi.getReminders.mockRejectedValue({ response: { status: 429 } })
    expect(await store.fetch()).toBe(false)
    expect(store.lastError).toContain('429')
    expect(store.badge).toBe(0)
    expect(store.urgent).toEqual([])
  })

  it('does not request anything while logged out, and clears state', async () => {
    auth.clearSession()
    expect(await store.fetch()).toBe(false)
    expect(learningApi.getReminders).not.toHaveBeenCalled()
    expect(store.lastError).toBe('')
  })

  it('hides the previous account\'s reminders after switching users', async () => {
    await store.fetch()
    expect(store.badge).toBe(3)
    // 切换账号后即便这一次拉取失败（离线/429），旧数据也不得继续显示
    auth.currentUser = { user_id: 'u2', username: 'u2' }
    learningApi.getReminders.mockRejectedValue({ response: { status: 500 } })
    await store.fetch({ force: true })
    expect(store.badge).toBe(0)
    expect(store.urgent).toEqual([])
    expect(store.upcoming).toEqual([])
    expect(store.hasData).toBe(false)
  })

  it('defers through the server endpoint with a replay-safe idempotency key', async () => {
    await store.fetch()
    learningApi.deferReview.mockResolvedValue({ data: { id: 1 } })
    const item = store.urgent[0]
    expect(await store.defer(item)).toBe(true)
    const [scheduleId, hours, key] = learningApi.deferReview.mock.calls[0]
    expect(scheduleId).toBe(1)
    expect(hours).toBe(DEFAULT_DEFER_HOURS)
    // 键内含分钟粒度的时间桶：同一分钟连点会命中服务端幂等回放
    expect(key).toMatch(/^defer-1-\d+$/)
    // defer 之后必须回读服务端真值（分档是派生结果，不做乐观猜测）
    expect(learningApi.getReminders).toHaveBeenCalledTimes(2)
  })

  it('refuses to defer an error-item reminder instead of faking success', async () => {
    await store.fetch()
    const errorItem = store.urgent.find(item => item.source === 'error_item')
    expect(errorItem.can_defer).toBe(false)
    expect(await store.defer(errorItem)).toBe(false)
    expect(learningApi.deferReview).not.toHaveBeenCalled()
    expect(errorItem.defer_disabled_reason).toContain('错题本')
  })

  it('reports a defer failure without throwing it at the caller', async () => {
    await store.fetch()
    learningApi.deferReview.mockRejectedValue({ response: { data: { detail: { message: '复习计划不存在' } } } })
    expect(await store.defer(store.urgent[0])).toBe(false)
    expect(store.lastError).toBe('复习计划不存在')
    expect(store.deferring).toBe('')
  })
})
