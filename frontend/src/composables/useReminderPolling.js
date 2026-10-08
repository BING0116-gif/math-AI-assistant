import { onBeforeUnmount, onMounted } from 'vue'
import { useReminderStore } from '@/stores/reminderStore'

/** 轮询间隔：5 分钟。刻意不做全站轮询 —— 提醒拉取走 general 限流桶，
 *  挂到每个页面会重现"预算被吃光、真实页面 429"的事故。 */
export const REMINDER_POLL_MS = 5 * 60 * 1000

/**
 * 复习提醒的拉取生命周期，只允许在首页（HomeView）与学习看板（DashboardView）调用。
 * 挂载后拉一次，之后每 5 分钟一次；标签页隐藏时跳过本轮，避免多标签页叠加请求。
 */
export function useReminderPolling() {
  const store = useReminderStore()
  let timer = null

  function tick() {
    if (typeof document !== 'undefined' && document.hidden) return
    // fetch 自带 60s 去抖与失败静默，这里不需要再包 try/catch
    store.fetch()
  }

  onMounted(() => {
    tick()
    timer = setInterval(tick, REMINDER_POLL_MS)
  })

  onBeforeUnmount(() => {
    if (timer) clearInterval(timer)
    timer = null
  })

  return { store, tick }
}
