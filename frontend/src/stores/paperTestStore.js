/**
 * 组卷测试状态（学生端，主系统 Pinia setup 风格，与 authStore/chatStore 一致）。
 * phase: setup（配置）→ test（答题）→ result（结果）
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { paperTestApi, unwrap } from '@/api/paperTest'

export const usePaperTestStore = defineStore('paperTest', () => {
  const phase = ref('setup')
  const loading = ref(false)
  const error = ref('')

  // 配置：type_mix = { choice: n, judge: n, numeric_fill: n, expression_fill: n }
  const config = ref({
    type_mix: { choice: 5, judge: 2, numeric_fill: 3, expression_fill: 0 },
    title: '',
  })

  const paper = ref(null)
  const answers = ref({})
  const result = ref(null)

  const totalCount = computed(() => paper.value?.total || 0)
  const answeredCount = computed(() =>
    paper.value
      ? paper.value.questions.filter(
          (q) => answers.value[q.question_id] !== undefined && answers.value[q.question_id] !== ''
        ).length
      : 0
  )
  const canSubmit = computed(() => totalCount.value > 0 && answeredCount.value === totalCount.value)

  async function generate() {
    loading.value = true
    error.value = ''
    try {
      const data = unwrap(await paperTestApi.generate({ config: { ...config.value }, title: config.value.title || '随堂练习' }))
      paper.value = data
      answers.value = {}
      result.value = null
      phase.value = 'test'
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function submit() {
    if (!paper.value) return
    loading.value = true
    error.value = ''
    try {
      result.value = unwrap(await paperTestApi.submit(paper.value.paper_id, answers.value))
      phase.value = 'result'
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  function reset() {
    phase.value = 'setup'
    paper.value = null
    answers.value = {}
    result.value = null
    error.value = ''
    loading.value = false
  }

  return {
    phase, loading, error, config, paper, answers, result,
    totalCount, answeredCount, canSubmit,
    generate, submit, reset,
  }
})
