/**
 * AI 能力状态 Composable
 *
 * 从后端 /api/health/detailed 获取 AI capability 状态，
 * 在组件中提供响应式能力判断。
 */
import { ref, computed } from 'vue'

/** 请求中的 health 缓存，避免重复请求 */
let cached = null
let cachedPromise = null

/**
 * @returns {{ enabled: boolean, configured: boolean, available: boolean, reason: string }}
 */
async function fetchCapability() {
  if (cachedPromise) return cachedPromise
  cachedPromise = (async () => {
    try {
      const res = await fetch('/api/health/detailed', { signal: AbortSignal.timeout(5000) })
      if (!res.ok) throw new Error('Health endpoint returned ' + res.status)
      const data = await res.json()
      cached = data.ai || { enabled: false, configured: false, available: false, reason: 'unknown' }
      return cached
    } catch (err) {
      cached = { enabled: false, configured: false, available: false, reason: 'unreachable' }
      return cached
    }
  })()
  return cachedPromise
}

/**
 * 提供 AI 能力状态的响应式数据。
 * 组件销毁时不自动清理，避免重复请求。
 */
export function useAiCapability() {
  const capability = ref(cached)
  const loading = ref(!cached)

  if (!cached) {
    fetchCapability().then((c) => {
      capability.value = c
      loading.value = false
    })
  } else {
    loading.value = false
  }

  const isAiAvailable = computed(() => capability.value?.available === true)
  const aiReason = computed(() => {
    if (!capability.value) return ''
    const map = {
      enabled: '',
      disabled_by_config: 'AI 功能已被管理员关闭',
      missing_api_key: 'AI 服务未配置 API 密钥',
      unknown: 'AI 状态未知',
      unreachable: '无法连接到服务器',
    }
    return map[capability.value.reason] || 'AI 功能当前不可用'
  })
  const aiEnabled = computed(() => capability.value?.enabled === true)
  const aiConfigured = computed(() => capability.value?.configured === true)

  /** 手动刷新 */
  async function refresh() {
    cachedPromise = null
    cached = null
    loading.value = true
    const c = await fetchCapability()
    capability.value = c
    loading.value = false
  }

  return {
    capability,
    loading,
    isAiAvailable,
    aiReason,
    aiEnabled,
    aiConfigured,
    refresh,
  }
}