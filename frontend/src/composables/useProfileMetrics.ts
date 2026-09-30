import { computed, type Ref } from 'vue'
import { formatStableDateTime } from '@/utils/dateTime'

type Profile = Record<string, any> | null
type Review = Record<string, any>

function formatDate(date: Date) {
  return `${date.getFullYear()}/${String(date.getMonth() + 1).padStart(2, '0')}/${String(date.getDate()).padStart(2, '0')}`
}

export function useProfileMetrics(
  canonicalProfile: Ref<Profile>,
  canonicalReviews: Ref<Review[]>,
  nowProvider: () => Date = () => new Date(),
) {
  const dateRange = computed(() => {
    const today = nowProvider()
    const weekAgo = new Date(today.getTime() - 6 * 24 * 60 * 60 * 1000)
    return `${formatDate(weekAgo)} – ${formatDate(today)}`
  })
  const masteryItems = computed(() => canonicalProfile.value?.dimensions?.mastery || [])
  const memoryStrengthItems = computed(() => canonicalProfile.value?.dimensions?.memory_strength || [])

  const masteryDistribution = computed(() => {
    const distribution = { mastered: 0, learning: 0, weak: 0, fragile: 0 }
    masteryItems.value.forEach((item: any) => {
      if (item.value >= 0.8) distribution.mastered++
      else if (item.value >= 0.6) distribution.learning++
      else if (item.value >= 0.35) distribution.weak++
      else distribution.fragile++
    })
    return distribution
  })
  const memoryStabilityScore = computed(() => {
    if (!memoryStrengthItems.value.length) return 0
    const average = memoryStrengthItems.value.reduce((sum: number, item: any) => sum + item.value, 0)
      / memoryStrengthItems.value.length
    return Math.round(average * 100)
  })
  const stabilityLevel = computed(() => {
    const score = memoryStabilityScore.value
    if (score >= 80) return '良好'
    if (score >= 60) return '中等'
    if (score >= 40) return '较弱'
    return '需要加强'
  })
  const stabilityLevelColor = computed(() => {
    const score = memoryStabilityScore.value
    if (score >= 80) return 'var(--green)'
    if (score >= 60) return 'var(--accent)'
    if (score >= 40) return 'var(--amber)'
    return 'var(--rose)'
  })
  const fragilePoints = computed(() => masteryItems.value
    .filter((item: any) => item.value < 0.35)
    .map((item: any) => ({ name: item.code, count: 1 })))

  // 当前 API 没有上周快照。没有比较证据时不制造趋势。
  const fragileDelta = computed(() => 0)
  const retentionTrend = computed(() => 0)
  const longTermRetention = computed(() => {
    const observations = canonicalProfile.value?.forgetting_curve?.observations || []
    if (!observations.length) return 0
    return Math.round(observations.filter((item: any) => item.retained).length / observations.length * 100)
  })
  const reviewPlan = computed(() => canonicalReviews.value.map((item: any) => ({
    title: item.knowledge_point_name,
    time: formatStableDateTime(item.due_at),
    category: '间隔复习',
    count: 1,
    interval: `${item.interval_days} 天间隔`,
  })))
  const reviewPlanCount = computed(() => reviewPlan.value.length)
  const reviewEstimateMinutes = computed(() => reviewPlan.value.length * 12)
  const forgettingCurveData = computed(() => {
    const observations = canonicalProfile.value?.forgetting_curve?.observations || []
    return {
      days: observations.map((item: any) => `${item.interval_days}天`),
      referenceCurve: [],
      userCurve: observations.map((item: any) => item.retained ? 100 : 0),
    }
  })
  const memoryStrengthData = computed(() => [
    { name: '已掌握', value: masteryDistribution.value.mastered },
    { name: '学习中', value: masteryDistribution.value.learning },
    { name: '薄弱', value: masteryDistribution.value.weak },
    { name: '脆弱', value: masteryDistribution.value.fragile },
  ])
  const strengthOverall = computed(() => memoryStabilityScore.value)
  const strengthLabel = computed(() => {
    if (strengthOverall.value >= 75) return '良好'
    if (strengthOverall.value >= 50) return '中等'
    return '需加强'
  })
  const knowledgeMasteryTop10 = computed(() => masteryItems.value
    .slice()
    .sort((a: any, b: any) => b.value - a.value)
    .slice(0, 10)
    .map((item: any) => ({
      category: item.code,
      rate: Math.round(item.value * 100),
      evidenceCount: item.evidence_count ?? 0,
    })))
  const aiInsights = computed(() => (canonicalProfile.value?.insights || []).map((item: any) => ({
    label: item.title,
    value: item.conclusion,
    evidence: item.evidence,
    action: item.action,
  })))

  return {
    dateRange,
    masteryDistribution,
    memoryStabilityScore,
    stabilityLevel,
    stabilityLevelColor,
    fragilePoints,
    fragileDelta,
    longTermRetention,
    retentionTrend,
    reviewPlan,
    reviewPlanCount,
    reviewEstimateMinutes,
    forgettingCurveData,
    memoryStrengthData,
    strengthOverall,
    strengthLabel,
    knowledgeMasteryTop10,
    aiInsights,
  }
}
