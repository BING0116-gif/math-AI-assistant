import { reactive, ref } from 'vue'
import { describe, expect, it } from 'vitest'
import {
  buildErrorPatternDistribution,
  errorStage,
  useErrorBookMetrics,
} from '../useErrorBookMetrics'

const NOW = new Date('2026-09-27T08:00:00+08:00').getTime()
const daysAgo = (days: number) => new Date(NOW - days * 86_400_000).toISOString()

function makeStore(errors: Array<Record<string, any>>) {
  return reactive({
    errors,
    filteredErrors: errors,
    get totalErrors() { return this.errors.length },
    get masteredCount() { return this.errors.filter(item => item.is_mastered).length },
    get unmasteredCount() { return this.errors.filter(item => !item.is_mastered).length },
  })
}

describe('useErrorBookMetrics', () => {
  it('classifies each graduation stage at deterministic boundaries', () => {
    expect(errorStage({ added_at: daysAgo(3) }, NOW)).toBe('new')
    expect(errorStage({ added_at: daysAgo(4) }, NOW)).toBe('understanding')
    expect(errorStage({ mastery_level: 4 }, NOW)).toBe('consolidating')
    expect(errorStage({ is_mastered: true }, NOW)).toBe('mastered')
    expect(errorStage({ added_at: 'invalid' }, NOW)).toBe('understanding')
  })

  it('projects due reviews and tab filtering from canonical evidence', () => {
    const errors = [
      { id: 'new', added_at: daysAgo(1), error_reason: '计算符号写错', categories: ['高数'] },
      { id: 'old', added_at: daysAgo(8), error_reason: '遗漏定义域', knowledge_point_codes: ['KP-1'] },
      { id: 'done', added_at: daysAgo(2), is_mastered: true, error_reason: '审题失误' },
    ]
    const store = makeStore(errors)
    const reviews = ref([{
      id: 9,
      due_at: new Date(NOW - 1_000).toISOString(),
      knowledge_point_code: 'KP-1',
      knowledge_point_name: '函数定义域',
      review_count: 1,
      interval_days: 3,
    }])
    const activeTab = ref('understanding')
    const metrics = useErrorBookMetrics(store, reviews, activeTab, () => NOW)

    expect(metrics.todayReviewCount.value).toBe(1)
    expect(metrics.todayReviewPlan.value[0]).toMatchObject({
      error: { id: 'old' },
      topic: '函数定义域',
      stage: { label: '第 2 次' },
    })
    expect(metrics.filteredForTab.value.map(item => item.id)).toEqual(['old'])
    expect(metrics.graduationStages.value.map(item => item.count)).toEqual([1, 1, 0, 1])
  })

  it('keeps pattern and empty-state summaries evidence based', () => {
    expect(buildErrorPatternDistribution([])).toEqual([])
    const patterns = buildErrorPatternDistribution([
      { error_reason: '计算错误' },
      { error_reason: '代数运算不规范' },
      { error_reason: '读题失误' },
    ])
    expect(patterns[0]).toMatchObject({ name: '计算错误', count: 2, percent: 67 })

    const metrics = useErrorBookMetrics(makeStore([]), ref([]), ref('all'), () => NOW)
    expect(metrics.todayReviewCount.value).toBe(0)
    expect(metrics.graduationProgressText.value).toBe('暂无错题')
    expect(metrics.topErrorPattern.value).toEqual({ name: '—', meta: '暂无数据' })
  })
})
