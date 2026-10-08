<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import type { EChartsOption } from 'echarts'
import { currentChartTheme, graphic, init, type ECharts } from '@/utils/charts'
import AppShell from '@/components/shell/AppShell.vue'
import { getLearningDashboard } from '@/api/learning'
import { apiErrorMessage } from '@/utils/apiError'
import { useDashboardMetrics } from '@/composables/useDashboardMetrics'
import { chartAnimation, chartVar, useChartTheme } from '@/composables/useChartTheme'
import { useEntranceAnimation } from '@/composables/useEntranceAnimation'
import { useReminderPolling } from '@/composables/useReminderPolling'
import { useErrorBookStore } from '@/stores/errorBookStore'
import {
  BookX, Check, CircleCheck, Clock, Crosshair, Play, Sparkles, Target, TrendingDown, Zap, ArrowUpRight,
} from 'lucide-vue-next'

const router = useRouter()
const errorBookStore = useErrorBookStore()
// 学习看板是提醒中心的两个拉取入口之一（另一个是首页）：挂载后一次 + 每 5 分钟。
useReminderPolling()

const learningDashboard = ref<any>(null)
const learningError = ref('')
const period = ref('7d')
const loading = ref(true)

const bodyEl = ref<HTMLElement | null>(null)
const trendChartEl = ref<HTMLElement | null>(null)
let trendChart: ECharts | null = null

let resizeHandler: (() => void) | null = null

const {
  greeting, greetingSub, learningHours, weekStudyDaysDisplay, masteredPoints,
  accuracyRate, weakPoints, chapterMastery, todayTasks, completedTasks,
  totalTasks, trendData, periodText,
} = useDashboardMetrics(learningDashboard, period)

const { bindChart, refreshAll, disposeAll } = useChartTheme()

/* 开屏动效:数据异步加载,内容渲染完成后手动重放;数字滚动由 v-count-up 承担 */
const playEntrance = useEntranceAnimation(() => bodyEl.value ?? undefined, { skipCountUp: true, autoplay: false })

const periodOptions = [
  { value: '7d', label: '近 7 天' },
  { value: '30d', label: '近 30 天' },
  { value: '90d', label: '近 90 天' },
]

const dateLabel = computed(() => {
  const now = new Date()
  const weeks = ['日', '一', '二', '三', '四', '五', '六']
  return `${now.getMonth() + 1}月${now.getDate()}日 周${weeks[now.getDay()]}`
})

const hoursNum = computed(() => Number(learningHours.value) || 0)
const totalKnowledgePoints = computed(
  () => learningDashboard.value?.progress?.knowledge_points ?? masteredPoints.value,
)
const accuracySample = computed(() => learningDashboard.value?.metrics?.accuracy?.sample_size || 0)
const errorTotalCaption = computed(() =>
  errorBookStore.totalErrors ? `错题本共 ${errorBookStore.totalErrors} 题` : '暂无错题记录',
)

/* KPI 迷你走势线(§3.1:时长 brand / 正确率 accent;无真实序列时不渲染) */
function sparkPoints(values: number[], width = 72, height = 30, pad = 2): string {
  const vals = values.filter((v) => Number.isFinite(v))
  if (vals.length < 2) return ''
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  if (max === min && max === 0) return ''
  const span = max - min || 1
  const stepX = (width - pad * 2) / (vals.length - 1)
  return vals
    .map((v, i) => {
      const x = pad + i * stepX
      const y = height - pad - ((v - min) / span) * (height - pad * 2)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

const hoursSpark = computed(() =>
  sparkPoints((learningDashboard.value?.trend ?? []).slice(-14).map((item: any) => (item.active_seconds || 0) / 60)),
)
const accuracySpark = computed(() =>
  sparkPoints(
    (learningDashboard.value?.trend ?? [])
      .slice(-14)
      .map((item: any) => item.accuracy)
      .filter((value: any) => value != null),
  ),
)

/* 打卡热力格(0-4 级,口径沿用旧热力图:分钟 + 作答换算强度) */
const heatCells = computed(() =>
  (learningDashboard.value?.heatmap ?? []).map((item: any) => {
    const minutes = Math.round((item.active_seconds || 0) / 60)
    const attempts = item.attempts || 0
    const level = minutes === 0 && attempts === 0
      ? 0
      : Math.min(4, Math.max(1, Math.ceil((minutes + attempts * 2) / 15)))
    const day = new Date(item.date)
    return {
      key: item.date,
      level,
      label: `${day.getMonth() + 1}月${day.getDate()}日 · ${minutes} 分钟 · ${attempts} 次作答`,
    }
  }),
)

/* AI 洞察:只陈述 dashboard 真实字段(最薄弱/最牢固知识点),不虚构时间线 */
const topWeak = computed(() => learningDashboard.value?.weakest?.[0] ?? null)
const topStrong = computed(() => {
  const strong = learningDashboard.value?.strongest?.[0]
  return strong && strong.code !== topWeak.value?.code ? strong : null
})
const masteryPct = (item: any) => Math.round((item?.mastery ?? 0) * 100)

const taskTypeLabels: Record<string, string> = {
  review: '复习', practice: '练习', learn: '学习', challenge: '挑战', preview: '预习', weakness: '薄弱',
}
const taskTypeTags: Record<string, string> = {
  review: 'tag-soft-accent', practice: 'tag-soft-teal', learn: 'tag-soft-sky',
  challenge: 'tag-soft-rose', preview: 'tag-plain', weakness: 'tag-soft-amber',
}
const taskTypeLabel = (type: string) => taskTypeLabels[type] ?? type
const taskTagClass = (type: string) => taskTypeTags[type] ?? 'tag-plain'

const firstPendingTask = computed(
  () => todayTasks.value.find((task: any) => !task.done) ?? todayTasks.value[0] ?? null,
)

function startTask(task: any) {
  if (!task?.start?.route) return
  router.push({ path: task.start.route, query: task.start.query || {} })
}

function startWeakPractice() {
  router.push({ path: '/apply/practice', query: { knowledge_point: weakPoints.value[0]?.code } })
}

/* ── 学习投入趋势(§7.1:系列 1 学习时长=brand 主数据,系列 2 正确率=accent 对比)──
   颜色全部经 chartVar() 实时取值,配合 useChartTheme 的主题 watch 实现切换重绘 */
function buildTrendOption(): EChartsOption {
  const hoursByDate = new Map<string, number>()
  for (const item of learningDashboard.value?.trend ?? []) {
    hoursByDate.set(String(item.date).slice(5), Math.round(((item.active_seconds || 0) / 3600) * 10) / 10)
  }
  const dates = trendData.value.map((row) => row.date)
  return {
    grid: { left: 8, right: 8, top: 16, bottom: 0, containLabel: true },
    tooltip: {
      trigger: 'axis',
      backgroundColor: chartVar('--surface'),
      borderColor: chartVar('--border-strong'),
      borderWidth: 1,
      textStyle: { color: chartVar('--ink-1'), fontSize: 12 },
      extraCssText: 'border-radius:10px; box-shadow:var(--shadow-3); padding:8px 12px;',
      formatter: (params: any) => {
        const rows = (params as any[])
          .map((p) => {
            const unit = p.seriesName === '学习时长' ? ' h' : '%'
            return `<div style="margin-top:2px">${p.marker}${p.seriesName} <b class="num">${p.value ?? '—'}${unit}</b></div>`
          })
          .join('')
        return `<div class="caption">${params[0]?.axisValue ?? ''}</div>${rows}`
      },
    },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: chartVar('--border-strong') } },
      axisTick: { show: false },
      axisLabel: { color: chartVar('--ink-3'), fontSize: 11 },
    },
    yAxis: [
      {
        type: 'value',
        min: 0,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: chartVar('--ink-3'), fontSize: 11, formatter: '{value}h' },
        splitLine: { lineStyle: { color: chartVar('--border'), type: 'dashed' } },
      },
      {
        type: 'value',
        min: 0,
        max: 100,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { color: chartVar('--ink-3'), fontSize: 11, formatter: '{value}%' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: '学习时长',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 5,
        data: dates.map((d) => hoursByDate.get(d) ?? 0),
        lineStyle: { color: chartVar('--brand'), width: 2 },
        itemStyle: { color: chartVar('--brand'), borderColor: chartVar('--surface'), borderWidth: 1.5 },
        areaStyle: {
          color: new graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: chartVar('--brand-soft-2') },
            { offset: 1, color: 'transparent' },
          ]),
        },
        ...chartAnimation,
      },
      {
        name: '正确率',
        type: 'line',
        smooth: true,
        yAxisIndex: 1,
        symbol: 'none',
        data: trendData.value.map((row) => row.rate),
        lineStyle: { color: chartVar('--accent'), width: 1.8, opacity: 0.55 },
        itemStyle: { color: chartVar('--accent') },
        ...chartAnimation,
      },
    ],
  }
}

function destroyCharts() {
  disposeAll()
  trendChart = null
}

/* loading 门控会卸载图表容器,每次数据到位后重建实例并绑定主题重绘 */
async function renderCharts() {
  await nextTick()
  if (!trendChart && trendChartEl.value) {
    trendChart = init(trendChartEl.value, currentChartTheme())
    bindChart(trendChart, buildTrendOption)
  }
  refreshAll()
}

function handleResize() {
  trendChart?.resize()
}

async function fetchDashboard(value: string) {
  loading.value = true
  learningError.value = ''
  destroyCharts()
  try {
    const { data } = await getLearningDashboard(value)
    learningDashboard.value = data
    learningError.value = ''
  } catch (error: any) {
    learningError.value = apiErrorMessage(error, '暂时无法读取学习状态')
  } finally {
    loading.value = false
  }
  if (!learningError.value) {
    await renderCharts()
    playEntrance()
  }
}

function loadDashboard() {
  return fetchDashboard(period.value)
}

onMounted(() => {
  loadDashboard()
  // 待复盘错题计数(与侧栏角标同源;失败静默,不打断看板)
  errorBookStore.loadErrors().catch(() => {})
  resizeHandler = () => handleResize()
  window.addEventListener('resize', resizeHandler)
})

watch(period, (value) => {
  fetchDashboard(value)
})

onBeforeUnmount(() => {
  if (resizeHandler) window.removeEventListener('resize', resizeHandler)
  destroyCharts()
})
</script>

<template>
  <AppShell>
    <template #topbar-title>
      <span>学习看板</span>
    </template>

    <div class="dashboard-view">
      <div v-if="loading" class="dashboard-loading">正在读取学习状态…</div>

      <div v-else-if="learningError" class="app-state" role="alert">
        <p>{{ learningError }}</p>
        <button type="button" @click="loadDashboard">重试</button>
      </div>

      <div v-else ref="bodyEl" class="dashboard-body">
        <!-- 冷启动:尚在了解你 -->
        <div v-if="learningDashboard?.status === 'discovering'" class="card cold-start-card">
          <h2 class="t-2">尚在了解你</h2>
          <p class="muted">
            {{ learningDashboard.status_message }}。先完成一次基础诊断，之后这里会只展示有真实证据的进步、薄弱点和下一步任务。
          </p>
          <button
            v-if="learningDashboard.today?.primary?.start"
            class="btn btn-primary cold-start-action"
            type="button"
            @click="startTask(learningDashboard.today.primary)"
          >
            <Play class="ic-15" :stroke-width="1.75" />开始基础诊断
          </button>
          <p v-else class="caption">
            {{ learningDashboard.today?.primary?.degradation?.message || '诊断题库暂不可用' }}
          </p>
        </div>

        <template v-else>
          <!-- 页头 -->
          <div class="page-head">
            <div>
              <h1 class="t-1">{{ greeting }}</h1>
              <div class="sub">{{ dateLabel }} · {{ greetingSub }}</div>
            </div>
            <div class="head-actions">
              <div class="segmented" role="group" aria-label="选择学习看板统计周期">
                <button
                  v-for="opt in periodOptions"
                  :key="opt.value"
                  type="button"
                  :class="{ on: period === opt.value }"
                  @click="period = opt.value"
                >{{ opt.label }}</button>
              </div>
            </div>
          </div>

          <!-- KPI 统计 -->
          <div class="stat-grid">
            <div class="card stat">
              <div class="top">
                <span class="ic-chip" style="background:var(--brand-soft);color:var(--brand-text)"><Clock class="ic-15" :stroke-width="1.75" /></span>
                <span class="label">学习时长</span>
              </div>
              <div class="value">
                <span v-count-up="{ value: hoursNum, decimals: 1 }">{{ hoursNum.toFixed(1) }}</span><small>h</small>
              </div>
              <div class="delta-row"><span class="caption">{{ periodText }}学习 {{ weekStudyDaysDisplay }} 天</span></div>
              <svg v-if="hoursSpark" class="spark" width="72" height="30" viewBox="0 0 72 30" aria-hidden="true">
                <polyline :points="hoursSpark" fill="none" stroke="var(--brand)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </div>

            <div class="card stat">
              <div class="top">
                <span class="ic-chip" style="background:var(--green-soft);color:var(--green)"><CircleCheck class="ic-15" :stroke-width="1.75" /></span>
                <span class="label">已掌握知识点</span>
              </div>
              <div class="value">
                <span v-count-up="{ value: masteredPoints }">{{ masteredPoints }}</span><small>/ {{ totalKnowledgePoints }}</small>
              </div>
              <div class="delta-row"><span class="caption">按掌握度 ≥ 80% 计</span></div>
            </div>

            <div class="card stat">
              <div class="top">
                <span class="ic-chip" style="background:var(--accent-soft);color:var(--accent-text)"><Target class="ic-15" :stroke-width="1.75" /></span>
                <span class="label">练习正确率</span>
              </div>
              <div class="value">
                <template v-if="accuracyRate != null">
                  <span v-count-up="{ value: accuracyRate }">{{ accuracyRate }}</span><small>%</small>
                </template>
                <template v-else><span>—</span></template>
              </div>
              <div class="delta-row"><span class="caption">{{ accuracySample }} 次真实作答</span></div>
              <svg v-if="accuracySpark" class="spark" width="72" height="30" viewBox="0 0 72 30" aria-hidden="true">
                <polyline :points="accuracySpark" fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </div>

            <div class="card stat">
              <div class="top">
                <span class="ic-chip" style="background:var(--rose-soft);color:var(--rose)"><BookX class="ic-15" :stroke-width="1.75" /></span>
                <span class="label">待复盘错题</span>
              </div>
              <div class="value">
                <span v-count-up="{ value: errorBookStore.unmasteredCount }">{{ errorBookStore.unmasteredCount }}</span><small>道</small>
              </div>
              <div class="delta-row"><span class="caption">{{ errorTotalCaption }}</span></div>
            </div>
          </div>

          <!-- 主内容网格 -->
          <div class="grid-2">
            <!-- 左列 -->
            <div class="col-stack">
              <div class="card">
                <div class="card-head">
                  <span class="t-3">学习投入趋势</span>
                  <div class="legend">
                    <span><i style="background:var(--brand)"></i>学习时长</span>
                    <span><i style="background:var(--accent)"></i>练习正确率</span>
                  </div>
                </div>
                <div class="chart-wrap">
                  <div v-if="trendData.length" ref="trendChartEl" class="chart-trend"></div>
                  <p v-else class="caption chart-empty">暂无趋势数据，完成练习后这里会展示投入与正确率走势</p>
                </div>
              </div>

              <div class="card">
                <div class="card-head">
                  <span class="t-3">章节掌握度</span>
                  <button class="more" type="button" @click="router.push('/knowledge')">
                    查看知识图谱<ArrowUpRight class="ic-14" :stroke-width="1.75" />
                  </button>
                </div>
                <div class="chapter-list">
                  <div
                    v-for="ch in chapterMastery"
                    :key="ch.name"
                    class="bar-row"
                    :title="`证据 ${ch.evidence_count ?? 0} 次`"
                  >
                    <span class="bn">{{ ch.name }}</span>
                    <span class="progress"><i :style="{ width: ch.percent + '%' }" :class="{ amber: ch.percent < 40 }"></i></span>
                    <span class="bv"><b v-count-up="{ value: ch.percent }">{{ ch.percent }}</b>/100</span>
                  </div>
                  <p v-if="!chapterMastery.length" class="caption chapter-empty">完成练习后，这里会展示各章节掌握度</p>
                </div>
              </div>

              <div class="card">
                <div class="card-head">
                  <span class="t-3">薄弱知识点预警</span>
                  <button class="more" type="button" @click="router.push('/error-book')">
                    查看错题本<ArrowUpRight class="ic-14" :stroke-width="1.75" />
                  </button>
                </div>
                <div v-if="weakPoints.length" class="weak-list">
                  <div v-for="wp in weakPoints" :key="wp.code ?? wp.category" class="bar-row">
                    <span class="bn">{{ wp.category }}</span>
                    <span class="progress"><i class="rose" :style="{ width: wp.rate + '%' }"></i></span>
                    <span class="bv weak-rate"><b>{{ wp.rate }}%</b></span>
                  </div>
                </div>
                <p v-else class="caption chapter-empty">暂无薄弱知识点记录，完成练习后这里会显示需要加强的考点</p>
                <div v-if="weakPoints.length" class="card-foot">
                  <button class="btn btn-primary btn-block" type="button" @click="startWeakPractice">
                    <Crosshair class="ic-15" :stroke-width="1.75" />去强化「{{ weakPoints[0].category }}」
                  </button>
                </div>
              </div>
            </div>

            <!-- 右列 -->
            <div class="col-stack">
              <div class="card">
                <div class="card-head">
                  <span class="t-3">今日任务</span>
                  <span class="tag tag-soft-accent">{{ completedTasks }}/{{ totalTasks }} 项</span>
                </div>
                <div class="task-list">
                  <div
                    v-for="task in todayTasks"
                    :key="task.id"
                    class="task"
                    :class="{ done: task.done }"
                    role="button"
                    tabindex="0"
                    @click="startTask(task)"
                    @keydown.enter="startTask(task)"
                  >
                    <span class="tick">
                      <Check v-if="task.done" class="ic-14" :stroke-width="2.6" />
                    </span>
                    <div>
                      <div class="tt" :title="task.reason">{{ task.title }}</div>
                      <div class="tm">
                        <span class="tag" :class="taskTagClass(task.type)">{{ taskTypeLabel(task.type) }}</span>
                        <span class="tm-reason">{{ task.reason }}</span>
                      </div>
                    </div>
                  </div>
                  <p v-if="!todayTasks.length" class="caption task-empty">尚在了解你，完成一次基础诊断后会生成今日任务</p>
                </div>
                <div class="card-foot">
                  <button
                    class="btn btn-primary btn-block"
                    type="button"
                    :disabled="!firstPendingTask"
                    @click="startTask(firstPendingTask)"
                  >
                    <Play class="ic-15" :stroke-width="1.75" />开始今日任务
                  </button>
                </div>
              </div>

              <div class="card ai-card">
                <div class="card-head">
                  <span class="ai-head"><Sparkles class="ic" :stroke-width="1.75" />AI 学习洞察</span>
                  <span class="caption">基于真实作答生成</span>
                </div>
                <div class="ai-body">
                  <div v-if="topWeak" class="ai-insight">
                    <TrendingDown class="ic-14" :stroke-width="1.75" />
                    <p><b>「{{ topWeak.name }}」</b>掌握度 <b class="num">{{ masteryPct(topWeak) }}</b>，建议本周优先安排专项练习，尽快补齐薄弱点。</p>
                  </div>
                  <div v-if="topStrong" class="ai-insight">
                    <Zap class="ic-14" :stroke-width="1.75" />
                    <p><b>「{{ topStrong.name }}」</b>掌握度领先（<b class="num">{{ masteryPct(topStrong) }}</b>），可以尝试变式挑战巩固迁移能力。</p>
                  </div>
                  <div v-if="!topWeak && !topStrong" class="ai-insight">
                    <Sparkles class="ic-14" :stroke-width="1.75" />
                    <p>完成一次练习后，这里会基于真实作答给出学习洞察。</p>
                  </div>
                </div>
              </div>

              <div class="card">
                <div class="card-head">
                  <span class="t-3">学习打卡</span>
                  <span class="caption">{{ periodText }}</span>
                </div>
                <div v-if="heatCells.length" class="heat" role="img" aria-label="学习打卡热力图">
                  <i
                    v-for="cell in heatCells"
                    :key="cell.key"
                    :class="cell.level ? `l${cell.level}` : undefined"
                    :title="cell.label"
                  ></i>
                </div>
                <p v-else class="caption heat-empty">暂无学习记录</p>
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </AppShell>
</template>

<style scoped>
.dashboard-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.dashboard-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--ink-3);
  font-size: 13.5px;
}

/* 滚动由 shell-content 承担;内容列限宽居中(§3.3 数据页内容宽) */
.dashboard-body {
  flex: 1;
  width: 100%;
  max-width: var(--content-max);
  margin: 0 auto;
  padding: 24px clamp(16px, 3vw, 32px) 44px;
}

/* ── 页头 ── */
.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 22px;
}
.page-head h1 {
  margin: 0;
}
.page-head .sub {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 13px;
  color: var(--ink-3);
}
.head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
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

/* ── 图表卡 ── */
.legend {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: var(--ink-2);
}
.legend i {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 3px;
  margin-right: 6px;
}
.chart-wrap {
  padding: 6px 12px 12px;
}
.chart-trend {
  height: 220px;
}
.chart-empty {
  padding: 40px 20px;
  text-align: center;
}

/* ── KPI 迷你走势线 ── */
.spark {
  position: absolute;
  right: 14px;
  bottom: 16px;
  opacity: 0.9;
}

/* ── 章节掌握度 / 薄弱预警(bar-row 原子类,局部仅补空态与动作区)── */
.chapter-list {
  padding: 8px 0 12px;
}
.chapter-empty {
  padding: 20px;
  text-align: center;
}
.weak-rate b {
  color: var(--rose);
}
.card-foot {
  padding: 8px 20px 16px;
}
.card-foot .btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ── 今日任务(task 原子类,局部补列表容器与元信息)── */
.task-list {
  padding: 6px 0 4px;
}
.task-empty {
  padding: 20px;
  text-align: center;
}
.task .tm-reason {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── AI 洞察(ai-card 描边与 .ai-insight 为全局原子类)── */
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

/* ── 学习打卡(heat 原子类)── */
.heat-empty {
  padding: 20px;
  text-align: center;
}

/* ── 响应式(≤768 时 stat-grid 2 列、grid-2 单列由 global 原子类负责)── */
@media (max-width: 768px) {
  .dashboard-body {
    padding: 20px var(--space-4) 36px;
  }

  .page-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>
