import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
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
    if (id) await endLearningActivity(id).catch(() => {})
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
  onMounted(start)
  watch(() => route.fullPath, start)
  onBeforeUnmount(stop)
}
