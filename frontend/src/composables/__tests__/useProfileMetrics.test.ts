import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { useProfileMetrics } from '../useProfileMetrics'

const fixedNow = () => new Date(2026, 8, 27, 12, 0, 0)

describe('useProfileMetrics', () => {
  it('projects canonical profile evidence into stable metrics', () => {
    const profile = ref<any>({
      dimensions: {
        mastery: [
          { code: 'A', value: 0.9, evidence_count: 4 },
          { code: 'B', value: 0.65, evidence_count: 3 },
          { code: 'C', value: 0.4, evidence_count: 2 },
          { code: 'D', value: 0.2, evidence_count: 1 },
        ],
        memory_strength: [{ value: 0.8 }, { value: 0.6 }],
      },
      forgetting_curve: {
        observations: [
          { interval_days: 1, retained: true },
          { interval_days: 3, retained: false },
        ],
      },
      insights: [{ title: '结论', conclusion: '需巩固', evidence: '2 次', action: '复习' }],
    })
    const metrics = useProfileMetrics(profile, ref([]), fixedNow)

    expect(metrics.dateRange.value).toBe('2026/09/21 – 2026/09/27')
    expect(metrics.masteryDistribution.value).toEqual({ mastered: 1, learning: 1, weak: 1, fragile: 1 })
    expect(metrics.memoryStabilityScore.value).toBe(70)
    expect(metrics.longTermRetention.value).toBe(50)
    expect(metrics.knowledgeMasteryTop10.value[0]).toEqual({ category: 'A', rate: 90, evidenceCount: 4 })
    expect(metrics.forgettingCurveData.value.userCurve).toEqual([100, 0])
  })

  it('does not invent week-over-week trends without historical evidence', () => {
    const profile = ref<any>({
      dimensions: {
        mastery: [{ code: '脆弱点', value: 0.1 }],
        memory_strength: [],
      },
    })
    const metrics = useProfileMetrics(profile, ref([]), fixedNow)

    expect(metrics.fragilePoints.value).toHaveLength(1)
    expect(metrics.fragileDelta.value).toBe(0)
    expect(metrics.retentionTrend.value).toBe(0)
  })

  it('keeps empty profile and review plan explicit', () => {
    const metrics = useProfileMetrics(ref(null), ref([]), fixedNow)

    expect(metrics.memoryStabilityScore.value).toBe(0)
    expect(metrics.stabilityLevel.value).toBe('需要加强')
    expect(metrics.reviewPlan.value).toEqual([])
    expect(metrics.reviewEstimateMinutes.value).toBe(0)
    expect(metrics.aiInsights.value).toEqual([])
  })
})
