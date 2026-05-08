import { defineStore } from 'pinia'
import { ref, computed, reactive } from 'vue'
import { generateUUID } from '@/utils/helpers'
import { loadFromStorage, saveToStorage } from '@/utils/storage'
import * as errorBookApi from '@/api/errorBook'

const STORAGE_KEY = 'math_ai_error_book'

export const useErrorBookStore = defineStore('errorBook', () => {
  const errors = ref(loadFromStorage(STORAGE_KEY, []))
  const loading = ref(false)
  const currentDetailId = ref(null)

  const filter = reactive({
    search: '',
    category: '',
    mastery: ''
  })

  const totalErrors = computed(() => errors.value.length)
  const unmasteredCount = computed(() => errors.value.filter(e => !e.is_mastered).length)
  const masteredCount = computed(() => errors.value.filter(e => e.is_mastered).length)

  const availableCategories = computed(() => {
    const cats = new Set()
    errors.value.forEach(e => {
      (e.categories || []).forEach(c => cats.add(c))
    })
    return [...cats]
  })

  const filteredErrors = computed(() => {
    let result = [...errors.value]

    if (filter.search) {
      const term = filter.search.toLowerCase()
      result = result.filter(item => {
        const searchText = [
          item.display_question || item.question,
          item.correct_answer,
          item.error_reason,
          item.recognized_text,
          ...(item.categories || [])
        ].join(' ').toLowerCase()
        return searchText.includes(term)
      })
    }

    if (filter.category) {
      result = result.filter(item =>
        item.categories && item.categories.includes(filter.category)
      )
    }

    if (filter.mastery) {
      const level = parseInt(filter.mastery)
      result = result.filter(item => (item.mastery_level || 3) === level)
    }

    return result
  })

  const currentDetail = computed(() =>
    errors.value.find(e => e.id === currentDetailId.value) || null
  )

  function persist() {
    saveToStorage(STORAGE_KEY, errors.value)
  }

  async function loadErrors() {
    loading.value = true
    try {
      const response = await errorBookApi.getErrorBook()
      const data = Array.isArray(response.data) ? response.data : (response.data.data || [])
      errors.value = data
      persist()
    } catch (err) {
      console.error('加载错题本失败:', err)
      errors.value = loadFromStorage(STORAGE_KEY, [])
    } finally {
      loading.value = false
    }
  }

  async function addError(errorData) {
    try {
      const response = await errorBookApi.addErrorBook(errorData)
      const data = response.data
      const newError = {
        id: data.id || data.data?.id || generateUUID(),
        ...errorData,
        ...(data.data || {}),
        added_at: data.data?.added_at || new Date().toLocaleString()
      }
      errors.value.unshift(newError)
      persist()
      return newError
    } catch (err) {
      console.error('添加错题失败:', err)
      const fallback = {
        id: generateUUID(),
        ...errorData,
        added_at: new Date().toLocaleString()
      }
      errors.value.unshift(fallback)
      persist()
      return fallback
    }
  }

  async function updateError(errorId, updates) {
    const idx = errors.value.findIndex(e => e.id === errorId)
    if (idx === -1) return

    Object.assign(errors.value[idx], updates)
    persist()

    try {
      await errorBookApi.updateErrorBook(errorId, updates)
    } catch (err) {
      console.error('更新错题失败:', err)
    }
  }

  async function deleteError(errorId) {
    errors.value = errors.value.filter(e => e.id !== errorId)
    persist()

    try {
      await errorBookApi.deleteErrorBook(errorId)
    } catch (err) {
      console.error('删除错题失败:', err)
    }
  }

  function toggleMastery(errorId) {
    const error = errors.value.find(e => e.id === errorId)
    if (error) {
      error.is_mastered = !error.is_mastered
      persist()
    }
  }

  function setFilter(newFilter) {
    Object.assign(filter, newFilter)
  }

  function resetFilter() {
    filter.search = ''
    filter.category = ''
    filter.mastery = ''
  }

  function setCurrentDetail(errorId) {
    currentDetailId.value = errorId
  }

  function clearCurrentDetail() {
    currentDetailId.value = null
  }

  return {
    errors,
    loading,
    filter,
    currentDetailId,
    totalErrors,
    unmasteredCount,
    masteredCount,
    availableCategories,
    filteredErrors,
    currentDetail,
    loadErrors,
    addError,
    updateError,
    deleteError,
    toggleMastery,
    setFilter,
    resetFilter,
    setCurrentDetail,
    clearCurrentDetail,
    persist
  }
})
