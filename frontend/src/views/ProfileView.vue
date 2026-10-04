<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import type { EChartsOption } from 'echarts'
import { currentChartTheme, graphic, init, type ECharts } from '@/utils/charts'
import AppShell from '@/components/shell/AppShell.vue'
import { getLearningDashboard, getLearningProfile } from '@/api/learning'
import { getProfileWhy } from '@/api/profileEvidence'
import MemoryPanel from '@/components/profile/MemoryPanel.vue'
import { useRouter } from 'vue-router'
import { apiErrorMessage } from '@/utils/apiError'
import { formatStableDateTime } from '@/utils/dateTime'
import { useProfileMetrics } from '@/composables/useProfileMetrics'
import { chartAnimation, chartVar, useChartTheme } from '@/composables/useChartTheme'
import { useEntranceAnimation } from '@/composables/useEntranceAnimation'
import { useAuthStore } from '@/stores/authStore'
import { ArrowUpRight, LayoutDashboard, Sparkles, TrendingDown, Zap } from 'lucide-vue-next'

const router = useRouter()
const authStore = useAuthStore()

const loading = ref(true)
const profileError = ref('')
const canonicalProfile = ref<any>(null)
const canonicalReviews = ref<any[]>([])
const weekDashboard = ref<any>(null)
const evidenceByDimension = ref<Record<string, any>>({})
const evidenceLoading = ref<Record<string, boolean>>({})
const evidenceErrors = ref<Record<string, string>>({})

const bodyEl = ref<HTMLElement | null>(null)
const curveChartEl = ref<HTMLElement | null>(null)
const barChartEl = ref<HTMLElement | null>(null)
let curveChart: ECharts | null = null
let barChart: ECharts | null = null

let resizeHandler: (() => void) | null = null

const {
  dateRange,
  masteryDistribution,
  memoryStabilityScore,
  stabilityLevel,
  strengthLabel,
  longTermRetention,
  reviewPlan,
  reviewPlanCount,
  reviewEstimateMinutes,
  knowledgeMasteryTop10,
  aiInsights,
} = useProfileMetrics(canonicalProfile, canonicalReviews)

const { bindChart, refreshAll, disposeAll } = useChartTheme()

/* 开屏动效:异步数据页内容渲染后手动重放;数字滚动由 v-count-up 承担 */
const playEntrance = useEntranceAnimation(() => bodyEl.value ?? undefined, { skipCountUp: true, autoplay: false })

const displayName = computed(() => (authStore.username || '').trim() || '同学')
const avatarChar = computed(() => displayName.value.charAt(0).toUpperCase())

const insightIcons = [Zap, TrendingDown, Sparkles]

// ── 能力雷达(五轴全部来自真实画像聚合:掌握/记忆/迁移/正确率/复习保持)──

const RADAR_CX = 140
const RADAR_CY = 112
const RADAR_R = 62

function radarPoint(index: number, total: number, frac: number) {
  const angle = ((-90 + (360 / total) * index) * Math.PI) / 180
  return {
    x: RADAR_CX + Math.cos(angle) * RADAR_R * frac,
    y: RADAR_CY + Math.sin(angle) * RADAR_R * frac,
  }
}

function pointsToString(points: Array<{ x: number; y: number }>): string {
  return points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
}

const knowledgeTotal = computed(() => canonicalProfile.value?.dimensions?.mastery?.length ?? 0)

const radarAxes = computed(() => {
  const dims = canonicalProfile.value?.dimensions ?? {}
  const avgPct = (items: any[]) =>
    items.length
      ? Math.round((items.reduce((sum: number, item: any) => sum + (item.value || 0), 0) / items.length) * 100)
      : 0
  const accuracyInsight = (canonicalProfile.value?.insights ?? []).find(
    (item: any) => item.evidence?.metric === 'accuracy',
  )
  const accuracy = accuracyInsight
    ? Number(accuracyInsight.evidence.value)
    : (weekDashboard.value?.metrics?.accuracy?.value ?? 0)
  return [
    { label: '知识掌握', value: avgPct(dims.mastery ?? []) },
    { label: '记忆强度', value: memoryStabilityScore.value },
    { label: '迁移应用', value: avgPct(dims.transfer ?? []) },
    { label: '近期正确率', value: accuracy },
    { label: '复习保持', value: longTermRetention.value },
  ]
})

const radar = computed(() => {
  const axes = radarAxes.value
  const total = axes.length
  const rings = [0.25, 0.5, 0.75, 1].map((frac) =>
    pointsToString(axes.map((_, i) => radarPoint(i, total, frac))))
  const spokes = axes.map((_, i) => {
    const p = radarPoint(i, total, 1)
    return { x1: RADAR_CX, y1: RADAR_CY, x2: p.x, y2: p.y }
  })
  const vertices = axes.map((axis, i) => radarPoint(i, total, Math.max(0.04, axis.value / 100)))
  const labels = axes.map((axis, i) => {
    const rad = ((-90 + (360 / total) * i) * Math.PI) / 180
    const cos = Math.cos(rad)
    const sin = Math.sin(rad)
    const p = radarPoint(i, total, 1.24)
    return {
      text: axis.label,
      x: p.x + (cos > 0.35 ? 6 : cos < -0.35 ? -6 : 0),
      y: p.y + (sin > 0.35 ? 13 : sin < -0.35 ? -4 : 4),
      anchor: (cos > 0.35 ? 'start' : cos < -0.35 ? 'end' : 'middle') as 'start' | 'middle' | 'end',
    }
  })
  const values = axes.map((axis, i) => {
    const p = radarPoint(i, total, Math.min(1.16, Math.max(0.2, axis.value / 100 + 0.14)))
    return { x: p.x, y: p.y + 3, text: axis.value }
  })
  return { rings, spokes, vertices, labels, values, polygon: pointsToString(vertices) }
})

/* ── 本周学习节奏(近 7 天真实学习投入,来自 learning dashboard trend)── */

const weekRhythm = computed(() => {
  const trend = weekDashboard.value?.trend ?? []
  const labels = ['日', '一', '二', '三', '四', '五', '六']
  const items = trend.map((row: any) => {
    const day = new Date(row.date)
    return {
      key: String(row.date),
      label: labels[day.getDay()] ?? '',
      minutes: Math.round((row.active_seconds || 0) / 60),
    }
  })
  const max = Math.max(0, ...items.map((item) => item.minutes))
  return items.map((item) => ({
    ...item,
    hot: item.minutes > 0 && item.minutes === max,
    height: item.minutes > 0 ? Math.max(6, Math.round((item.minutes / max) * 90)) : 4,
  }))
})

const weekPeak = computed(() => {
  let best: { label: string; minutes: number } | null = null
  for (const item of weekRhythm.value) {
    if (!best || item.minutes > best.minutes) best = { label: item.label, minutes: item.minutes }
  }
  return best && best.minutes > 0 ? best : null
})

const weekTotalMinutes = computed(() => weekRhythm.value.reduce((sum, item) => sum + item.minutes, 0))

const headCaption = computed(() => {
  const parts = [canonicalProfile.value?.status_message || '画像来自真实作答证据']
  if (knowledgeTotal.value) parts.push(`已纳入 ${knowledgeTotal.value} 个知识点`)
  const activeSeconds = weekDashboard.value?.metrics?.active_seconds?.value
  if (activeSeconds != null) {
    parts.push(`近 7 天学习 ${(Math.round((activeSeconds / 3600) * 10) / 10).toFixed(1)} 小时`)
  }
  return parts.join(' · ')
})

/* 掌握分布堆叠条(四档语义色:已掌握/学习中/薄弱/脆弱) */
const distribution = computed(() => {
  const d = masteryDistribution.value
  const total = d.mastered + d.learning + d.weak + d.fragile
  if (!total) return null
  const pct = (n: number) => (n / total) * 100
  const p1 = pct(d.mastered)
  const p2 = p1 + pct(d.learning)
  const p3 = p2 + pct(d.weak)
  const fmt = (v: number) => v.toFixed(2)
  return {
    total,
    mastered: d.mastered,
    gradient: `linear-gradient(90deg, var(--green) 0 ${fmt(p1)}%, var(--amber) ${fmt(p1)}% ${fmt(p2)}%, var(--rose) ${fmt(p2)}% ${fmt(p3)}%, var(--ink-3) ${fmt(p3)}% 100%)`,
    legend: [
      { label: '已掌握', count: d.mastered, color: 'var(--green)' },
      { label: '学习中', count: d.learning, color: 'var(--amber)' },
      { label: '薄弱', count: d.weak, color: 'var(--rose)' },
      { label: '脆弱', count: d.fragile, color: 'var(--ink-3)' },
    ],
  }
})

function formatEvidenceTime(value: string) {
  return formatStableDateTime(value)
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

// ── 图表(§7.2:chartVar 实时取色 + useChartTheme 主题重绘,替代旧一次性取色快照与旧墨绿 fallback)──

function buildCurveOption(): EChartsOption {
  const observations = canonicalProfile.value?.forgetting_curve?.observations ?? []
  const data = observations.map((item: any) => (item.retained ? 100 : 0))
  const days = observations.map((item: any) => `${item.interval_days}天`)
  return {
    grid: { left: 8, right: 16, top: 18, bottom: 0, containLabel: true },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const point = (params as any[])[0]
        if (!point) return ''
        return `<div class="caption">${point.axisValue}</div><div style="margin-top:2px">${point.value === 100 ? '复习后保持' : '未保持'}</div>`
      },
    },
    xAxis: {
      type: 'category',
      data: days,
      boundaryGap: false,
      axisLine: { lineStyle: { color: chartVar('--border-strong') } },
      axisTick: { show: false },
      axisLabel: { color: chartVar('--ink-3'), fontSize: 11 },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { color: chartVar('--ink-3'), fontSize: 11, formatter: '{value}%' },
      splitLine: { lineStyle: { color: chartVar('--border'), type: 'dashed' } },
    },
    series: [
      {
        name: '保持率',
        type: 'line',
        step: 'middle',
        symbol: 'circle',
        symbolSize: 7,
        data,
        lineStyle: { color: chartVar('--brand'), width: 2 },
        itemStyle: {
          color: (params: any) => (params.value === 100 ? chartVar('--brand') : chartVar('--rose')),
          borderColor: chartVar('--surface'),
          borderWidth: 1.5,
        },
        areaStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: chartVar('--brand-soft-2') },
            { offset: 1, color: 'transparent' },
          ]),
        },
        ...chartAnimation,
      },
    ],
  }
}

function buildBarOption(): EChartsOption {
  const data = knowledgeMasteryTop10.value
  return {
    grid: { left: 8, right: 44, top: 4, bottom: 4, containLabel: true },
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'none' },
      formatter: (params: any) => {
        const point = (params as any[])[0]
        const evidence = data.find((item) => item.category === point.name)?.evidenceCount ?? 0
        return `<div class="caption">${point.name}</div><div style="margin-top:2px">掌握度 <b class="num">${point.value}%</b> · 证据 ${evidence} 次</div>`
      },
    },
    xAxis: { type: 'value', show: false, max: 100 },
    yAxis: {
      type: 'category',
      data: data.map((item) => item.category).reverse(),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: chartVar('--ink-2'), fontSize: 12, width: 120, overflow: 'truncate' },
    },
    series: [
      {
        name: '掌握度',
        type: 'bar',
        data: data.map((item) => item.rate).reverse(),
        barWidth: 10,
        itemStyle: {
          borderRadius: [0, 4, 4, 0],
          color: (params: any) => {
            const rate = params.value
            if (rate >= 70) return chartVar('--green')
            if (rate >= 45) return chartVar('--amber')
            return chartVar('--rose')
          },
        },
        label: {
          show: true,
          position: 'right',
          formatter: '{c}%',
          color: chartVar('--ink-3'),
          fontSize: 11,
        },
        ...chartAnimation,
      },
    ],
  }
}

function handleResize() {
  curveChart?.resize()
  barChart?.resize()
}

function destroyCharts() {
  disposeAll()
  curveChart = null
  barChart = null
}

/* loading 门控会卸载图表容器,数据到位后重建实例并交给 useChartTheme 管理主题重绘 */
async function renderCharts() {
  await nextTick()
  if (!curveChart && curveChartEl.value) {
    curveChart = init(curveChartEl.value, currentChartTheme())
    bindChart(curveChart, buildCurveOption)
  }
  if (!barChart && barChartEl.value) {
    barChart = init(barChartEl.value, currentChartTheme())
    bindChart(barChart, buildBarOption)
  }
  refreshAll()
}

async function loadProfileData() {
  loading.value = true
  profileError.value = ''
  destroyCharts()
  try {
    const { data } = await getLearningProfile()
    canonicalProfile.value = data
    canonicalReviews.value = data.review_plan || []
  } catch (error: any) {
    profileError.value = apiErrorMessage(error, '画像加载失败，请稍后重试')
  } finally {
    loading.value = false
  }
  if (profileError.value) return
  // 近 7 天节奏为独立数据源,失败时静默降级为空态,不影响画像主数据
  getLearningDashboard('7d')
    .then(({ data }) => {
      weekDashboard.value = data
    })
    .catch(() => {})
  await renderCharts()
  playEntrance()
}

onMounted(() => {
  loadProfileData()
  resizeHandler = () => handleResize()
  window.addEventListener('resize', resizeHandler)
})

onBeforeUnmount(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  destroyCharts()
})
</script>

<template>
  <AppShell>
    <template #topbar-title>
      <span>记忆画像</span>
    </template>

    <div class="profile-view">
      <div v-if="loading" class="profile-loading">正在读取画像…</div>

      <div v-else-if="profileError" class="app-state" role="alert">
        <p>{{ profileError }}</p>
        <button type="button" @click="loadProfileData">重试</button>
      </div>

      <div v-else ref="bodyEl" class="profile-body">
        <!-- 冷启动:尚在了解你 -->
        <div v-if="canonicalProfile?.status === 'discovering'" class="card cold-start-card">
          <h2 class="t-2">尚在了解你</h2>
          <p class="muted">{{ canonicalProfile?.status_message || '完成基础诊断或一次练习后' }}，这里会展示掌握度、记忆强度、错误模式和迁移能力。</p>
          <button class="btn btn-primary cold-start-action" type="button" @click="router.push('/dashboard')">
            <LayoutDashboard class="ic-15" :stroke-width="1.75" />前往学习看板
          </button>
        </div>

        <template v-else>
          <!-- 画像头 -->
          <header class="profile-head">
            <span class="big-avatar" aria-hidden="true">{{ avatarChar }}</span>
            <div class="ph-main">
              <h2 class="ph-name">
                {{ displayName }}
                <span class="tag tag-soft-accent">{{ stabilityLevel }}</span>
              </h2>
              <p class="caption ph-caption">{{ headCaption }}</p>
              <div class="xp-track">
                <div class="xp-labels">
                  <span>记忆稳定性</span>
                  <span>综合 <b class="num">{{ memoryStabilityScore }}</b>/100 · {{ strengthLabel }}</span>
                </div>
                <div class="progress" role="img" :aria-label="`记忆稳定性 ${memoryStabilityScore}/100`">
                  <i :style="{ width: memoryStabilityScore + '%' }"></i>
                </div>
              </div>
            </div>
            <div class="head-actions">
              <span class="date-range">{{ dateRange }}</span>
            </div>
          </header>

          <div class="grid-2">
            <!-- 左列:能力雷达 + 本周学习节奏 -->
            <div class="col-stack">
              <div class="card">
                <div class="card-head">
                  <span class="t-3">能力雷达</span>
                  <span class="caption">综合评级 {{ strengthLabel }} · 基于真实作答</span>
                </div>
                <div v-if="knowledgeTotal" class="radar-wrap">
                  <svg width="280" height="216" viewBox="0 0 280 216" role="img" aria-label="能力雷达图">
                    <polygon
                      v-for="(ring, i) in radar.rings"
                      :key="`ring-${i}`"
                      :points="ring"
                      fill="none"
                      :stroke="i === radar.rings.length - 1 ? 'var(--border-strong)' : 'var(--border)'"
                      stroke-width="1"
                    />
                    <line v-for="(spoke, i) in radar.spokes" :key="`spoke-${i}`" v-bind="spoke" stroke="var(--border)" />
                    <polygon
                      class="radar-poly"
                      :points="radar.polygon"
                      fill="var(--brand-soft-2)"
                      stroke="var(--brand)"
                      stroke-width="1.8"
                      stroke-linejoin="round"
                    />
                    <circle v-for="(vertex, i) in radar.vertices" :key="`dot-${i}`" :cx="vertex.x" :cy="vertex.y" r="2.6" fill="var(--brand)" />
                    <text
                      v-for="(label, i) in radar.labels"
                      :key="`label-${i}`"
                      :x="label.x"
                      :y="label.y"
                      :text-anchor="label.anchor"
                      class="radar-label"
                    >{{ label.text }}</text>
                    <text
                      v-for="(value, i) in radar.values"
                      :key="`value-${i}`"
                      :x="value.x"
                      :y="value.y"
                      text-anchor="middle"
                      class="radar-value"
                    >{{ value.text }}</text>
                  </svg>
                </div>
                <p v-else class="caption radar-empty">完成练习后，这里会基于真实作答生成能力雷达</p>
              </div>

              <div class="card">
                <div class="card-head">
                  <span class="t-3">本周学习节奏</span>
                  <span class="caption">单位：分钟</span>
                </div>
                <div v-if="weekTotalMinutes > 0" class="week-bars" role="img" aria-label="近 7 天学习节奏">
                  <div v-for="day in weekRhythm" :key="day.key" class="wbar" :class="{ hot: day.hot }">
                    <i :style="{ height: day.height + 'px' }"></i>
                    <span>{{ day.label }}</span>
                  </div>
                </div>
                <p v-else class="caption rhythm-empty">近 7 天暂无学习记录</p>
                <div v-if="weekPeak" class="rhythm-foot">
                  <span class="caption">单日最高 <b class="num" v-count-up="{ value: weekPeak.minutes }">{{ weekPeak.minutes }}</b> 分钟（周{{ weekPeak.label }}）</span>
                  <span class="caption">周总计 <b class="num" v-count-up="{ value: weekTotalMinutes }">{{ weekTotalMinutes }}</b> 分钟</span>
                </div>
              </div>
            </div>

            <!-- 右列:记忆留存曲线 + AI 画像解读 -->
            <div class="col-stack">
              <div class="card">
                <div class="card-head">
                  <span class="t-3">记忆留存曲线</span>
                  <div class="legend">
                    <span><i style="background:var(--brand)"></i>复习后保持</span>
                    <span><i style="background:var(--rose)"></i>未保持</span>
                  </div>
                </div>
                <div
                  v-if="canonicalProfile?.forgetting_curve?.status === 'available'"
                  ref="curveChartEl"
                  class="chart-curve"
                  role="img"
                  :aria-label="`个人遗忘曲线，共 ${canonicalProfile.forgetting_curve.sample_size} 条复习证据`"
                ></div>
                <p v-else class="caption rhythm-empty">个人曲线数据积累中：{{ canonicalProfile?.forgetting_curve?.message }}</p>
                <div class="curve-foot">
                  <span class="caption">样本 {{ canonicalProfile?.forgetting_curve?.sample_size || 0 }} 条 · 算法 {{ canonicalProfile?.forgetting_curve?.algorithm_version }}</span>
                  <span class="caption">当前保持率 <b class="num">{{ longTermRetention }}%</b></span>
                </div>
              </div>

              <div class="card ai-card">
                <div class="card-head">
                  <span class="ai-head"><Sparkles class="ic" :stroke-width="1.75" />AI 画像解读</span>
                  <span class="caption">基于真实作答生成</span>
                </div>
                <div class="ai-body">
                  <div v-for="(insight, i) in aiInsights" :key="i" class="ai-insight">
                    <component :is="insightIcons[i % insightIcons.length]" class="ic-14" :stroke-width="1.75" />
                    <div>
                      <p><b>{{ insight.label }}</b>：{{ insight.value }}</p>
                      <small class="caption">样本 {{ insight.evidence?.sample_size || 0 }} · {{ insight.evidence?.period || '全部' }}</small>
                      <button
                        v-if="insight.action?.route"
                        class="insight-more"
                        type="button"
                        @click="router.push(insight.action.route)"
                      >
                        {{ insight.action.label }}<ArrowUpRight class="ic-14" :stroke-width="1.75" />
                      </button>
                    </div>
                  </div>
                  <div v-if="!aiInsights.length" class="ai-insight">
                    <Sparkles class="ic-14" :stroke-width="1.75" />
                    <p>完成一次练习后，这里会基于真实作答给出画像解读。</p>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 知识掌握分布(四段堆叠条) -->
          <div class="card dist-card">
            <div class="card-head">
              <span class="t-3">知识掌握分布</span>
              <div v-if="distribution" class="legend">
                <span v-for="seg in distribution.legend" :key="seg.label">
                  <i :style="{ background: seg.color }"></i>{{ seg.label }} {{ seg.count }}
                </span>
              </div>
            </div>
            <div v-if="distribution" class="dist-rows">
              <div class="bar-row dist-row">
                <span class="bn">全部知识点</span>
                <span class="progress dist-progress"><i :style="{ width: '100%', background: distribution.gradient }"></i></span>
                <span class="bv"><b v-count-up="{ value: distribution.mastered }">{{ distribution.mastered }}</b>/{{ distribution.total }} 已掌握</span>
              </div>
            </div>
            <p v-else class="caption dist-empty">暂无知识点掌握数据</p>
          </div>

          <!-- 知识点表现 + 复习计划 -->
          <div class="grid-2 bottom-grid">
            <div class="card">
              <div class="card-head">
                <span class="t-3">知识点记忆表现</span>
                <span class="caption">TOP {{ knowledgeMasteryTop10.length }} · 按掌握度排序</span>
              </div>
              <div v-if="knowledgeMasteryTop10.length" ref="barChartEl" class="chart-bar"></div>
              <p v-else class="caption dist-empty">暂无知识点掌握数据</p>
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

            <div class="card">
              <div class="card-head">
                <span class="t-3">未来复习计划</span>
                <button class="more" type="button" @click="router.push('/error-book')">
                  去错题本<ArrowUpRight class="ic-14" :stroke-width="1.75" />
                </button>
              </div>
              <div v-if="reviewPlan.length" class="timeline-list">
                <div v-for="(item, i) in reviewPlan" :key="i" class="timeline-item">
                  <div class="timeline-time">{{ item.time }}</div>
                  <div class="timeline-content">
                    <div class="timeline-title">{{ item.title }}</div>
                    <div class="timeline-meta">{{ item.category }}</div>
                  </div>
                  <span class="tag tag-plain">{{ item.interval }}</span>
                </div>
              </div>
              <div v-else class="empty-state">
                <p class="empty-text">暂无复习计划</p>
                <p class="empty-hint">在错题本中标记薄弱知识点后，系统会自动规划复习</p>
              </div>
              <div v-if="reviewPlanCount" class="timeline-foot">
                <span class="caption">共 {{ reviewPlanCount }} 条 · 预计 {{ reviewEstimateMinutes }} 分钟</span>
              </div>
            </div>
          </div>

          <!-- 我的记忆(阶段四 6.5):查看/确认/纠正/删除/导出 -->
          <MemoryPanel />

          <!-- 学习路径入口(阶段五 7.1) -->
          <div class="card path-entry-card">
            <div class="card-head">
              <span class="t-3">我的学习路径</span>
              <button class="more" type="button" @click="router.push('/learning/path')">
                查看路径<ArrowUpRight class="ic-14" :stroke-width="1.75" />
              </button>
            </div>
            <p class="caption">基于你的掌握度与知识点依赖关系,每周生成确定性的薄弱点攻克计划。</p>
          </div>
        </template>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.profile-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.profile-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-3);
  font-size: 13.5px;
}

/* 滚动由 shell-content 承担;内容列限宽居中(与 Dashboard 同宽) */
.profile-body {
  flex: 1;
  width: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
  padding: 24px clamp(16px, 3vw, 32px) 44px;
}

/* ── 冷启动 ── */
.cold-start-card {
  max-width: 720px;
  padding: var(--space-5);
}
.cold-start-card h2 {
  margin: 0 0 var(--space-2);
}
.cold-start-card p {
  line-height: 1.7;
}
.cold-start-action {
  margin-top: var(--space-4);
}

/* ── 画像头(profile-head 原型语言:大头像 + 名称 + 稳定性进度轨)── */
.profile-head {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 24px;
}
.big-avatar {
  width: 64px;
  height: 64px;
  border-radius: 20px;
  display: grid;
  place-items: center;
  flex: none;
  font-size: 22px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #17A98A, #0B7A5E 55%, #0AA2C4);
  box-shadow: 0 6px 20px -6px rgba(11, 122, 94, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}
.ph-main {
  flex: 1;
  min-width: 0;
}
.ph-name {
  margin: 0;
  font-size: 21px;
  font-weight: 700;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 10px;
}
.ph-caption {
  margin: 6px 0 0;
}
.ph-caption .num {
  color: var(--ink-2);
}
.xp-track {
  width: 220px;
  max-width: 100%;
  margin-top: 10px;
}
.xp-labels {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-size: 11.5px;
  color: var(--ink-3);
}
.xp-labels .num {
  color: var(--ink-2);
}
.xp-track .progress {
  margin-top: 5px;
  height: 8px;
}
.xp-track .progress > i {
  background: linear-gradient(90deg, var(--brand), var(--violet));
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.date-range {
  font-size: 12px;
  color: var(--ink-3);
  padding: 5px 13px;
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  background: var(--surface);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

/* ── 能力雷达(radar-poly 交给入场动效做中心绽放)── */
.radar-wrap {
  display: grid;
  place-items: center;
  padding: 8px 0 14px;
}
.radar-empty {
  padding: 34px 20px;
  text-align: center;
}
.radar-label {
  font-size: 10.5px;
  fill: var(--ink-2);
  font-weight: 600;
}
.radar-value {
  font-family: var(--font-disp);
  font-size: 10px;
  font-weight: 700;
  fill: var(--brand-text);
}

/* ── 本周学习节奏(wbar 结构,入场动效 scaleY 生长)── */
.week-bars {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  height: 120px;
  padding: 6px 20px 0;
}
.wbar {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.wbar i {
  width: 100%;
  max-width: 26px;
  border-radius: 6px 6px 3px 3px;
  background: var(--brand-soft-2);
  display: block;
}
.wbar.hot i {
  background: linear-gradient(180deg, var(--brand), var(--brand-strong));
}
.wbar span {
  font-size: 11px;
  color: var(--ink-3);
}
.wbar.hot span {
  color: var(--accent-text);
  font-weight: 600;
}
.rhythm-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 20px 14px;
  border-top: 1px dashed var(--border);
  margin-top: 14px;
}
.rhythm-foot .num {
  color: var(--ink-1);
}
.rhythm-empty {
  padding: 30px 20px;
  text-align: center;
}

/* ── 图表卡 ── */
.legend {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: var(--ink-2);
  flex-wrap: wrap;
}
.legend i {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 3px;
  margin-right: 6px;
}
.chart-curve {
  height: 190px;
  padding: 6px 12px 0;
}
.curve-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 20px 14px;
  border-top: 1px dashed var(--border);
  margin-top: 12px;
}
.curve-foot .num {
  color: var(--ink-1);
}
.chart-bar {
  height: 300px;
  padding: 8px 8px 0;
}

/* ── AI 画像解读(ai-card 渐变描边为全局原子类)── */
.ai-head {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.ai-head .ic {
  color: var(--brand);
}
.ai-body {
  padding: 4px 20px 16px;
}
.insight-more {
  margin-top: 6px;
  font-size: 12px;
  color: var(--brand-text);
  font-weight: 500;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  cursor: pointer;
  background: none;
  border: none;
  padding: 0;
}
.insight-more:hover {
  color: var(--brand);
}

/* ── 知识掌握分布(单条四段堆叠,进度条入场宽度生长)── */
.dist-card {
  margin-top: 16px;
}
.dist-rows {
  padding: 10px 0 14px;
}
.dist-row {
  grid-template-columns: 120px 1fr 110px;
}
.dist-progress {
  height: 10px;
}
.dist-empty {
  padding: 24px 20px;
  text-align: center;
}

/* ── 复习计划 ── */
.timeline-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: 12px 20px 4px;
}
.timeline-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--surface-2);
  border-radius: var(--r-s);
}
.timeline-time {
  font-size: 12px;
  font-weight: 600;
  color: var(--brand-text);
  min-width: 88px;
  flex: none;
  font-variant-numeric: tabular-nums;
}
.timeline-content {
  flex: 1;
  min-width: 0;
}
.timeline-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.timeline-meta {
  font-size: 11.5px;
  color: var(--ink-3);
  margin-top: 2px;
}
.timeline-foot {
  padding: 10px 20px 14px;
}

/* ── 空态 ── */
.empty-state {
  padding: var(--space-8) var(--space-4);
  text-align: center;
}
.empty-text {
  font-size: 13px;
  color: var(--ink-2);
  margin-bottom: var(--space-2);
}
.empty-hint {
  font-size: 12px;
  color: var(--ink-3);
  line-height: 1.6;
}

.bottom-grid {
  margin-top: 16px;
}

/* ── 响应式(≤768 时 grid-2 单列由 global 原子类负责)── */
@media (max-width: 768px) {
  .profile-body {
    padding: 20px var(--space-4) 36px;
  }
  .profile-head {
    flex-wrap: wrap;
  }
  .ph-main {
    flex: 1 1 220px;
  }
  .head-actions {
    width: 100%;
  }
  .xp-track {
    width: 100%;
  }
  .chart-bar {
    height: 260px;
  }
}
</style>

<style scoped>
.evidence-dimensions {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin: var(--space-3) var(--space-5) var(--space-4);
}

.evidence-panel {
  border: 1px solid var(--border);
  border-radius: var(--r-s);
  background: var(--surface-2);
  overflow: hidden;
}

.evidence-summary {
  min-height: 44px;
  padding: 0 var(--space-3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  color: var(--ink-2);
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.evidence-summary:hover,
.evidence-summary:focus-visible {
  color: var(--ink-1);
  background: var(--surface);
  outline: 2px solid var(--brand);
  outline-offset: -2px;
}

.evidence-action {
  color: var(--brand-text);
  font-weight: 600;
}

.evidence-body {
  padding: var(--space-3);
  border-top: 1px solid var(--border);
}

.evidence-conclusion,
.evidence-memory-title,
.evidence-status {
  margin: 0;
  line-height: 1.6;
}

.evidence-conclusion {
  color: var(--ink-1);
  font-size: 13px;
  font-weight: 600;
}

.evidence-memory {
  margin-top: var(--space-3);
}

.evidence-memory-title,
.evidence-status {
  color: var(--ink-2);
  font-size: 12px;
}

.evidence-events {
  margin: var(--space-2) 0 0;
  padding-left: var(--space-5);
  color: var(--ink-2);
  font-size: 12px;
}

.evidence-events li {
  margin-bottom: var(--space-2);
  line-height: 1.6;
}

.evidence-events time {
  display: block;
  color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}

.evidence-status--error {
  color: var(--rose);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.evidence-retry {
  min-height: 44px;
  padding: 0 var(--space-3);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-s);
  background: var(--surface);
  color: var(--ink-1);
  cursor: pointer;
}

.evidence-retry:hover {
  border-color: var(--brand);
  color: var(--brand-text);
}

@media (prefers-reduced-motion: reduce) {
  .evidence-summary {
    transition: none;
  }
}
</style>
