import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { registerLogoutFlush } from '@/utils/logoutFlush'
import { endLearningActivity, heartbeatLearningActivity, startLearningActivity } from '@/api/learning'

const routeContext = (path) => {
  if (path.startsWith('/chat')) return 'chat'
  if (path.startsWith('/knowledge')) return 'knowledge'
  if (path.startsWith('/apply/practice')) return 'practice'
  if (path.startsWith('/apply/assessment')) return 'assessment'
  if (path.startsWith('/apply/exam')) return 'exam'
  return null
}

export function useLearningActivity() {
  const route = useRoute()
  const auth = useAuthStore()
  let activityId = null
  let timer = null
  const stop = async () => {
    if (timer) clearInterval(timer)
    timer = null
    const id = activityId
    activityId = null
    // 会话已经清掉就不再上报：该端点要鉴权，空 Authorization 只会得到一个被吃掉的 401
    if (!id || !auth.isAuthenticated) return
    await endLearningActivity(id).catch(() => {})
  }
  const start = async () => {
    await stop()
    const contextType = routeContext(route.path)
    if (!auth.isAuthenticated || !contextType) return
    const clientId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    const { data } = await startLearningActivity({
      client_session_id: clientId, context_type: contextType,
      context_id: String(route.params.chatId || route.params.pointId || route.params.sessionId || '') || null,
    }).catch(() => ({ data: null }))
    activityId = data?.id || null
    if (activityId) timer = setInterval(() => {
      if (document.visibilityState === 'visible' && activityId) heartbeatLearningActivity(activityId, new Date().toISOString()).catch(() => {})
    }, 30000)
  }
  // 注册为登出收尾：authStore.logout() 会在 clearSession() 之前调用 stop，结束上报因此
  // 还能用上有效 token；路由跳转后的那一次 stop 已经是空 ID，不会重复发请求。
  let unregisterLogoutFlush = () => {}
  onMounted(() => {
    unregisterLogoutFlush = registerLogoutFlush(stop)
    start()
  })
  watch(() => route.fullPath, start)
  onBeforeUnmount(() => {
    unregisterLogoutFlush()
    stop()
  })
}
