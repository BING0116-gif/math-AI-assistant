import { computed, type Ref } from 'vue'


export function greetingForHour(hour: number) {
  if (hour < 6) return ['夜深了，注意休息', '用数据看见进步']
  if (hour < 12) return ['上午好，开始今天的学习', '用数据看见进步']
  if (hour < 18) return ['下午好，继续加油', '用数据看见进步']
  return ['晚上好，辛苦了', '回顾今天的收获']
}


export function useDashboardMetrics(learningDashboard: Ref<any>, period: Ref<string>) {
  const greetingPair = computed(() => greetingForHour(new Date().getHours()))
  const greeting = computed(() => greetingPair.value[0])
  const greetingSub = computed(() => greetingPair.value[1])

  const learningMinutes = computed(() =>
    Math.round((learningDashboard.value?.metrics?.active_seconds?.value || 0) / 60)
  )
  const learningHours = computed(() => (learningMinutes.value / 60).toFixed(1))
  const weekStudyDaysDisplay = computed(() =>
    Math.max(0, learningDashboard.value?.metrics?.study_days?.value || 0)
  )
  const masteredPoints = computed(() =>
    (learningDashboard.value?.dimensions?.mastery || []).filter((item: any) => item.value >= 0.8).length
  )
  const accuracyRate = computed(() => learningDashboard.value?.metrics?.accuracy?.value ?? null)
  const weakPoints = computed(() =>
    (learningDashboard.value?.weakest || []).map((item: any) => ({
      category: item.name || item.code,
      code: item.code,
      rate: Math.round((1 - item.mastery) * 100),
      sampleSize: item.sample_size,
    }))
  )
  const chapterMastery = computed(() =>
    (learningDashboard.value?.chapter_mastery || []).map((item: any) => ({
      ...item,
      percent: Math.round(item.value * 100),
    }))
  )
  const todayTasks = computed(() => {
    const today = learningDashboard.value?.today
    return [today?.primary, ...(today?.alternatives || [])]
      .filter(Boolean)
      .map((task: any) => ({ ...task, done: false }))
  })
  const completedTasks = computed(() => todayTasks.value.filter((task: any) => task.done).length)
  const totalTasks = computed(() => todayTasks.value.length)
  const taskProgress = computed(() =>
    totalTasks.value ? Math.round((completedTasks.value / totalTasks.value) * 100) : 0
  )
  const goalItems = computed(() => learningDashboard.value?.goals?.items || [])
  const overallGoalProgress = computed(() => {
    const items = goalItems.value
    return items.length
      ? Math.round(items.reduce((sum: number, item: any) => sum + item.percent, 0) / items.length)
      : 0
  })
  const trendData = computed(() =>
    (learningDashboard.value?.trend || []).map((item: any) => ({
      date: item.date.slice(5),
      rate: item.accuracy,
      correct: item.correct,
      total: item.attempts,
    }))
  )
  const heatmapData = computed(() =>
    (learningDashboard.value?.heatmap || []).map((item: any, index: number) => {
      const minutes = Math.round(item.active_seconds / 60)
      const intensity = minutes === 0 && item.attempts === 0
        ? 0
        : Math.min(4, Math.max(1, Math.ceil((minutes + item.attempts * 2) / 15)))
      return [new Date(item.date).getDay(), Math.floor(index / 7), intensity, item.date, minutes, item.attempts]
    })
  )
  const weeklyComparison = computed(() => {
    const rows = trendData.value.slice(-7)
    const total = rows.reduce((sum: number, item: any) => sum + item.total, 0)
    const correct = rows.reduce((sum: number, item: any) => sum + item.correct, 0)
    return { thisWeek: total ? Math.round(correct / total * 100) : null, sampleSize: total }
  })
  const periodText = computed(() =>
    period.value === '7d' ? '近 7 天' : period.value === '30d' ? '近 30 天' : '全部'
  )

  return {
    greeting,
    greetingSub,
    learningHours,
    weekStudyDaysDisplay,
    masteredPoints,
    accuracyRate,
    weakPoints,
    chapterMastery,
    todayTasks,
    completedTasks,
    totalTasks,
    taskProgress,
    goalItems,
    overallGoalProgress,
    trendData,
    heatmapData,
    weeklyComparison,
    periodText,
  }
}
