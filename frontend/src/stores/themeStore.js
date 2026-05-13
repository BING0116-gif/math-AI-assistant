import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { loadFromStorage, saveToStorage } from '@/utils/storage'

const THEME_KEY = 'math_ai_theme'

export const useThemeStore = defineStore('theme', () => {
  const theme = ref(loadFromStorage(THEME_KEY, 'light'))

  function setTheme(newTheme) {
    theme.value = newTheme
    saveToStorage(THEME_KEY, newTheme)
    applyTheme(newTheme)
  }

  function toggleTheme() {
    setTheme(theme.value === 'light' ? 'dark' : 'light')
  }

  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t)
  }

  function init() {
    applyTheme(theme.value)
  }

  init()

  return { theme, setTheme, toggleTheme, init }
})