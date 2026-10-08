/**
 * 登录冷却倒计时（423 账户锁定 / 429 限流共用）。
 *
 * 只做一件事：拿到"还要等多久"之后禁用提交按钮并逐秒递减，归零自动放开。
 * 计时器随组件卸载清理，避免路由切换后 setInterval 泄漏。
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import { formatRetryDelay } from '@/api/authErrors'

export function useLoginLock() {
  const remainingSeconds = ref(0)
  let timer = null

  const coolingDown = computed(() => remainingSeconds.value > 0)
  const countdownText = computed(() =>
    coolingDown.value ? formatRetryDelay(remainingSeconds.value) : ''
  )

  function clearLock() {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
    remainingSeconds.value = 0
  }

  function startLock(seconds) {
    const total = Math.max(1, Math.floor(Number(seconds) || 0))
    remainingSeconds.value = total
    if (timer) clearInterval(timer)
    timer = setInterval(() => {
      remainingSeconds.value -= 1
      if (remainingSeconds.value <= 0) {
        clearLock()
      }
    }, 1000)
  }

  onBeforeUnmount(clearLock)

  return { remainingSeconds, coolingDown, countdownText, startLock, clearLock }
}
