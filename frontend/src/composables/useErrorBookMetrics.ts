import { computed, type Ref } from 'vue'

type ErrorItem = Record<string, any>
type ReviewItem = Record<string, any>
type ErrorBookStore = Record<string, any>

const DAY_MS = 86_400_000

function timestamp(value: unknown, fallback: number) {
  if (value === null || value === undefined || value === '') return fallback
  return new Date(value as string | number | Date).getTime()
}

export function errorStage(error: ErrorItem, now: number) {
  if (error.is_mastered) return 'mastered'
  if ((error.mastery_level || 3) >= 4) return 'consolidating'
  const addedAt = timestamp(error.added_at, now)
  if (!Number.isFinite(addedAt)) return 'understanding'
  const ageDays = Math.floor((now - addedAt) / DAY_MS)
  return ageDays <= 3 ? 'new' : 'understanding'
}

export function buildErrorPatternDistribution(errors: ErrorItem[]) {
  const patternMap: Record<string, string[]> = {
    条件遗漏: ['条件遗漏', '条件', '定义域', '边界', '范围'],
    概念理解偏差: ['概念', '混淆', '理解', '定义', '定理', '公式'],
    计算错误: ['计算', '运算', '符号', '代数', '数值'],
    方法选择错误: ['方法', '思路', '方向', '策略', '选择'],
    审题失误: ['审题', '读题', '理解题意', '漏看', '误读'],
  }
  const counts: Record<string, number> = {}

  errors.forEach((error) => {
    const reason = String(error.error_reason || '').toLowerCase()
    const matched = Object.entries(patternMap).find(([, keywords]) =>
      keywords.some(keyword => reason.includes(keyword.toLowerCase())),
    )
    const name = matched?.[0] || '其他类型'
    counts[name] = (counts[name] || 0) + 1
  })

  const total = Object.values(counts).reduce((sum, count) => sum + count, 0) || 1
  return Object.entries(counts)
    .map(([name, count]) => {
      const percent = Math.round((count / total) * 100)
      const tone = percent >= 40 ? 'terracotta' : percent >= 20 ? 'amber' : 'sage'
      return { name, count, percent, tone }
    })
    .sort((a, b) => b.percent - a.percent)
    .slice(0, 5)
}

function lastReviewText(error: ErrorItem, now: number) {
  if (error.is_mastered) return '已掌握'
  const diff = Math.floor((now - timestamp(error.added_at, now)) / DAY_MS)
  if (diff === 0) return '今天'
  if (diff === 1) return '1 天前'
  return `${diff} 天前`
}

export function useErrorBookMetrics(
  store: ErrorBookStore,
  canonicalReviews: Ref<ReviewItem[]>,
  activeTab: Ref<string>,
  nowProvider: () => number = () => Date.now(),
) {
  const now = () => nowProvider()
  const dueReviews = computed(() =>
    canonicalReviews.value.filter(item => timestamp(item.due_at, Infinity) <= now()),
  )

  const todayReviewCount = computed(() =>
    dueReviews.value.length || store.errors.filter((e: ErrorItem) => !e.is_mastered && e.review_state !== 'graduated').length,
  )
  const errorPatterns = computed(() => buildErrorPatternDistribution(store.errors))
  const topErrorPattern = computed(() => {
    const top = errorPatterns.value[0]
    if (!top) return { name: '—', meta: '暂无数据' }
    return { name: top.name, meta: top.percent > 0 ? `${top.percent}% 错误率 · ${top.count} 题` : '暂无数据' }
  })
  const inProgressCount = computed(() =>
    store.errors.filter((e: ErrorItem) => !e.is_mastered && (e.mastery_level || 3) >= 3).length,
  )
  const graduationProgressText = computed(() => {
    if (store.totalErrors === 0) return '暂无错题'
    return `${Math.round((store.masteredCount / store.totalErrors) * 100)}% 已毕业 · ${store.masteredCount}/${store.totalErrors}`
  })
  const weeklyMasteredCount = computed(() => {
    const cutoff = now() - 7 * DAY_MS
    return store.errors.filter((e: ErrorItem) => e.is_mastered && timestamp(e.added_at, now()) >= cutoff).length
  })
  const patternSummary = computed(() => {
    const top = errorPatterns.value[0]
    if (!top || store.totalErrors === 0) return ''
    const messages: Record<string, string> = {
      条件遗漏: '你最近的主要问题并不是公式不会，而是在含参数题目中容易忽略边界条件。建议优先训练条件识别能力。',
      概念理解偏差: '你的主要问题集中在概念理解上。建议先回归教材，梳理相关定义和定理，再针对性练习。',
      计算错误: '你的计算环节需要加强。建议保持规范的解题步骤，每步仔细核对后再推进。',
    }
    if (messages[top.name]) return messages[top.name]
    if (top.count >= Math.ceil(store.totalErrors / 2)) {
      return `「${top.name}」是最突出的错误模式，占比 ${top.percent}%。建议集中解决此类问题。`
    }
    return `你的错误分布较为分散，共有 ${errorPatterns.value.length} 种错误模式。建议从占比最高的「${top.name}」开始突破。`
  })

  const todayReviewPlan = computed(() => {
    const scheduled = dueReviews.value.slice(0, 5).flatMap((review: ReviewItem) => {
      const error = review.error_item_id
        ? store.errors.find((item: ErrorItem) => item.id === review.error_item_id)
        : store.errors.find((item: ErrorItem) =>
            (item.knowledge_point_codes || item.categories || []).includes(review.knowledge_point_code),
          )
      if (!error) return []
      return [{
        error,
        topic: review.knowledge_point_name,
        stage: { label: `第 ${review.review_count + 1} 次`, class: review.stage ? 'consolidating' : 'new' },
        lastReviewText: `已到期 · ${review.interval_days} 天间隔`,
      }]
    })
    if (scheduled.length) return scheduled
    return store.errors
      .filter((e: ErrorItem) => !e.is_mastered && e.review_state !== 'graduated')
      .slice(0, 5)
      .map((error: ErrorItem) => ({
        error,
        topic: error.knowledge_point_codes?.[0] || error.categories?.[0] || '错题回顾',
        stage: { label: '待复习', class: 'new' },
        lastReviewText: `${lastReviewText(error, now())} · 尚未排期`,
      }))
  })

  const reviewSchedule = computed(() => {
    const groups = new Map<string, { label: string; tone: string; tasks: string[] }>()
    const today = new Date(now()).setHours(0, 0, 0, 0)
    canonicalReviews.value.forEach((item: ReviewItem) => {
      const due = new Date(item.due_at).setHours(0, 0, 0, 0)
      const days = Math.floor((due - today) / DAY_MS)
      const label = days <= 0 ? '今天' : days === 1 ? '明天' : `${days} 天后`
      const group = groups.get(label) || { label, tone: days <= 0 ? 'urgent' : days === 1 ? 'soon' : 'normal', tasks: [] }
      group.tasks.push(`${item.knowledge_point_name} · 第 ${item.review_count + 1} 次复习（${item.interval_days} 天间隔）`)
      groups.set(label, group)
    })
    return [...groups.values()]
  })

  const graduationStages = computed(() => {
    const stages = [
      { key: 'new', label: '新错', icon: '📝', count: 0, class: 'new', percent: 0 },
      { key: 'understanding', label: '理解中', icon: '📖', count: 0, class: 'understanding', percent: 0 },
      { key: 'consolidating', label: '巩固中', icon: '🔄', count: 0, class: 'consolidating', percent: 0 },
      { key: 'mastered', label: '稳定掌握', icon: '✓', count: 0, class: 'mastered', percent: 0 },
    ]
    store.errors.forEach((error: ErrorItem) => {
      const stage = errorStage(error, now())
      stages.find(item => item.key === stage)!.count++
    })
    stages.forEach((stage) => { stage.percent = Math.round((stage.count / (store.totalErrors || 1)) * 100) })
    return stages
  })
  const graduationStats = computed(() => ({
    total: store.totalErrors,
    mastered: store.masteredCount,
    inProgress: store.unmasteredCount,
  }))
  const filterTabs = computed(() => [
    { key: 'all', label: '全部', count: store.totalErrors },
    ...graduationStages.value.map(stage => ({
      key: stage.key,
      label: stage.key === 'mastered' ? '已掌握' : stage.label,
      count: stage.count,
    })),
  ])
  const filteredForTab = computed(() => {
    if (activeTab.value === 'all') return store.filteredErrors
    return store.filteredErrors.filter((error: ErrorItem) => errorStage(error, now()) === activeTab.value)
  })
  const getFilteredIndex = (index: number) => {
    const error = filteredForTab.value[index]
    if (!error) return index
    const globalIndex = store.filteredErrors.findIndex((item: ErrorItem) => item.id === error.id)
    return globalIndex >= 0 ? globalIndex : index
  }

  const knowledgeOverview = computed(() => {
    const categories: Record<string, { total: number; mastered: number }> = {}
    store.errors.forEach((error: ErrorItem) => {
      ;(error.categories || ['其他']).forEach((name: string) => {
        categories[name] ||= { total: 0, mastered: 0 }
        categories[name].total++
        if (error.is_mastered) categories[name].mastered++
      })
    })
    return Object.entries(categories).map(([name, data]) => {
      const percent = data.total ? Math.round((data.mastered / data.total) * 100) : 0
      return { name, percent, tone: percent >= 70 ? 'sage' : percent >= 45 ? 'amber' : 'terracotta', ...data }
    }).sort((a, b) => a.name.localeCompare(b.name, 'zh'))
  })
  const learningTips = computed(() => {
    const tips: Array<{ icon: string; text: string }> = []
    const weakest = [...knowledgeOverview.value].sort((a, b) => a.percent - b.percent)[0]
    if (weakest) tips.push({ icon: '🎯', text: `「${weakest.name}」是当前最薄弱环节，需优先巩固` })
    if (store.unmasteredCount > 0) tips.push({ icon: '⏰', text: `有 ${store.unmasteredCount} 道错题等待复习，建议集中处理` })
    const avg = knowledgeOverview.value.length
      ? Math.round(knowledgeOverview.value.reduce((sum, item) => sum + item.percent, 0) / knowledgeOverview.value.length)
      : 0
    tips.push({ icon: '💡', text: avg >= 60 ? `整体掌握率 ${avg}%，可适度提高难度` : `整体掌握率 ${avg}%，建议加强基础题练习` })
    return tips
  })

  return {
    todayReviewCount, topErrorPattern, inProgressCount, graduationProgressText,
    weeklyMasteredCount, errorPatterns, patternSummary, todayReviewPlan,
    reviewSchedule, graduationStages, graduationStats, filterTabs, filteredForTab,
    getFilteredIndex, knowledgeOverview, learningTips,
  }
}
