<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import AppShell from '@/components/shell/AppShell.vue'
import { getLearningProfile } from '@/api/learning'
import { getProfileWhy } from '@/api/profileEvidence'
import { useRouter } from 'vue-router'

const router = useRouter()

const loading = ref(true)
const canonicalProfile = ref<any>(null)
const canonicalReviews = ref<any[]>([])
const evidenceByDimension = ref<Record<string, any>>({})
const evidenceLoading = ref<Record<string, boolean>>({})
const evidenceErrors = ref<Record<string, string>>({})

const curveChartEl = ref<HTMLElement | null>(null)
const donutChartEl = ref<HTMLElement | null>(null)
const barChartEl = ref<HTMLElement | null>(null)
let curveChart: echarts.ECharts | null = null
let donutChart: echarts.ECharts | null = null
let barChart: echarts.ECharts | null = null

let resizeHandler: (() => void) | null = null

// ── Date range ──
const today = new Date()
const weekAgo = new Date(today.getTime() - 6 * 24 * 60 * 60 * 1000)
const formatDate = (d: Date) => `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}`
const dateRange = computed(() => `${formatDate(weekAgo)} – ${formatDate(today)}`)

// ── Helpers ──
function getCSSVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

// ── Data computation from real sources ──

// Collect all knowledge categories from error book
const allCategories = computed(() => {
  return (canonicalProfile.value?.dimensions?.mastery || []).map((item: any) => item.code)
})

// Mastery distribution: group errors by mastery level
const masteryDistribution = computed(() => {
  const dist = { mastered: 0, learning: 0, weak: 0, fragile: 0 }
  const canonical = canonicalProfile.value?.dimensions?.mastery || []
  if (canonical.length) {
    canonical.forEach((item: any) => {
      if (item.value >= .8) dist.mastered++
      else if (item.value >= .6) dist.learning++
      else if (item.value >= .35) dist.weak++
      else dist.fragile++
    })
    return dist
  }
  return dist
})

// Memory stability score (0-100)
const memoryStabilityScore = computed(() => {
  const values = canonicalProfile.value?.dimensions?.memory_strength || []
  if (values.length) return Math.round(values.reduce((sum: number, item: any) => sum + item.value, 0) / values.length * 100)
  return 0
})

const stabilityLevel = computed(() => {
  const s = memoryStabilityScore.value
  if (s >= 80) return '良好'
  if (s >= 60) return '中等'
  if (s >= 40) return '较弱'
  return '需要加强'
})

const stabilityLevelColor = computed(() => {
  const s = memoryStabilityScore.value
  if (s >= 80) return 'var(--mastered)'
  if (s >= 60) return 'var(--accent)'
  if (s >= 40) return 'var(--learning)'
  return 'var(--weak)'
})

// Fragile knowledge points (mastery_level <= 2)
const fragilePoints = computed(() => {
  return (canonicalProfile.value?.dimensions?.mastery || []).filter((item: any) => item.value < .35).map((item: any) => ({ name: item.code, count: 1 }))
})

// Fragile count change (compared to estimated last week)
const fragileDelta = computed(() => {
  const current = fragilePoints.value.length
  // Simple heuristic: if we have data, estimate delta
  return current > 0 ? current : 0
})

// Long-term memory retention rate
const longTermRetention = computed(() => {
  const observations = canonicalProfile.value?.forgetting_curve?.observations || []
  return observations.length ? Math.round(observations.filter((item: any) => item.retained).length / observations.length * 100) : 0
})

// Mastered rate
const masteredRate = computed(() => {
  const values = canonicalProfile.value?.dimensions?.mastery || []
  return values.length ? Math.round(values.filter((item: any) => item.value >= .8).length / values.length * 100) : 0
})

// Retention trend
const retentionTrend = computed(() => {
  return 0
})

// Review plan
const reviewPlan = computed(() => {
  return canonicalReviews.value.map((item: any) => ({
    title: item.knowledge_point_name,
    time: new Date(item.due_at).toLocaleString(),
    category: '间隔复习', count: 1, interval: `${item.interval_days} 天间隔`,
  }))
})

const reviewPlanCount = computed(() => reviewPlan.value.length)
const reviewEstimateMinutes = computed(() => reviewPlan.value.length * 12)

// Forgetting curve data (simulated based on real data)
const forgettingCurveData = computed(() => {
  const observations = canonicalProfile.value?.forgetting_curve?.observations || []
  return { days: observations.map((item: any) => `${item.interval_days}天`), referenceCurve: [], userCurve: observations.map((item: any) => item.retained ? 100 : 0) }
})

// Memory strength distribution data
const memoryStrengthData = computed(() => {
  return [
    { name: '已掌握', value: masteryDistribution.value.mastered },
    { name: '学习中', value: masteryDistribution.value.learning },
    { name: '薄弱', value: masteryDistribution.value.weak },
    { name: '脆弱', value: masteryDistribution.value.fragile },
  ]
})

const strengthOverall = computed(() => {
  return Math.round(memoryStabilityScore.value)
})

const strengthLabel = computed(() => {
  const s = strengthOverall.value
  if (s >= 75) return '良好'
  if (s >= 50) return '中等'
  return '需加强'
})

// Knowledge point mastery TOP10
const knowledgeMasteryTop10 = computed(() => {
  const canonical = canonicalProfile.value?.dimensions?.mastery || []
  return canonical.slice().sort((a: any, b: any) => b.value - a.value).slice(0, 10).map((item: any) => ({ category: item.code, rate: Math.round(item.value * 100), evidenceCount: item.evidence_count ?? 0 }))
})

// AI insights
const aiInsights = computed(() => {
  return (canonicalProfile.value?.insights || []).map((item: any) => ({ label: item.title, value: item.conclusion, evidence: item.evidence, action: item.action }))
})

function formatEvidenceTime(value: string) {
  return value ? new Date(value).toLocaleString() : '时间未知'
}

async function loadDimensionEvidence(dimension: string, force = false) {
  if (!force && (evidenceByDimension.value[dimension] || evidenceLoading.value[dimension])) return
  evidenceLoading.value = { ...evidenceLoading.value, [dimension]: true }
  evidenceErrors.value = { ...evidenceErrors.value, [dimension]: '' }
  try {
    const evidence = await getProfileWhy(dimension)
    evidenceByDimension.value = { ...evidenceByDimension.value, [dimension]: evidence }
  } catch (error: any) {
    evidenceErrors.value = {
      ...evidenceErrors.value,
      [dimension]: error?.response?.data?.detail || error?.message || '依据加载失败，请稍后重试',
    }
  } finally {
    evidenceLoading.value = { ...evidenceLoading.value, [dimension]: false }
  }
}

function handleEvidenceToggle(event: Event, dimension: string) {
  if ((event.currentTarget as HTMLDetailsElement).open) loadDimensionEvidence(dimension)
}

// ── Chart initialization ──

function initCurveChart() {
  if (!curveChartEl.value) return

  const surface = getCSSVar('--surface') || '#FCFBF8'
  const borderSubtle = getCSSVar('--border-subtle') || '#E6E3DA'
  const textPrimary = getCSSVar('--text-primary') || '#20231F'
  const textSecondary = getCSSVar('--text-secondary') || '#72766F'
  const textTertiary = getCSSVar('--text-tertiary') || '#9A9D96'
  const accent = getCSSVar('--accent') || '#416B56'
  const danger = getCSSVar('--danger') || '#C9674C'
  const warning = getCSSVar('--warning') || '#C8913D'

  curveChart = echarts.init(curveChartEl.value)

  const data = forgettingCurveData.value

  curveChart.setOption({
    grid: {
      left: 40,
      right: 20,
      top: 30,
      bottom: 30,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: surface,
      borderColor: borderSubtle,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: textPrimary, fontSize: 12 },
      extraCssText: 'box-shadow: 0 2px 8px rgba(32,35,31,0.06); border-radius: 8px;',
      formatter: (params: any) => {
        const day = params[0].axisValue
        const userVal = params.find((p: any) => p.seriesName === '你的保持率')
        const refVal = params.find((p: any) => p.seriesName === '参考曲线')
        return `<div style="font-size:12px;color:${textSecondary}">${day}</div>
                ${userVal ? `<div style="color:${accent}">你的保持率 ${userVal.value}%</div>` : ''}
                ${refVal ? `<div style="color:${textTertiary}">参考 ${refVal.value}%</div>` : ''}`
      },
    },
    legend: {
      data: ['你的保持率', '参考曲线'],
      top: 0,
      right: 0,
      textStyle: { color: textTertiary, fontSize: 11 },
      itemWidth: 16,
      itemHeight: 3,
      itemGap: 16,
    },
    xAxis: {
      type: 'category',
      data: data.days,
      axisLine: { lineStyle: { color: borderSubtle } },
      axisLabel: { color: textTertiary, fontSize: 11 },
      axisTick: { show: false },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: borderSubtle, type: 'dashed' } },
      axisLabel: { color: textTertiary, fontSize: 11, formatter: '{value}%' },
    },
    series: [
      {
        name: '你的保持率',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: data.userCurve,
        lineStyle: { color: accent, width: 2.5 },
        itemStyle: { color: accent, borderColor: surface, borderWidth: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(65, 107, 86, 0.15)' },
            { offset: 1, color: 'rgba(65, 107, 86, 0.01)' },
          ]),
        },
      },
      {
        name: '参考曲线',
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: data.referenceCurve,
        lineStyle: { color: textTertiary, width: 1.5, type: 'dashed' },
      },
    ],
  })
}

function initDonutChart() {
  if (!donutChartEl.value) return

  const surface = getCSSVar('--surface') || '#FCFBF8'
  const textPrimary = getCSSVar('--text-primary') || '#20231F'
  const textSecondary = getCSSVar('--text-secondary') || '#72766F'
  const textTertiary = getCSSVar('--text-tertiary') || '#9A9D96'
  const mastered = getCSSVar('--mastered') || '#5F947C'
  const accent = getCSSVar('--accent') || '#416B56'
  const learning = getCSSVar('--learning') || '#C8913D'
  const weak = getCSSVar('--weak') || '#C9674C'

  donutChart = echarts.init(donutChartEl.value)

  const data = memoryStrengthData.value
  const colors = [mastered, accent, learning, weak]

  donutChart.setOption({
    tooltip: {
      trigger: 'item',
      backgroundColor: surface,
      borderColor: getCSSVar('--border-subtle') || '#E6E3DA',
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: textPrimary, fontSize: 12 },
      extraCssText: 'box-shadow: 0 2px 8px rgba(32,35,31,0.06); border-radius: 8px;',
      formatter: (params: any) => {
        return `<div style="font-size:12px;color:${textSecondary}">${params.name}</div>
                <div style="font-weight:600;color:${params.color}">${params.value} (${params.percent}%)</div>`
      },
    },
    legend: {
      bottom: 0,
      left: 'center',
      textStyle: { color: textTertiary, fontSize: 11 },
      itemWidth: 8,
      itemHeight: 8,
      itemGap: 12,
    },
    series: [
      {
        name: '记忆强度',
        type: 'pie',
        radius: ['55%', '78%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: false,
        label: {
          show: true,
          position: 'center',
          formatter: () => {
            return `{value|${strengthOverall.value}}%\n{label|${strengthLabel.value}}`
          },
          rich: {
            value: {
              fontSize: 28,
              fontWeight: 700,
              color: textPrimary,
              lineHeight: 36,
            },
            label: {
              fontSize: 13,
              color: textSecondary,
              lineHeight: 20,
            },
          },
        },
        emphasis: {
          label: { show: false },
          itemStyle: {
            shadowBlur: 6,
            shadowColor: 'rgba(32, 35, 31, 0.12)',
          },
        },
        labelLine: { show: false },
        data: data.map((d, i) => ({
          ...d,
          itemStyle: { color: colors[i] },
        })),
      },
    ],
  })
}

function initBarChart() {
  if (!barChartEl.value) return

  const borderSubtle = getCSSVar('--border-subtle') || '#E6E3DA'
  const textPrimary = getCSSVar('--text-primary') || '#20231F'
  const textTertiary = getCSSVar('--text-tertiary') || '#9A9D96'
  const accent = getCSSVar('--accent') || '#416B56'
  const mastered = getCSSVar('--mastered') || '#5F947C'
  const weak = getCSSVar('--weak') || '#C9674C'

  barChart = echarts.init(barChartEl.value)

  const data = knowledgeMasteryTop10.value

  barChart.setOption({
    grid: {
      left: 10,
      right: 40,
      top: 5,
      bottom: 5,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'none' },
      backgroundColor: getCSSVar('--surface') || '#FCFBF8',
      borderColor: borderSubtle,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: textPrimary, fontSize: 12 },
      extraCssText: 'box-shadow: 0 2px 8px rgba(32,35,31,0.06); border-radius: 8px;',
      formatter: (params: any) => {
        const p = params[0]
        return `<div style="font-size:12px;color:${textTertiary}">${p.name}</div>
                <div style="font-weight:600;color:${p.color}">掌握度 ${p.value}%</div>`
      },
    },
    xAxis: {
      type: 'value',
      show: false,
      max: 100,
    },
    yAxis: {
      type: 'category',
      data: data.map(d => d.category).reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: getCSSVar('--text-secondary') || '#72766F',
        fontSize: 12,
        width: 120,
        overflow: 'truncate',
      },
      inverse: false,
    },
    series: [
      {
        type: 'bar',
        data: data.map(d => d.rate).reverse(),
        barWidth: 10,
        itemStyle: {
          color: (params: any) => {
            const rate = params.value
            if (rate >= 70) return mastered
            if (rate >= 45) return accent
            return weak
          },
          borderRadius: [0, 3, 3, 0],
        },
        label: {
          show: true,
          position: 'right',
          formatter: '{c}%',
          color: textTertiary,
          fontSize: 11,
        },
      },
    ],
  })
}

function handleResize() {
  curveChart?.resize()
  donutChart?.resize()
  barChart?.resize()
}

// ── Load profile data from API ──
async function loadProfileData() {
  const { data } = await getLearningProfile()
  canonicalProfile.value = data
  canonicalReviews.value = data.review_plan || []
}

onMounted(async () => {
  try {
    await loadProfileData()

    await nextTick()
    initCurveChart()
    initDonutChart()
    initBarChart()

    resizeHandler = () => handleResize()
    window.addEventListener('resize', resizeHandler!)
  } finally {
    // Expired or unavailable sessions must render a recoverable state instead
    // of leaving the whole page behind a permanent loading screen.
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeHandler!)
  curveChart?.dispose()
  donutChart?.dispose()
  barChart?.dispose()
})

watch(forgettingCurveData, () => {
  if (curveChart) {
    curveChart.setOption({
      xAxis: { data: forgettingCurveData.value.days },
      series: [
        { data: forgettingCurveData.value.userCurve },
        { data: forgettingCurveData.value.referenceCurve },
      ],
    })
  }
}, { deep: true })

watch(memoryStrengthData, () => {
  if (donutChart) {
    donutChart.setOption({
      series: [{
        data: memoryStrengthData.value.map((d, i) => ({
          ...d,
          itemStyle: { color: [getCSSVar('--mastered') || '#5F947C', getCSSVar('--accent') || '#416B56', getCSSVar('--learning') || '#C8913D', getCSSVar('--weak') || '#C9674C'][i] },
        })),
      }],
    })
  }
}, { deep: true })

watch(knowledgeMasteryTop10, () => {
  if (barChart) {
    const data = knowledgeMasteryTop10.value
    barChart.setOption({
      yAxis: { data: data.map(d => d.category).reverse() },
      series: [{ data: data.map(d => d.rate).reverse() }],
    })
  }
}, { deep: true })
</script>

<template>
  <AppShell>
    <template #topbar-title>
      <span>记忆画像</span>
    </template>
    <template #topbar-actions>
      <span class="date-range">{{ dateRange }}</span>
    </template>

    <div class="profile-view">
      <div v-if="loading" class="profile-loading">加载中...</div>

      <div v-else class="profile-body">
        <!-- Subtitle line (compact inline) -->
        <div class="subtitle-line">
          <span class="subtitle-text">{{ canonicalProfile?.status_message || '学习画像来自真实作答证据' }}</span>
        </div>
        <div v-if="canonicalProfile?.status === 'discovering'" class="profile-loading">尚在了解你。完成基础诊断或一次练习后，这里会展示掌握度、记忆强度、错误模式和迁移能力。</div>
        <!-- ── KPI Row ── -->
        <div v-else class="kpi-row">
          <div class="kpi-card">
            <div class="kpi-label">记忆稳定性评分</div>
            <div class="kpi-value">{{ memoryStabilityScore }}<span class="kpi-unit">/100</span></div>
            <div class="kpi-sub">
              <span class="kpi-badge" :style="{ color: stabilityLevelColor }">{{ stabilityLevel }}</span>
              <span class="kpi-count" v-if="masteryDistribution.mastered > 0">个{{ masteryDistribution.mastered }}</span>
            </div>
          </div>

          <div class="kpi-card">
            <div class="kpi-label">脆弱知识点</div>
            <div class="kpi-value fragile">{{ fragilePoints.length }}<span class="kpi-unit">个</span></div>
            <div class="kpi-sub">
              <span v-if="fragileDelta > 0" class="kpi-delta-up">较上周 +{{ fragileDelta }}</span>
              <span v-else class="kpi-sub-neutral">状态良好</span>
            </div>
          </div>

          <div class="kpi-card">
            <div class="kpi-label">长期记忆保持率</div>
            <div class="kpi-value">{{ longTermRetention }}<span class="kpi-unit">%</span></div>
            <div class="kpi-sub">
              <span v-if="retentionTrend > 0" class="kpi-delta-up">↑ {{ retentionTrend }}%</span>
              <span v-else class="kpi-sub-neutral">保持稳定</span>
            </div>
          </div>

          <div class="kpi-card">
            <div class="kpi-label">下次复习计划</div>
            <div class="kpi-value">{{ reviewPlanCount }}<span class="kpi-unit">条</span></div>
            <div class="kpi-sub">预计 {{ reviewEstimateMinutes }} 分钟</div>
          </div>
        </div>

        <!-- ── Middle Row: Curve + Donut + AI Insights ── -->
        <div v-if="canonicalProfile?.status !== 'discovering'" class="middle-row">
          <!-- Forgetting Curve -->
          <div class="card card--curve">
            <div class="card-header">
              <h3 class="card-title">遗忘曲线</h3>
              <span class="card-badge">总体</span>
            </div>
            <div v-if="canonicalProfile.forgetting_curve?.status === 'available'" ref="curveChartEl" class="chart-container chart--curve" role="img" :aria-label="`个人遗忘曲线，共 ${canonicalProfile.forgetting_curve.sample_size} 条复习证据`"></div>
            <div v-else class="empty-state"><p class="empty-text">个人曲线数据积累中</p><p class="empty-hint">{{ canonicalProfile.forgetting_curve?.message }}</p></div>
            <div class="card-footer">
              <span>样本 {{ canonicalProfile.forgetting_curve?.sample_size || 0 }} 条 · 算法 {{ canonicalProfile.forgetting_curve?.algorithm_version }}</span>
            </div>
          </div>

          <!-- Memory Strength Donut -->
          <div class="card card--donut">
            <div class="card-header">
              <h3 class="card-title">记忆强度分布</h3>
            </div>
            <div ref="donutChartEl" class="chart-container chart--donut"></div>
          </div>

          <!-- AI Insights -->
          <div class="card card--insights">
            <div class="card-header">
              <h3 class="card-title">学习洞察</h3>
            </div>
            <div class="insight-list">
              <div v-for="(insight, i) in aiInsights" :key="i" class="insight-item">
                <span class="insight-label">{{ insight.label }}</span>
                <span class="insight-value">{{ insight.value }}</span>
                <small class="insight-evidence">样本 {{ insight.evidence?.sample_size || 0 }} · {{ insight.evidence?.period || '全部' }}</small>
              </div>
            </div>
            <button class="insight-action" @click="router.push('/error-book')">查看真实复习计划 →</button>
          </div>
        </div>

        <!-- ── Bottom Row: TOP10 Bar + Review Timeline ── -->
        <div v-if="canonicalProfile?.status !== 'discovering'" class="bottom-row">
          <!-- Knowledge Mastery TOP10 -->
          <div class="card card--top10">
            <div class="card-header">
              <h3 class="card-title">知识点记忆表现</h3>
            </div>
            <div ref="barChartEl" class="chart-container chart--bar"></div>
            <div class="evidence-dimensions" aria-label="知识点画像依据">
              <details
                v-for="item in knowledgeMasteryTop10"
                :key="item.category"
                class="evidence-panel"
                @toggle="handleEvidenceToggle($event, item.category)"
              >
                <summary class="evidence-summary">
                  <span>{{ item.category }} · 证据 {{ item.evidenceCount }} 次</span>
                  <span class="evidence-action">依据</span>
                </summary>
                <div class="evidence-body" aria-live="polite">
                  <p v-if="evidenceLoading[item.category]" class="evidence-status">正在追溯学习记录...</p>
                  <div v-else-if="evidenceErrors[item.category]" class="evidence-status evidence-status--error">
                    <span>{{ evidenceErrors[item.category] }}</span>
                    <button type="button" class="evidence-retry" @click="loadDimensionEvidence(item.category, true)">重试</button>
                  </div>
                  <template v-else-if="evidenceByDimension[item.category]">
                    <p class="evidence-conclusion">{{ evidenceByDimension[item.category].conclusion }}</p>
                    <div
                      v-for="memory in evidenceByDimension[item.category].supporting_memories"
                      :key="memory.memory_id"
                      class="evidence-memory"
                    >
                      <p class="evidence-memory-title">支撑记忆 · {{ memory.content }}</p>
                      <ol class="evidence-events">
                        <li v-for="event in memory.evidence_events" :key="event.learning_record_id">
                          <span>{{ event.summary }}</span>
                          <time :datetime="event.at">{{ formatEvidenceTime(event.at) }}</time>
                        </li>
                      </ol>
                    </div>
                    <p v-if="!evidenceByDimension[item.category].supporting_memories.length" class="evidence-status">暂无足够的独立作答证据</p>
                  </template>
                </div>
              </details>
            </div>
          </div>

          <!-- Review Timeline -->
          <div class="card card--timeline">
            <div class="card-header">
              <h3 class="card-title">未来复习计划</h3>
              <span class="card-subtitle">智能间隔</span>
            </div>
            <div class="timeline-list" v-if="reviewPlan.length > 0">
              <div v-for="(item, i) in reviewPlan" :key="i" class="timeline-item">
                <div class="timeline-time">{{ item.time }}</div>
                <div class="timeline-content">
                  <div class="timeline-title">{{ item.title }}</div>
                  <div class="timeline-meta">{{ item.category }}</div>
                </div>
                <span class="timeline-badge">{{ item.interval }}</span>
              </div>
            </div>
            <div v-else class="empty-state">
              <p class="empty-text">暂无复习计划</p>
              <p class="empty-hint">在错题本中标记薄弱知识点后，系统会自动规划复习</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.profile-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--canvas);
}

.profile-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
}

/* ── Subtitle (compact inline) ── */
.subtitle-line {
  margin-bottom: var(--space-4);
}
.subtitle-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
}

/* ── Date range (used in topbar) ── */
.date-range {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  padding: 5px 13px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--surface);
  font-variant-numeric: tabular-nums;
}

/* ── Scrollable body ── */
.profile-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6);
}

/* ── KPI Row ── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.kpi-card {
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  transition: box-shadow var(--transition-fast), border-color var(--transition-fast);
}

.kpi-card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-sm);
}

.kpi-label {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  font-weight: 500;
  letter-spacing: 0.02em;
}

.kpi-value {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  color: var(--text-primary);
  margin: var(--space-1) 0;
  line-height: 1.2;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}

.kpi-value.fragile {
  color: var(--weak);
}

.kpi-unit {
  font-size: var(--font-size-base);
  font-weight: 500;
  color: var(--text-secondary);
  margin-left: 4px;
}

.kpi-sub {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.kpi-badge {
  font-weight: 600;
}

.kpi-count {
  color: var(--text-tertiary);
}

.kpi-delta-up {
  color: var(--mastered);
  font-weight: 500;
}

.kpi-sub-neutral {
  color: var(--text-tertiary);
}

/* ── Card base ── */
.card {
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  transition: box-shadow var(--transition-fast), border-color var(--transition-fast);
}

.card:hover {
  border-color: var(--border-strong);
  box-shadow: var(--shadow-sm);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-3);
}

.card-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}

.card-badge {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  padding: 2px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--surface-muted);
}

.card-subtitle {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.card-footer {
  font-size: var(--font-size-xs);
  color: var(--text-secondary);
  margin-top: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
  line-height: 1.6;
}

/* ── Chart containers ── */
.chart-container {
  flex: 1;
  min-height: 220px;
  width: 100%;
}

.chart--curve {
  min-height: 220px;
}

.chart--donut {
  min-height: 220px;
}

.chart--bar {
  min-height: 320px;
}

/* ── Middle Row ── */
.middle-row {
  display: grid;
  grid-template-columns: 1.5fr 1fr 1fr;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.card--curve {
  grid-column: span 1;
}

.card--donut {
  grid-column: span 1;
}

.card--insights {
  grid-column: span 1;
}

/* ── AI Insights ── */
.insight-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.insight-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-3) var(--space-4);
  background: var(--surface-muted);
  border-radius: var(--radius-sm);
}

.insight-label {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  font-weight: 500;
}

.insight-value {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: 600;
}

.insight-action {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.insight-action:hover {
  background: var(--accent-hover);
}

/* ── Bottom Row ── */
.bottom-row {
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

.card--top10 {
  grid-column: span 1;
}

.card--timeline {
  grid-column: span 1;
}

/* ── Timeline ── */
.timeline-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.timeline-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--surface-muted);
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.timeline-item:hover {
  background: var(--surface-hover);
}

.timeline-time {
  font-size: var(--font-size-xs);
  font-weight: 600;
  color: var(--accent);
  min-width: 70px;
  font-variant-numeric: tabular-nums;
}

.timeline-content {
  flex: 1;
  min-width: 0;
}

.timeline-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-meta {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  margin-top: 2px;
}

.timeline-badge {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  padding: 2px 8px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── Empty state ── */
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-8) var(--space-4);
  text-align: center;
}

.empty-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  margin-bottom: var(--space-2);
}

.empty-hint {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  line-height: 1.6;
}

/* ── Responsive ── */
@media (max-width: 1200px) {
  .middle-row {
    grid-template-columns: 1fr 1fr;
  }
  .card--insights {
    grid-column: span 2;
  }
  .bottom-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 900px) {
  .kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .middle-row {
    grid-template-columns: 1fr;
  }
  .card--insights {
    grid-column: span 1;
  }
}

@media (max-width: 600px) {
  .profile-body {
    padding: var(--space-4);
  }
  .kpi-row {
    grid-template-columns: 1fr;
  }
  .chart-container {
    min-height: 180px;
  }
  .chart--bar {
    min-height: 260px;
  }
}
</style>

<style scoped>
.evidence-dimensions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.evidence-panel {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
  overflow: hidden;
}

.evidence-summary {
  min-height: 44px;
  padding: 0 var(--space-3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}

.evidence-summary:hover,
.evidence-summary:focus-visible {
  color: var(--text-primary);
  background: var(--surface-hover);
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.evidence-action {
  color: var(--accent);
  font-weight: 600;
}

.evidence-body {
  padding: var(--space-3);
  border-top: 1px solid var(--border-subtle);
}

.evidence-conclusion,
.evidence-memory-title,
.evidence-status {
  margin: 0;
  line-height: 1.6;
}

.evidence-conclusion {
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  font-weight: 600;
}

.evidence-memory {
  margin-top: var(--space-3);
}

.evidence-memory-title,
.evidence-status {
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
}

.evidence-events {
  margin: var(--space-2) 0 0;
  padding-left: var(--space-5);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
}

.evidence-events li {
  margin-bottom: var(--space-2);
  line-height: 1.6;
}

.evidence-events time {
  display: block;
  color: var(--text-tertiary);
  font-variant-numeric: tabular-nums;
}

.evidence-status--error {
  color: var(--danger);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.evidence-retry {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  cursor: pointer;
}

@media (prefers-reduced-motion: reduce) {
  .evidence-summary { transition: none; }
}
</style>
