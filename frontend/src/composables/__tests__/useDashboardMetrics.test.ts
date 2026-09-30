import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { greetingForHour, useDashboardMetrics } from '../useDashboardMetrics'


describe('useDashboardMetrics', () => {
  it('projects empty evidence without inventing progress', () => {
    const metrics = useDashboardMetrics(ref(null), ref('7d'))

    expect(metrics.learningHours.value).toBe('0.0')
    expect(metrics.accuracyRate.value).toBeNull()
    expect(metrics.todayTasks.value).toEqual([])
    expect(metrics.overallGoalProgress.value).toBe(0)
    expect(metrics.weeklyComparison.value).toEqual({ thisWeek: null, sampleSize: 0 })
  })

  it('projects evidence, tasks, trend, and heatmap deterministically', () => {
    const dashboard = ref({
      metrics: {
        active_seconds: { value: 5400 },
        study_days: { value: 3 },
        accuracy: { value: 75 },
      },
      dimensions: { mastery: [{ value: 0.8 }, { value: 0.79 }, { value: 1 }] },
      weakest: [{ name: '极限', code: 'limit', mastery: 0.35, sample_size: 4 }],
      chapter_mastery: [{ name: '第一章', value: 0.666, evidence_count: 3 }],
      today: { primary: { id: 'p1' }, alternatives: [{ id: 'p2' }] },
      goals: { items: [{ percent: 50 }, { percent: 100 }] },
      trend: [{ date: '2026-09-26', accuracy: 75, correct: 3, attempts: 4 }],
      heatmap: [{ date: '2026-09-26', active_seconds: 600, attempts: 1 }],
    })
    const metrics = useDashboardMetrics(dashboard, ref('30d'))

    expect(metrics.learningHours.value).toBe('1.5')
    expect(metrics.masteredPoints.value).toBe(2)
    expect(metrics.weakPoints.value[0]).toMatchObject({ category: '极限', rate: 65 })
    expect(metrics.chapterMastery.value[0].percent).toBe(67)
    expect(metrics.totalTasks.value).toBe(2)
    expect(metrics.overallGoalProgress.value).toBe(75)
    expect(metrics.weeklyComparison.value).toEqual({ thisWeek: 75, sampleSize: 4 })
    expect(metrics.heatmapData.value[0].slice(2)).toEqual([1, '2026-09-26', 10, 1])
    expect(metrics.periodText.value).toBe('近 30 天')
  })

  it('keeps greeting boundaries explicit', () => {
    expect(greetingForHour(5)[0]).toContain('夜深')
    expect(greetingForHour(6)[0]).toContain('上午好')
    expect(greetingForHour(14)[0]).toContain('下午好')
    expect(greetingForHour(18)[1]).toContain('回顾')
  })
})
