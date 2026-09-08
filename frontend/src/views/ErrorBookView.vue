<template>
  <AppShell>
    <template #topbar-title>
      <span>错题复盘</span>
    </template>

    <div class="error-book-view" v-loading="store.loading">
      <!-- ═══ Page Header ═══ -->
      <div class="page-header">
        <div class="page-header-left">
          <h1 class="page-header-title">错题复盘</h1>
          <p class="page-header-subtitle">AI 根据你的错误模式和学习记录安排复习</p>
        </div>
        <div class="page-header-right">
          <router-link to="/" class="back-link">返回对话</router-link>
          <button class="start-review-btn" @click="startDailyReview">开始今日复习</button>
        </div>
      </div>

      <!-- ═══ KPI Row ═══ -->
      <div class="kpi-row">
        <div class="kpi-card amber">
          <div class="kpi-value">{{ todayReviewCount }}</div>
          <div class="kpi-label">今日待解决</div>
          <div class="kpi-meta">{{ todayReviewCount > 0 ? '优先复习最早加入的错题' : '全部完成' }}</div>
        </div>
        <div class="kpi-card terracotta">
          <div class="kpi-value">{{ topErrorPattern.name }}</div>
          <div class="kpi-label">核心错误模式</div>
          <div class="kpi-meta">{{ topErrorPattern.meta }}</div>
        </div>
        <div class="kpi-card ink">
          <div class="kpi-value">{{ inProgressCount }}</div>
          <div class="kpi-label">待毕业错题</div>
          <div class="kpi-meta">{{ graduationProgressText }}</div>
        </div>
        <div class="kpi-card sage">
          <div class="kpi-value">{{ weeklyMasteredCount }}</div>
          <div class="kpi-label">本周消灭错误</div>
          <div class="kpi-meta">{{ weeklyMasteredCount > 0 ? '稳定掌握中' : '继续努力' }}</div>
        </div>
      </div>

      <!-- ═══ Row 2: Today's Plan + AI Error Pattern ═══ -->
      <div class="content-grid-2col">
        <!-- Today's Review Plan -->
        <div class="panel panel-plan">
          <div class="panel-header">
            <h3 class="panel-title">今日复习计划</h3>
            <button class="panel-link" @click="scrollToAll">查看全部 →</button>
          </div>
          <div class="panel-body">
            <div v-if="todayReviewPlan.length === 0" class="panel-empty">
              <span class="empty-icon">✓</span>
              <p class="empty-text">暂无待复习的错题</p>
              <p class="empty-hint">在对话中点击「加入错题本」来添加第一道错题</p>
            </div>
            <div v-else class="review-plan-list">
              <div
                v-for="(item, idx) in todayReviewPlan"
                :key="item.error.id"
                class="review-plan-item"
                @click="openDetailForItem(item.error)"
              >
                <div class="plan-rank">{{ String(idx + 1).padStart(2, '0') }}</div>
                <div class="plan-info">
                  <div class="plan-title">
                    <span class="plan-cat" v-for="cat in item.error.categories?.slice(0, 2)" :key="cat">{{ cat }}</span>
                    <span class="plan-sep">·</span>
                    <span class="plan-topic">{{ item.topic }}</span>
                  </div>
                  <div class="plan-meta">
                    <span class="plan-error-type">错误类型：{{ item.error.error_reason || '需巩固' }}</span>
                    <span class="plan-dot">·</span>
                    <span class="plan-time">上次错误：{{ item.lastReviewText }}</span>
                  </div>
                </div>
                <div class="plan-action">
                  <span class="plan-stage-badge" :class="item.stage.class">{{ item.stage.label }}</span>
                  <span class="plan-arrow">→</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- AI Error Pattern Analysis -->
        <div class="panel panel-pattern">
          <div class="panel-header">
            <h3 class="panel-title">AI 错因画像</h3>
          </div>
          <div class="panel-body">
            <div v-if="errorPatterns.length === 0" class="panel-empty">
              <p class="empty-text">暂无足够数据进行分析</p>
            </div>
            <div v-else>
              <div class="pattern-list">
                <div
                  v-for="p in errorPatterns"
                  :key="p.name"
                  class="pattern-item"
                >
                  <div class="pattern-info">
                    <span class="pattern-name">{{ p.name }}</span>
                    <span class="pattern-percent" :class="p.tone">{{ p.percent }}%</span>
                  </div>
                  <div class="pattern-bar">
                    <div class="pattern-fill" :class="p.tone" :style="{ width: p.percent + '%' }"></div>
                  </div>
                </div>
              </div>
              <div class="pattern-summary" v-if="patternSummary">
                <div class="summary-text">{{ patternSummary }}</div>
              </div>
              <div class="pattern-action">
                <button class="pattern-train-btn" @click="handleTrainClick">
                  训练条件识别能力 →
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ Row 3: Future Review Plan + Graduation Progress ═══ -->
      <div class="content-grid-2col">
        <!-- Future Review Plan -->
        <div class="panel panel-schedule">
          <div class="panel-header">
            <h3 class="panel-title">未来复习计划</h3>
            <span class="panel-range">基于间隔重复</span>
          </div>
          <div class="panel-body">
            <div class="schedule-timeline">
              <div
                v-for="(slot, idx) in reviewSchedule"
                :key="idx"
                class="timeline-item"
              >
                <div class="timeline-marker">
                  <div class="timeline-dot" :class="slot.tone"></div>
                  <div v-if="idx < reviewSchedule.length - 1" class="timeline-line"></div>
                </div>
                <div class="timeline-content">
                  <div class="timeline-label">{{ slot.label }}</div>
                  <div class="timeline-tasks">
                    <span
                      v-for="(task, ti) in slot.tasks"
                      :key="ti"
                      class="timeline-task"
                    >{{ task }}</span>
                    <span v-if="slot.tasks.length === 0" class="timeline-empty">暂无安排</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Graduation Progress -->
        <div class="panel panel-graduation">
          <div class="panel-header">
            <h3 class="panel-title">错题毕业进度</h3>
            <span class="panel-range">{{ graduationStats.total }} 道错题</span>
          </div>
          <div class="panel-body">
            <div class="graduation-flow">
              <div
                v-for="stage in graduationStages"
                :key="stage.key"
                class="grad-stage"
              >
                <div class="grad-icon-wrap" :class="stage.class">
                  <span class="grad-icon">{{ stage.icon }}</span>
                </div>
                <div class="grad-info">
                  <span class="grad-label">{{ stage.label }}</span>
                  <span class="grad-count">{{ stage.count }}</span>
                </div>
                <div v-if="stage.percent > 0" class="grad-bar-wrap">
                  <div class="grad-bar" :style="{ width: stage.percent + '%' }"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ═══ All Errors Section ═══ -->
      <div class="all-errors-panel" ref="allErrorsRef">
        <div class="all-errors-header">
          <h2 class="section-title">全部错题</h2>
          <div class="compact-filter">
            <div class="filter-search">
              <span class="search-icon">🔍</span>
              <input
                v-model="store.filter.search"
                @input="onFilterChange"
                placeholder="搜索题目、标签..."
                class="search-input"
              />
            </div>
            <select v-model="store.filter.category" @change="onFilterChange" class="filter-select">
              <option value="">全部分类</option>
              <option v-for="cat in store.availableCategories" :key="cat" :value="cat">{{ cat }}</option>
            </select>
            <div class="filter-tabs">
              <button
                v-for="tab in filterTabs"
                :key="tab.key"
                class="filter-tab"
                :class="{ active: activeTab === tab.key }"
                @click="activeTab = tab.key"
              >
                {{ tab.label }}
                <span class="tab-count">{{ tab.count }}</span>
              </button>
            </div>
          </div>
        </div>

        <div class="all-errors-grid">
          <div class="errors-col">
            <div class="errors-list" ref="listRef">
              <TransitionGroup name="list-item">
                <ErrorCard
                  v-for="(error, idx) in filteredForTab"
                  :key="error.id"
                  :error="error"
                  :index="getFilteredIndex(idx)"
                  @view-detail="openDetail"
                  @toggle-mastery="store.toggleMastery(error.id)"
                  @delete="handleDelete(error)"
                />
              </TransitionGroup>
              <div v-if="filteredForTab.length === 0 && !store.loading" class="empty-state">
                <div class="empty-icon">—</div>
                <div class="empty-text">{{ store.totalErrors === 0 ? '暂无错题记录' : '没有匹配的错题' }}</div>
                <div class="empty-hint">{{ store.totalErrors === 0 ? '在对话中点击"加入错题本"来添加第一道错题吧！' : '尝试调整筛选条件' }}</div>
              </div>
            </div>
          </div>

          <div class="knowledge-sidebar">
            <div class="knowledge-card">
              <div class="knowledge-header">
                <h3 class="knowledge-title">知识点掌握概览</h3>
              </div>
              <div class="knowledge-body">
                <div v-for="cat in knowledgeOverview" :key="cat.name" class="knowledge-item">
                  <div class="knowledge-name-row">
                    <span class="knowledge-name">{{ cat.name }}</span>
                    <span class="knowledge-percent" :class="cat.tone">{{ cat.percent }}%</span>
                  </div>
                  <div class="knowledge-bar">
                    <div class="knowledge-fill" :class="cat.tone" :style="{ width: cat.percent + '%' }"></div>
                  </div>
                </div>
              </div>
            </div>
            <div class="knowledge-card tips">
              <div class="knowledge-header">
                <h3 class="knowledge-title">学习建议</h3>
              </div>
              <div class="knowledge-body tips-body">
                <div v-for="(tip, idx) in learningTips" :key="idx" class="tip-item">
                  <span class="tip-icon">{{ tip.icon }}</span>
                  <span class="tip-text">{{ tip.text }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <ErrorDetailModal
        v-if="detailVisible"
        :error="detailError"
        :current-index="detailIndex"
        :total="store.filteredErrors.length"
        @close="closeDetail"
        @prev="navigateDetail(-1)"
        @next="navigateDetail(1)"
        @toggle-mastery="store.toggleMastery(detailError.id)"
        @delete="handleDeleteFromDetail"
      />
    </Teleport>
  </AppShell>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import AppShell from '@/components/shell/AppShell.vue'
import ErrorCard from '@/components/errorBook/ErrorCard.vue'
import ErrorDetailModal from '@/components/errorBook/ErrorDetailModal.vue'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { getDueReviews } from '@/api/learning'

const route = useRoute()
const router = useRouter()
const store = useErrorBookStore()
const canonicalReviews = ref([])

const detailVisible = ref(false)
const detailIndex = ref(-1)
const activeTab = ref('all')
const allErrorsRef = ref(null)
const listRef = ref(null)

const detailError = computed(() =>
  detailIndex.value >= 0 ? store.filteredErrors[detailIndex.value] : null
)

/* ============================================================
 * Helpers
 * ============================================================ */
function truncateText(text, maxLen) {
  if (!text) return ''
  if (text.length <= maxLen) return text
  return text.substring(0, maxLen) + '...'
}

/* ============================================================
 * KPI Data
 * ============================================================ */
const todayReviewCount = computed(() => {
  const now = Date.now()
  const due = canonicalReviews.value.filter(item => new Date(item.due_at).getTime() <= now).length
  if (due) return due
  // 与 todayReviewPlan 的兜底口径一致：无排期时未毕业错题计入今日待解决。
  // 【T02 注】ReviewScheduler 上线后本兜底可移除（后端已合并错题级到期项）；
  // 仅当后端一个到期项都没有（如全是 T02 之前入库的历史错题）时才会走到这里。
  return store.errors.filter(e => !e.is_mastered && e.review_state !== 'graduated').length
})

const topErrorPattern = computed(() => {
  const patterns = getErrorPatternDistribution()
  if (patterns.length === 0) return { name: '—', meta: '暂无数据' }
  const top = patterns[0]
  const total = patterns.reduce((s, p) => s + p.count, 0)
  return {
    name: top.name,
    meta: top.percent > 0 ? `${top.percent}% 错误率 · ${top.count} 题` : '暂无数据'
  }
})

const inProgressCount = computed(() => {
  // 待毕业：未掌握 + 不是新错
  return store.errors.filter(e => {
    if (e.is_mastered) return false
    const ml = e.mastery_level || 3
    // 巩固中及以上被认为是接近毕业
    return ml >= 3
  }).length
})

const graduationProgressText = computed(() => {
  const total = store.totalErrors
  const mastered = store.masteredCount
  if (total === 0) return '暂无错题'
  const pct = Math.round((mastered / total) * 100)
  return `${pct}% 已毕业 · ${mastered}/${total}`
})

const weeklyMasteredCount = computed(() => {
  // 本周消灭：基于最近 7 天理解的逻辑
  const now = Date.now()
  const weekAgo = now - 7 * 86400000
  return store.errors.filter(e => {
    if (!e.is_mastered) return false
    try {
      const added = new Date(e.added_at || Date.now()).getTime()
      // 已掌握且最近 7 天内加入的，近似为"本周消灭"
      return added >= weekAgo
    } catch { return false }
  }).length
})

/* ============================================================
 * Error Pattern Analysis (by error reason, not by category)
 * ============================================================ */
function getErrorPatternDistribution() {
  // 将 error_reason 归类为标准错误模式
  const patternMap = {
    '条件遗漏': ['条件遗漏', '条件', '定义域', '边界', '范围'],
    '概念理解偏差': ['概念', '混淆', '理解', '定义', '定理', '公式'],
    '计算错误': ['计算', '运算', '符号', '代数', '数值'],
    '方法选择错误': ['方法', '思路', '方向', '策略', '选择'],
    '审题失误': ['审题', '读题', '理解题意', '漏看', '误读']
  }

  const counts = {}
  const otherKey = '其他类型'

  store.errors.forEach(e => {
    const reason = (e.error_reason || '').toLowerCase()
    let matched = false
    for (const [pattern, keywords] of Object.entries(patternMap)) {
      if (keywords.some(kw => reason.includes(kw.toLowerCase()))) {
        counts[pattern] = (counts[pattern] || 0) + 1
        matched = true
        break
      }
    }
    if (!matched) {
      counts[otherKey] = (counts[otherKey] || 0) + 1
    }
  })

  const total = Object.values(counts).reduce((s, c) => s + c, 0) || 1
  return Object.entries(counts)
    .map(([name, count]) => {
      const percent = Math.round((count / total) * 100)
      let tone = 'terracotta'
      if (percent >= 40) tone = 'terracotta'
      else if (percent >= 20) tone = 'amber'
      else tone = 'sage'
      return { name, count, percent, tone }
    })
    .sort((a, b) => b.percent - a.percent)
    .slice(0, 5)
}

const errorPatterns = computed(() => getErrorPatternDistribution())

const patternSummary = computed(() => {
  const patterns = errorPatterns.value
  if (patterns.length === 0) return ''
  const top = patterns[0]
  const topCount = top.count
  const totalErrors = store.totalErrors
  if (totalErrors === 0) return ''

  if (top.name === '条件遗漏') {
    return `你最近的主要问题并不是公式不会，而是在含参数题目中容易忽略边界条件。建议优先训练条件识别能力。`
  }
  if (top.name === '概念理解偏差') {
    return `你的主要问题集中在概念理解上。建议先回归教材，梳理相关定义和定理，再针对性练习。`
  }
  if (top.name === '计算错误') {
    return `你的计算环节需要加强。建议保持规范的解题步骤，每步仔细核对后再推进。`
  }
  if (topCount >= Math.ceil(totalErrors / 2)) {
    return `「${top.name}」是最突出的错误模式，占比 ${top.percent}%。建议集中解决此类问题。`
  }
  return `你的错误分布较为分散，共有 ${patterns.length} 种错误模式。建议从占比最高的「${top.name}」开始突破。`
})

/* ============================================================
 * Today's Review Plan
 * ============================================================ */
const todayReviewPlan = computed(() => {
  const now = Date.now()
  const scheduled = canonicalReviews.value.filter(item => new Date(item.due_at).getTime() <= now).slice(0, 5).flatMap(review => {
    // T02 ReviewScheduler 上线后，后端 /learning/reviews/due 已合并错题级到期项
    // （source=error_item 携带 error_item_id），优先按 id 直连错题；知识点级排期
    // 保持原有的 KP 码模糊匹配。
    const e = review.error_item_id
      ? store.errors.find(error => error.id === review.error_item_id)
      : store.errors.find(error =>
          (error.knowledge_point_codes || error.categories || []).includes(review.knowledge_point_code)
        )
    if (!e) return []
    return {
      error: e,
      topic: review.knowledge_point_name,
      stage: { label: `第 ${review.review_count + 1} 次`, class: review.stage ? 'consolidating' : 'new' },
      lastReviewText: `已到期 · ${review.interval_days} 天间隔`
    }
  })
  if (scheduled.length) return scheduled
  // 兜底：知识点复习排期尚未生成时（如新学生首次练习答错），未毕业错题直接进入
  // 今日复习，避免"错题有统计但复习计划永远为空"的闭环断点。
  // 【T02 注】ReviewScheduler 上线后本兜底可移除：练习答错已自动写入错题级排期
  // （error_items.next_review_at），到期项会经 /learning/reviews/due 返回。
  // 暂保留仅用于 T02 之前入库、从未被排期的历史错题降级展示；一旦后端返回了
  // 任何到期项（scheduled.length > 0），本分支不会被触发。
  return store.errors
    .filter(e => !e.is_mastered && e.review_state !== 'graduated')
    .slice(0, 5)
    .map(e => ({
      error: e,
      topic: (e.knowledge_point_codes && e.knowledge_point_codes[0]) || (e.categories && e.categories[0]) || '错题回顾',
      stage: { label: '待复习', class: 'new' },
      lastReviewText: `${getLastReviewText(e)} · 尚未排期`
    }))
})

function getLastReviewText(error) {
  if (error.is_mastered) return '已掌握'
  const date = new Date(error.added_at || Date.now())
  const diff = Math.floor((Date.now() - date.getTime()) / 86400000)
  if (diff === 0) return '今天'
  if (diff === 1) return '1 天前'
  return `${diff} 天前`
}

/* ReviewSchedule 是唯一排期事实源；前端只负责本地化分组显示。 */
const reviewSchedule = computed(() => {
  const groups = new Map()
  const now = new Date()
  canonicalReviews.value.forEach(item => {
    const due = new Date(item.due_at)
    const days = Math.floor((due.setHours(0, 0, 0, 0) - new Date(now).setHours(0, 0, 0, 0)) / 86400000)
    const label = days <= 0 ? '今天' : days === 1 ? '明天' : `${days} 天后`
    const group = groups.get(label) || { label, tone: days <= 0 ? 'urgent' : days === 1 ? 'soon' : 'normal', tasks: [] }
    group.tasks.push(`${item.knowledge_point_name} · 第 ${item.review_count + 1} 次复习（${item.interval_days} 天间隔）`)
    groups.set(label, group)
  })
  return [...groups.values()]
})

/* ============================================================
 * Graduation Progress
 * ============================================================ */
const graduationStages = computed(() => {
  const stages = [
    { key: 'new', label: '新错', icon: '📝', count: 0, class: 'new', percent: 0 },
    { key: 'understanding', label: '理解中', icon: '📖', count: 0, class: 'understanding', percent: 0 },
    { key: 'consolidating', label: '巩固中', icon: '🔄', count: 0, class: 'consolidating', percent: 0 },
    { key: 'mastered', label: '稳定掌握', icon: '✓', count: 0, class: 'mastered', percent: 0 }
  ]
  const total = store.totalErrors || 1

  store.errors.forEach(e => {
    if (e.is_mastered) {
      stages[3].count++
    } else if ((e.mastery_level || 3) >= 4) {
      stages[2].count++
    } else {
      try {
        const added = new Date(e.added_at || Date.now()).getTime()
        const days = Math.floor((Date.now() - added) / 86400000)
        if (days <= 3) {
          stages[0].count++
        } else {
          stages[1].count++
        }
      } catch {
        stages[1].count++
      }
    }
  })

  stages.forEach(s => {
    s.percent = Math.round((s.count / total) * 100)
  })

  return stages
})

const graduationStats = computed(() => ({
  total: store.totalErrors,
  mastered: store.masteredCount,
  inProgress: store.unmasteredCount
}))

/* ============================================================
 * All Errors - Tabs
 * ============================================================ */
const filterTabs = computed(() => [
  { key: 'all', label: '全部', count: store.totalErrors },
  { key: 'new', label: '新错', count: getStageCount('new') },
  { key: 'understanding', label: '理解中', count: getStageCount('understanding') },
  { key: 'consolidating', label: '巩固中', count: getStageCount('consolidating') },
  { key: 'mastered', label: '已掌握', count: store.masteredCount }
])

function getStageCount(stageKey) {
  return store.errors.filter(e => {
    if (stageKey === 'mastered') return e.is_mastered
    if (stageKey === 'consolidating') return !e.is_mastered && (e.mastery_level || 3) >= 4
    if (stageKey === 'new') {
      try {
        const added = new Date(e.added_at || Date.now()).getTime()
        return !e.is_mastered && Math.floor((Date.now() - added) / 86400000) <= 3
      } catch { return false }
    }
    if (stageKey === 'understanding') {
      if (e.is_mastered) return false
      if ((e.mastery_level || 3) >= 4) return false
      try {
        const added = new Date(e.added_at || Date.now()).getTime()
        return Math.floor((Date.now() - added) / 86400000) > 3
      } catch { return true }
    }
    return false
  }).length
}

const filteredForTab = computed(() => {
  let list = store.filteredErrors
  if (activeTab.value === 'all') return list
  return list.filter(e => {
    switch (activeTab.value) {
      case 'mastered': return e.is_mastered
      case 'consolidating': return !e.is_mastered && (e.mastery_level || 3) >= 4
      case 'new': {
        try {
          const added = new Date(e.added_at || Date.now()).getTime()
          return !e.is_mastered && Math.floor((Date.now() - added) / 86400000) <= 3
        } catch { return false }
      }
      case 'understanding': {
        if (e.is_mastered) return false
        if ((e.mastery_level || 3) >= 4) return false
        try {
          const added = new Date(e.added_at || Date.now()).getTime()
          return Math.floor((Date.now() - added) / 86400000) > 3
        } catch { return true }
      }
      default: return true
    }
  })
})

function getFilteredIndex(idx) {
  const error = filteredForTab.value[idx]
  if (!error) return idx
  const globalIdx = store.filteredErrors.findIndex(e => e.id === error.id)
  return globalIdx >= 0 ? globalIdx : idx
}

function onFilterChange() {
  // reactive
}

/* ============================================================
 * Knowledge Overview
 * ============================================================ */
const knowledgeOverview = computed(() => {
  const catData = {}
  store.errors.forEach(e => {
    const cats = e.categories || ['其他']
    cats.forEach(c => {
      if (!catData[c]) catData[c] = { total: 0, mastered: 0 }
      catData[c].total++
      if (e.is_mastered) catData[c].mastered++
    })
  })
  return Object.entries(catData)
    .map(([name, data]) => {
      const percent = data.total > 0 ? Math.round((data.mastered / data.total) * 100) : 0
      let tone = 'terracotta'
      if (percent >= 70) tone = 'sage'
      else if (percent >= 45) tone = 'amber'
      return { name, percent, tone, total: data.total, mastered: data.mastered }
    })
    .sort((a, b) => a.name.localeCompare(b.name, 'zh'))
})

const learningTips = computed(() => {
  const tips = []
  const sorted = [...knowledgeOverview.value].sort((a, b) => a.percent - b.percent)
  if (sorted.length > 0) {
    const weakest = sorted[0]
    tips.push({ icon: '🎯', text: `「${weakest.name}」是当前最薄弱环节，需优先巩固` })
  }
  if (store.unmasteredCount > 0) {
    tips.push({ icon: '⏰', text: `有 ${store.unmasteredCount} 道错题等待复习，建议集中处理` })
  }
  const avg = knowledgeOverview.value.length > 0
    ? Math.round(knowledgeOverview.value.reduce((s, c) => s + c.percent, 0) / knowledgeOverview.value.length)
    : 0
  tips.push({ icon: '💡', text: avg >= 60 ? `整体掌握率 ${avg}%，可适度提高难度` : `整体掌握率 ${avg}%，建议加强基础题练习` })
  return tips
})

/* ============================================================
 * Actions
 * ============================================================ */
function scrollToAll() {
  activeTab.value = 'all'
  nextTick(() => {
    if (allErrorsRef.value) {
      allErrorsRef.value.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  })
}

function handleTrainClick() {
  const due = canonicalReviews.value[0]
  const code = due?.knowledge_point_code || store.errors.find(item => (item.knowledge_point_codes || item.categories || []).length)?.knowledge_point_codes?.[0] || store.errors.find(item => item.categories?.length)?.categories?.[0]
  if (!code) return ElMessage.info('暂无可用于专项训练的真实知识点证据')
  router.push({ path: '/apply/practice', query: { knowledge_point: code } })
}

function openDetail(idx) {
  if (typeof idx === 'number') {
    detailIndex.value = idx
  }
  detailVisible.value = true
}

function openDetailForItem(error) {
  const idx = store.filteredErrors.findIndex(e => e.id === error.id)
  if (idx >= 0) {
    detailIndex.value = idx
    detailVisible.value = true
  }
}

function closeDetail() {
  detailVisible.value = false
  detailIndex.value = -1
}

function navigateDetail(dir) {
  const newIdx = detailIndex.value + dir
  if (newIdx >= 0 && newIdx < store.filteredErrors.length) {
    detailIndex.value = newIdx
  }
}

function startDailyReview() {
  const first = canonicalReviews.value.find(item => new Date(item.due_at).getTime() <= Date.now())
  if (first) {
    // T02：错题级到期项（source=error_item）不是知识点级 ReviewSchedule 行，
    // 不带 review_schedule_id（complete_review 只接受整型排期 id）；
    // 学生重做该知识点练习后，作答经练习链路回流（LearningRecord + 复习排期更新）。
    if (first.source === 'error_item') {
      router.push({ path: '/apply/practice', query: { knowledge_point: first.knowledge_point_code } })
      return
    }
    router.push({ path: '/apply/practice', query: {
      knowledge_point: first.knowledge_point_code,
      review_schedule_id: first.id,
      review_kind: 'spaced_correct',
    } })
    return
  }
  // 兜底：无到期排期时，从第一道未毕业错题出发做巩固练习（未知 review_kind
  // 在后端按 regular 处理，契约安全）。
  // 【T02 注】ReviewScheduler 上线后本兜底可移除：新错题都会被自动排期，
  // 到期项由 /learning/reviews/due 返回；本分支仅覆盖历史未排期错题。
  const error = store.errors.find(e => !e.is_mastered && e.review_state !== 'graduated')
  if (!error) return ElMessage.info('今天没有到期复习任务')
  const kp = (error.knowledge_point_codes && error.knowledge_point_codes[0]) || (error.categories && error.categories[0])
  ElMessage.info('该错题尚未生成复习排期，先做一次相关知识点的巩固练习')
  router.push({ path: '/apply/practice', query: kp ? { knowledge_point: kp, review_kind: 'spaced_correct' } : {} })
}

function handleDelete(error) {
  const name = (error.display_question || error.question || '').substring(0, 50)
  ElMessageBox.confirm(`确定要删除这道错题吗？\n\n${name}...`, '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(async () => {
    try { await store.deleteError(error.id); ElMessage.success('错题已删除') }
    catch { ElMessage.error('删除失败，数据库未发生变化，请重试') }
  }).catch(() => {})
}

function handleDeleteFromDetail() {
  const error = detailError.value
  if (!error) return
  handleDelete(error)
  closeDetail()
}

function handleKeydown(e) {
  if (!detailVisible.value) return
  if (e.key === 'Escape') closeDetail()
  else if (e.key === 'ArrowLeft') navigateDetail(-1)
  else if (e.key === 'ArrowRight') navigateDetail(1)
}

/* ============================================================
 * Lifecycle
 * ============================================================ */
onMounted(async () => {
  await Promise.allSettled([
    store.loadErrors().catch(() => ElMessage.error('错题本加载失败，请检查网络后重试')),
    getDueReviews(true).then(({ data }) => { canonicalReviews.value = data.items || [] }).catch(() => { canonicalReviews.value = [] }),
  ])
  const errorId = route.params.errorId
  if (errorId) {
    const idx = store.filteredErrors.findIndex(e => e.id === errorId)
    if (idx >= 0) {
      detailIndex.value = idx
      detailVisible.value = true
    }
  }
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

/* ============================================================
 * Main Layout
 * ============================================================ */
.error-book-view {
  flex: 1;
  overflow-y: auto;
  max-width: 1280px;
  width: 100%;
  margin: 0 auto;
  padding: 28px 32px 48px;

  &::-webkit-scrollbar {
    width: 6px;
    &-thumb {
      background: rgba(148, 163, 184, 0.3);
      border-radius: var(--radius-pill);
      &:hover { background: rgba(148, 163, 184, 0.5); }
    }
  }
}

/* ============================================================
 * Page Header
 * ============================================================ */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 28px;
  gap: 20px;
}

.page-header-left {
  flex: 1;
  min-width: 0;
}

.page-header-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 6px;
  letter-spacing: -0.02em;
  line-height: 1.3;
}

.page-header-subtitle {
  font-size: 14px;
  color: var(--text-tertiary);
  margin: 0;
  line-height: 1.5;
}

.page-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding-top: 2px;
}

.back-link {
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  font-weight: 500;
  padding: 7px 16px;
  border-radius: var(--radius-pill);
  transition: all var(--transition-fast);
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  &:hover { color: var(--text-primary); border-color: var(--border-strong); }
}

.start-review-btn {
  padding: 8px 20px;
  border-radius: var(--radius-pill);
  border: none;
  background: var(--accent);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;
  &:hover { background: var(--accent-hover); transform: translateY(-1px); }
  &:active { transform: translateY(0); }
}

/* ============================================================
 * KPI Row
 * ============================================================ */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.kpi-card {
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 14px 18px;
  transition: all var(--transition-fast);
  &:hover { border-color: var(--border-strong); }

  &.amber .kpi-value { color: var(--warning); }
  &.terracotta .kpi-value { color: var(--danger); }
  &.ink .kpi-value { color: var(--text-primary); }
  &.sage .kpi-value { color: var(--success); }
}

.kpi-value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.02em;
  margin-bottom: 2px;
}

.kpi-label {
  font-size: 13px;
  color: var(--text-tertiary);
  font-weight: 500;
  margin-bottom: 4px;
}

.kpi-meta {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 400;
}

/* ============================================================
 * Content Grid (2-column)
 * ============================================================ */
.content-grid-2col {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}

/* ── Panel Base ── */
.panel {
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: -0.01em;
}

.panel-link {
  font-size: 13px;
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  font-family: inherit;
  padding: 0;
  transition: color var(--transition-fast);
  &:hover { color: var(--accent); }
}

.panel-range {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.panel-body {
  padding: 16px 20px;
  flex: 1;
}

.panel-empty {
  text-align: center;
  padding: 32px 0;
  color: var(--text-tertiary);
  .empty-icon { font-size: 28px; display: block; margin-bottom: 6px; }
  .empty-text { font-size: 14px; margin: 0 0 6px; }
  .empty-hint { font-size: 13px; color: var(--text-tertiary); margin: 0; }
}

/* ============================================================
 * Today's Review Plan
 * ============================================================ */
.review-plan-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.review-plan-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  &:hover { background: var(--surface-hover); }
}

.plan-rank {
  width: 30px;
  height: 30px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
}

.plan-info {
  flex: 1;
  min-width: 0;
}

.plan-title {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 3px;
}

.plan-cat {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
}

.plan-sep {
  font-size: 13px;
  color: var(--text-tertiary);
  opacity: 0.5;
}

.plan-topic {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.plan-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--text-tertiary);
  .plan-dot { opacity: 0.4; }
}

.plan-action {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.plan-stage-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: var(--radius-pill);

  &.new { color: var(--warning); background: rgba(200, 145, 61, 0.12); }
  &.understanding { color: var(--accent); background: var(--accent-soft); }
  &.consolidating { color: var(--teal); background: rgba(65, 137, 125, 0.12); }
}

.plan-arrow {
  font-size: 14px;
  color: var(--text-tertiary);
  transition: transform var(--transition-fast);
}

.review-plan-item:hover .plan-arrow {
  color: var(--accent);
  transform: translateX(2px);
}

/* ============================================================
 * AI Error Pattern
 * ============================================================ */
.pattern-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}

.pattern-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.pattern-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pattern-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.pattern-percent {
  font-size: 13px;
  font-weight: 700;
  &.terracotta { color: var(--danger); }
  &.amber { color: var(--warning); }
  &.sage { color: var(--success); }
}

.pattern-bar {
  height: 6px;
  background: var(--border-subtle);
  border-radius: 3px;
  overflow: hidden;
}

.pattern-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease-out;
  &.terracotta { background: var(--danger); }
  &.amber { background: var(--warning); }
  &.sage { background: var(--mastered); }
}

.pattern-summary {
  padding: 10px 14px;
  background: var(--surface-muted);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  margin-bottom: 14px;
}

.summary-text {
  font-size: 13.5px;
  line-height: 1.7;
  color: var(--text-secondary);
}

.pattern-action {
  text-align: center;
}

.pattern-train-btn {
  padding: 8px 20px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--accent);
  background: transparent;
  color: var(--accent);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
  &:hover {
    background: var(--accent-soft);
    border-color: var(--accent-hover);
  }
}

/* ============================================================
 * Review Schedule Timeline
 * ============================================================ */
.schedule-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.timeline-item {
  display: flex;
  gap: 14px;
  min-height: 52px;
}

.timeline-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 16px;
  flex-shrink: 0;
  padding-top: 4px;
}

.timeline-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  flex-shrink: 0;
  &.urgent { background: var(--warning); }
  &.soon { background: var(--accent); }
  &.normal { background: var(--text-tertiary); }
}

.timeline-line {
  width: 2px;
  flex: 1;
  background: var(--border-subtle);
  min-height: 24px;
  margin-top: 4px;
}

.timeline-content {
  flex: 1;
  padding-bottom: 16px;
}

.timeline-label {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.timeline-tasks {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.timeline-task {
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--surface-muted);
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-subtle);
}

.timeline-empty {
  font-size: 12px;
  color: var(--text-tertiary);
  font-style: italic;
}

/* ============================================================
 * Graduation Progress
 * ============================================================ */
.graduation-flow {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.grad-stage {
  display: flex;
  align-items: center;
  gap: 12px;
}

.grad-icon-wrap {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 16px;

  &.new { background: rgba(200, 145, 61, 0.12); }
  &.understanding { background: var(--accent-soft); }
  &.consolidating { background: rgba(65, 137, 125, 0.12); }
  &.mastered { background: rgba(95, 148, 124, 0.12); }
}

.grad-info {
  display: flex;
  flex-direction: column;
  min-width: 68px;
}

.grad-label {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.grad-count {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.grad-bar-wrap {
  flex: 1;
  height: 6px;
  background: var(--border-subtle);
  border-radius: 3px;
  overflow: hidden;
}

.grad-bar {
  height: 100%;
  background: var(--accent);
  border-radius: 3px;
  transition: width 0.5s ease-out;
}

/* ============================================================
 * All Errors Panel
 * ============================================================ */
.all-errors-panel {
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.all-errors-header {
  padding: 18px 20px 14px;
}

.section-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 14px;
  letter-spacing: -0.01em;
}

.compact-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.filter-search {
  position: relative;
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 200px;
  .search-icon {
    position: absolute;
    left: 12px;
    font-size: 13px;
    opacity: 0.5;
  }
}

.search-input {
  width: 100%;
  padding: 8px 14px 8px 34px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  font-size: 14px;
  font-family: inherit;
  background: var(--surface);
  color: var(--text-primary);
  outline: none;
  transition: border-color var(--transition-fast);
  &:focus { border-color: var(--accent); }
  &::placeholder { color: var(--text-tertiary); }
}

.filter-select {
  padding: 8px 12px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-md);
  font-size: 13px;
  font-family: inherit;
  background: var(--surface);
  color: var(--text-primary);
  outline: none;
  cursor: pointer;
  transition: border-color var(--transition-fast);
  &:focus { border-color: var(--accent); }
}

.filter-tabs {
  display: flex;
  gap: 4px;
  background: var(--surface-muted);
  border-radius: var(--radius-md);
  padding: 3px;
  overflow-x: auto;
  flex-shrink: 0;
}

.filter-tab {
  padding: 6px 14px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all var(--transition-fast);
  white-space: nowrap;
  &:hover { color: var(--text-primary); }
  &.active {
    background: var(--surface);
    color: var(--text-primary);
    box-shadow: var(--shadow-sm);
  }
  .tab-count {
    font-size: 11px;
    background: var(--border-subtle);
    color: var(--text-tertiary);
    padding: 1px 6px;
    border-radius: var(--radius-pill);
    font-weight: 600;
  }
  &.active .tab-count {
    background: var(--accent);
    color: #fff;
  }
}

/* ============================================================
 * All Errors Grid
 * ============================================================ */
.all-errors-grid {
  display: grid;
  grid-template-columns: minmax(0, 3fr) 260px;
  border-top: 1px solid var(--border-subtle);
}

.errors-col {
  border-right: 1px solid var(--border-subtle);
}

.errors-list {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 200px;
  position: relative;
}

/* ============================================================
 * Knowledge Sidebar
 * ============================================================ */
.knowledge-sidebar {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.knowledge-card {
  background: var(--surface-muted);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.knowledge-header {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-subtle);
}

.knowledge-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.knowledge-body {
  padding: 12px 14px;
}

.knowledge-item {
  margin-bottom: 10px;
  &:last-child { margin-bottom: 0; }
}

.knowledge-name-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.knowledge-name {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
}

.knowledge-percent {
  font-size: 13px;
  font-weight: 700;
  &.sage { color: var(--success); }
  &.amber { color: var(--warning); }
  &.terracotta { color: var(--danger); }
}

.knowledge-bar {
  height: 4px;
  background: var(--border-subtle);
  border-radius: 2px;
  overflow: hidden;
}

.knowledge-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s ease-out;
  &.sage { background: var(--mastered); }
  &.amber { background: var(--warning); }
  &.terracotta { background: var(--danger); }
}

.knowledge-card.tips .knowledge-body { padding: 12px 14px; }

.tips-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tip-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.tip-icon { font-size: 14px; flex-shrink: 0; }
.tip-text { flex: 1; }

/* ============================================================
 * Empty State
 * ============================================================ */
.empty-state {
  text-align: center;
  padding: 60px 20px;
  .empty-icon { font-size: 48px; margin-bottom: 12px; color: var(--text-tertiary); }
  .empty-text { font-size: 16px; color: var(--text-secondary); font-weight: 600; margin-bottom: 6px; }
  .empty-hint { font-size: 13px; color: var(--text-tertiary); line-height: 1.6; }
}

/* ============================================================
 * List Animations
 * ============================================================ */
.list-item-enter-active {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.list-item-leave-active {
  transition: all 0.25s ease;
  position: absolute;
  width: calc(100% - 40px);
}
.list-item-enter-from {
  opacity: 0;
  transform: translateY(20px) scale(0.98);
}
.list-item-leave-to {
  opacity: 0;
  transform: translateX(-30px) scale(0.95);
}

/* ============================================================
 * Responsive
 * ============================================================ */
@media (max-width: 1200px) {
  .content-grid-2col {
    grid-template-columns: 1fr;
  }

  .kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }

  .all-errors-grid {
    grid-template-columns: 1fr;
  }

  .errors-col {
    border-right: none;
    border-bottom: 1px solid var(--border-subtle);
  }

  .knowledge-sidebar {
    flex-direction: row;
  }

  .knowledge-card {
    flex: 1;
  }
}

@media (max-width: 900px) {
  .error-book-view {
    padding: 20px 20px 40px;
  }

  .page-header {
    flex-direction: column;
    gap: 14px;
  }

  .page-header-title { font-size: 22px; }

  .kpi-row { gap: 12px; }
  .kpi-card { padding: 12px 14px; }
  .kpi-value { font-size: 22px; }

  .compact-filter {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }

  .filter-search { min-width: auto; }

  .knowledge-sidebar { flex-direction: column; }
  .empty-state { padding: 40px 16px; }
}

@media (max-width: 600px) {
  .error-book-view {
    padding: 16px 14px 32px;
  }

  .page-header-right {
    flex-direction: column;
    align-items: stretch;
    width: 100%;
  }

  .back-link,
  .start-review-btn {
    text-align: center;
  }

  .kpi-row {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }

  .kpi-value { font-size: 20px; }
}
</style>
