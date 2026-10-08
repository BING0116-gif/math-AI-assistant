import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { loadFromStorage, saveToStorage } from '@/utils/storage'

const THEME_KEY = 'math_ai_theme'
const SIDEBAR_KEY = 'sidebar_collapsed'

type ThemePreference = 'light' | 'dark' | 'system'

const systemDarkQuery =
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null

/** 持久化值兜底:旧值 'light'/'dark' 直迁,'system' 合法,其余归 light */
function normalizeTheme(value: unknown): ThemePreference {
  return value === 'dark' || value === 'system' ? value : 'light'
}

export const useUiStore = defineStore('ui', () => {
  const theme = ref<ThemePreference>(normalizeTheme(loadFromStorage(THEME_KEY, 'light')))
  const sidebarCollapsed = ref(loadFromStorage(SIDEBAR_KEY, false))
  const inspectorOpen = ref(false)
  const mobileDrawerOpen = ref(false)
  // 登出流程进行中：由 useSignOut 置位，**导航落到登录页之后**才撤销。
  // 不能拿“/auth/logout 返回”当终点：那一刻会话已清、路由还没换，旧壳会闪一帧
  // 用户名空白、按钮回到空闲态的“半空壳”（实测约 160ms，本地环境可观测）。
  const signingOut = ref(false)

  function resolveTheme(t: ThemePreference): 'light' | 'dark' {
    if (t === 'system') return systemDarkQuery?.matches ? 'dark' : 'light'
    return t
  }

  function applyTheme(t: ThemePreference) {
    const resolved = resolveTheme(t)
    document.documentElement.setAttribute('data-theme', resolved)
    // Element Plus dark css-vars 以 html.dark 为激活条件(§9/§10)
    document.documentElement.classList.toggle('dark', resolved === 'dark')
    saveToStorage(THEME_KEY, t)
  }

  function onSystemChange() {
    if (theme.value === 'system') applyTheme('system')
  }

  function init() {
    applyTheme(theme.value)
    systemDarkQuery?.addEventListener?.('change', onSystemChange)
  }

  /** 循环切换:亮 → 暗 → 跟随系统 → 亮 */
  function toggleTheme() {
    const order: ThemePreference[] = ['light', 'dark', 'system']
    const next = order[(order.indexOf(theme.value) + 1) % order.length]
    theme.value = next
  }

  watch(theme, applyTheme)

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    saveToStorage(SIDEBAR_KEY, sidebarCollapsed.value)
  }

  function toggleInspector() {
    inspectorOpen.value = !inspectorOpen.value
  }

  return {
    theme,
    sidebarCollapsed,
    inspectorOpen,
    mobileDrawerOpen,
    signingOut,
    init,
    toggleTheme,
    toggleSidebar,
    toggleInspector,
  }
})
