/**
 * 提醒中心 Store（站内复习到期提醒）
 *
 * 数据源是后端派生聚合端点 GET /api/learning/reminders（不建通知表、不落 localStorage），
 * 因此这里必须守住三条约束：
 * 1. 拉取失败一律静默 —— 提醒是增值信息，任何情况下不得打断聊天/错题本等主流程；
 * 2. 60s 去抖 + 仅 Home/Dashboard 轮询 —— 全站轮询会重现"限流预算被吃光"的事故；
 * 3. 数据绑定 ownerId —— 切换账号后旧用户的提醒必须立刻不可见（哪怕这一次拉取失败）。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as learningApi from '@/api/learning'
import { useAuthStore } from '@/stores/authStore'

export const FETCH_DEBOUNCE_MS = 60_000
export const DEFAULT_DEFER_HOURS = 24

export const useReminderStore = defineStore('reminders', () => {
  const counts = ref({ overdue: 0, today: 0, upcoming: 0, total: 0 })
  const items = ref([])
  const primary = ref(null)
  const loading = ref(false)
  const deferring = ref('')
  const lastFetchedAt = ref(0)
  const lastError = ref('')
  const ownerId = ref('')

  const auth = useAuthStore()
  // 归属校验发生在读取端，而不是只依赖"下一次拉取会覆盖"：
  // 拉取可能失败（离线/429），此时旧数据绝不能继续显示给新账号。
  const owned = computed(() => !!ownerId.value && ownerId.value === auth.userId)

  const badge = computed(() => (owned.value ? counts.value.overdue + counts.value.today : 0))
  const urgent = computed(() => (owned.value
    ? items.value.filter(item => item.bucket === 'overdue' || item.bucket === 'today').slice(0, 5)
    : []))
  const upcoming = computed(() => (owned.value
    ? items.value.filter(item => item.bucket === 'upcoming').slice(0, 3)
    : []))
  const hasData = computed(() => owned.value && lastFetchedAt.value > 0)

  function reset() {
    counts.value = { overdue: 0, today: 0, upcoming: 0, total: 0 }
    items.value = []
    primary.value = null
    lastFetchedAt.value = 0
    lastError.value = ''
    ownerId.value = ''
  }

  /**
   * 拉取提醒。force 可越过 60s 去抖（仅用于 defer 之后回读服务端真值）。
   * @returns {Promise<boolean>} 是否真正刷新了数据
   */
  async function fetch({ force = false } = {}) {
    if (loading.value) return false
    if (!auth.userId) {
      reset()
      return false
    }
    if (!force && Date.now() - lastFetchedAt.value < FETCH_DEBOUNCE_MS) return false
    loading.value = true
    try {
      const { data } = await learningApi.getReminders()
      counts.value = data.counts || { overdue: 0, today: 0, upcoming: 0, total: 0 }
      items.value = Array.isArray(data.items) ? data.items : []
      primary.value = data.primary || null
      ownerId.value = auth.userId
      lastFetchedAt.value = Date.now()
      lastError.value = ''
      return true
    } catch (err) {
      // 静默：只记录状态码供面板显示一行 muted 文案，不弹 toast、不抛出。
      lastError.value = err?.response?.status ? `提醒暂不可用（${err.response.status}）` : '提醒暂不可用'
      return false
    } finally {
      loading.value = false
    }
  }

  /**
   * 稍后提醒：复用服务端 defer_review（deferred_until + 幂等键），本地不造状态。
   * 幂等键按分钟粒度生成 —— 同一分钟内的连点/重试由服务端回放原结果，
   * 而"真的想再延后一次"（下一分钟）不会被误判成 IDEMPOTENCY_CONFLICT。
   */
  async function defer(item, hours = DEFAULT_DEFER_HOURS) {
    if (!item || !item.can_defer || !item.schedule_id || deferring.value) return false
    const key = `defer-${item.schedule_id}-${Math.floor(Date.now() / 60_000)}`
    deferring.value = item.key
    try {
      await learningApi.deferReview(item.schedule_id, hours, key)
      // 回读服务端真值：分档（overdue/today/upcoming）是派生结果，不做乐观猜测。
      await fetch({ force: true })
      return true
    } catch (err) {
      lastError.value = err?.response?.data?.detail?.message || '稍后提醒失败，请稍后再试'
      return false
    } finally {
      deferring.value = ''
    }
  }

  return {
    counts, items, primary, loading, deferring, lastFetchedAt, lastError, ownerId,
    badge, urgent, upcoming, hasData,
    fetch, defer, reset,
  }
})
