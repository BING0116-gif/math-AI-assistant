import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { loadFromStorage, saveToStorage } from '@/utils/storage'

const THEME_KEY = 'math_ai_theme'
const SIDEBAR_KEY = 'sidebar_collapsed'

export const useUiStore = defineStore('ui', () => {
  const theme = ref<'light' | 'dark'>(loadFromStorage(THEME_KEY, 'light'))
  const sidebarCollapsed = ref(loadFromStorage(SIDEBAR_KEY, false))
  const inspectorOpen = ref(false)
  const mobileDrawerOpen = ref(false)

  function init() {
    applyTheme(theme.value)
  }

  function toggleTheme() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }

  function applyTheme(t: 'light' | 'dark') {
    document.documentElement.setAttribute('data-theme', t)
    saveToStorage(THEME_KEY, t)
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
    init,
    toggleTheme,
    toggleSidebar,
    toggleInspector,
  }
})