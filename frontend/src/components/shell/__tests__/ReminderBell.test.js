/**
 * 顶栏铃铛（ReminderBell）契约测试。
 *
 * 这里保护的是最容易漂移的三处：角标数字来自服务端 counts、
 * 错题级项的"稍后提醒"必须真的禁用（而不是点了没反应），
 * 以及每条提醒的跳转必须复用后端下发的 action（前端不再自己拼深链）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const { push, learningApi } = vi.hoisted(() => ({
  push: vi.fn(),
  learningApi: { getReminders: vi.fn(), deferReview: vi.fn() },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }))
vi.mock('@/api/learning', () => learningApi)

const ReminderBell = (await import('@/components/shell/ReminderBell.vue')).default
const { useReminderStore } = await import('@/stores/reminderStore')
const { useAuthStore } = await import('@/stores/authStore')

const ITEMS = [
  { key: 'review_schedule:1', bucket: 'overdue', source: 'knowledge_point', schedule_id: 1, knowledge_point_code: 'LIMIT', title: '复习 数列极限', hint: '逾期 3 天', can_defer: true, action: { route: '/knowledge', query: { point: 'LIMIT' } } },
  { key: 'error_review:7', bucket: 'today', source: 'error_item', schedule_id: null, error_item_id: 'err-7', title: '重练错题 数列极限', hint: '今日到期', can_defer: false, defer_disabled_reason: '错题复习节奏由错题本自动排期，暂不支持单独稍后提醒', action: { route: '/error-book/err-7', query: {} } },
  { key: 'review_schedule:3', bucket: 'upcoming', source: 'knowledge_point', schedule_id: 3, knowledge_point_code: 'SERIES', title: '复习 级数', hint: '6 小时后到期', can_defer: true, action: { route: '/knowledge', query: { point: 'SERIES' } } },
]

function reminderPayload() {
  return {
    data: {
      generated_at: '2024-05-10T12:00:00Z',
      version: 'reminders-derived-v1',
      counts: { overdue: 1, today: 1, upcoming: 1, total: 3 },
      items: ITEMS,
      primary: { id: 'review:LIMIT', title: '数列极限', start: { route: '/apply/practice', query: { knowledge_point: 'LIMIT' } } },
    },
  }
}

function mountBell() {
  return mount(ReminderBell, {
    global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
  })
}

describe('ReminderBell', () => {
  let store

  beforeEach(async () => {
    setActivePinia(createPinia())
    for (const mock of Object.values(learningApi)) mock.mockReset()
    push.mockReset()
    localStorage.clear()
    localStorage.setItem('auth_token', 't1')
    localStorage.setItem('current_user', JSON.stringify({ user_id: 'u1', username: 'u1' }))
    useAuthStore().restoreSession()
    store = useReminderStore()
    learningApi.getReminders.mockResolvedValue(reminderPayload())
    await store.fetch()
  })

  it('shows the server-derived badge and nothing until opened', async () => {
    const wrapper = mountBell()
    expect(wrapper.find('.bell-count').text()).toBe('2')
    expect(wrapper.find('.bell-panel').exists()).toBe(false)
    expect(wrapper.get('.bell-btn').attributes('title')).toContain('2 条复习提醒')
  })

  it('opens the panel, honours the fetch debounce, and refreshes once stale', async () => {
    const wrapper = mountBell()
    learningApi.getReminders.mockClear()
    await wrapper.get('.bell-btn').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.panel-list .panel-row').length).toBe(3)
    expect(wrapper.get('.panel-foot').text()).toContain('逾期 1')
    // 刚在 beforeEach 里拉过：去抖窗口内开面板不得再发请求
    expect(learningApi.getReminders).not.toHaveBeenCalled()
    await wrapper.get('.bell-btn').trigger('click')
    await flushPromises()
    expect(learningApi.getReminders).not.toHaveBeenCalled()
    // 数据过期后再开，只补一次
    store.lastFetchedAt = 0
    await wrapper.get('.bell-btn').trigger('click')
    await wrapper.get('.bell-btn').trigger('click')
    await flushPromises()
    expect(learningApi.getReminders).toHaveBeenCalledTimes(1)
  })

  it('navigates with the action payload handed back by the server', async () => {
    const wrapper = mountBell()
    await wrapper.get('.bell-btn').trigger('click')
    await flushPromises()
    const rows = wrapper.findAll('.row-main')
    await rows[0].trigger('click')
    expect(push).toHaveBeenLastCalledWith({ path: '/knowledge', query: { point: 'LIMIT' } })
    await rows[1].trigger('click')
    expect(push).toHaveBeenLastCalledWith({ path: '/error-book/err-7', query: {} })
    // 面板跳转后自动收起
    expect(wrapper.find('.bell-panel').exists()).toBe(false)
  })

  it('sends the today task to its own start route', async () => {
    const wrapper = mountBell()
    await wrapper.get('.bell-btn').trigger('click')
    await flushPromises()
    await wrapper.get('.panel-primary').trigger('click')
    expect(push).toHaveBeenCalledWith({ path: '/apply/practice', query: { knowledge_point: 'LIMIT' } })
  })

  it('disables 稍后提醒 on error-item rows and explains why', async () => {
    const wrapper = mountBell()
    await wrapper.get('.bell-btn').trigger('click')
    await flushPromises()
    const deferButtons = wrapper.findAll('.row-defer')
    expect(deferButtons[0].attributes('disabled')).toBeUndefined()
    expect(deferButtons[1].attributes('disabled')).toBeDefined()
    expect(deferButtons[1].attributes('title')).toContain('错题本自动排期')
    learningApi.deferReview.mockResolvedValue({ data: {} })
    await deferButtons[1].trigger('click')
    await flushPromises()
    expect(learningApi.deferReview).not.toHaveBeenCalled()
    await deferButtons[0].trigger('click')
    await flushPromises()
    expect(learningApi.deferReview).toHaveBeenCalledTimes(1)
    expect(learningApi.deferReview.mock.calls[0][0]).toBe(1)
  })

  it('renders an empty state instead of a stale badge when nothing is due', async () => {
    learningApi.getReminders.mockResolvedValue({
      data: { counts: { overdue: 0, today: 0, upcoming: 0, total: 0 }, items: [], primary: null },
    })
    store.reset()
    await store.fetch({ force: true })
    const wrapper = mountBell()
    expect(wrapper.find('.bell-count').exists()).toBe(false)
    await wrapper.get('.bell-btn').trigger('click')
    await flushPromises()
    expect(wrapper.get('.panel-empty').text()).toContain('暂时没有到期的复习')
    expect(wrapper.find('.panel-primary').exists()).toBe(false)
  })
})
