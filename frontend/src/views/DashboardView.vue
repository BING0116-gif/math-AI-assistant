<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import AppShell from '@/components/shell/AppShell.vue'
import { listCourses } from '@/api/knowledge'
import { getLearningDashboard } from '@/api/learning'
import { useRouter } from 'vue-router'

const router = useRouter()
const learningDashboard = ref<any>(null)
const learningError = ref('')

const period = ref('7d')
const loading = ref(true)

const trendChartEl = ref<HTMLElement | null>(null)
const heatmapChartEl = ref<HTMLElement | null>(null)
let trendChart: echarts.ECharts | null = null
let heatmapChart: echarts.ECharts | null = null

let resizeHandler: (() => void) | null = null

// ── Greeting ──
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了，注意休息'
  if (h < 12) return '上午好，开始今天的学习'
  if (h < 14) return '下午好，继续加油'
  if (h < 18) return '下午好，继续加油'
  return '晚上好，辛苦了'
})

const greetingSub = computed(() => {
  const h = new Date().getHours()
  if (h < 12) return '用数据看见进步'
  if (h < 18) return '用数据看见进步'
  return '回顾今天的收获'
})

// ── Data computation from real sources ──

// Total learning time estimate: ~3 min per user message, per session
const learningMinutes = computed(() => {
  return Math.round((learningDashboard.value?.metrics?.active_seconds?.value || 0) / 60)
})

const learningHours = computed(() => {
  const h = learningMinutes.value / 60
  return h.toFixed(1)
})

// This week study days
const weekStudyDays = computed(() => {
  return learningDashboard.value?.metrics?.study_days?.value || 0
})

const weekStudyDaysDisplay = computed(() => {
  return weekStudyDays.value > 0 ? weekStudyDays.value : 0
})

// Total knowledge points from error book categories
const masteredPoints = computed(() => {
  return (learningDashboard.value?.dimensions?.mastery || []).filter((item: any) => item.value >= .8).length
})

// Accuracy rate
const accuracyRate = computed(() => {
  return learningDashboard.value?.metrics?.accuracy?.value ?? null
})

// Weak knowledge points (from error book - unmastered entries)
const weakPoints = computed(() => {
  return (learningDashboard.value?.weakest || []).map((item: any) => ({
    category: item.name || item.code, code: item.code,
    rate: Math.round((1 - item.mastery) * 100), sampleSize: item.sample_size,
  }))
})

// Chapter mastery data (from error book categories + mastery status)
const chapterMastery = computed(() => {
  return (learningDashboard.value?.chapter_mastery || []).map((item: any) => ({ ...item, percent: Math.round(item.value * 100) }))
})

// Today's tasks
const todayTasks = computed(() => {
  const today = learningDashboard.value?.today
  return [today?.primary, ...(today?.alternatives || [])].filter(Boolean).map((task: any) => ({ ...task, done: false }))
})

const completedTasks = computed(() => todayTasks.value.filter(t => t.done).length)
const totalTasks = computed(() => todayTasks.value.length)
const taskProgress = computed(() => totalTasks.value ? Math.round((completedTasks.value / totalTasks.value) * 100) : 0)

// Today's goal progress
const goalItems = computed(() => {
  return learningDashboard.value?.goals?.items || []
})

const overallGoalProgress = computed(() => {
  const items = goalItems.value
  if (items.length === 0) return 0
  return Math.round(items.reduce((sum, item) => sum + item.percent, 0) / items.length)
})

// Accuracy trend data (last 7 days)
const trendData = computed(() => {
  return (learningDashboard.value?.trend || []).map((item: any) => ({
    date: item.date.slice(5), rate: item.accuracy, correct: item.correct, total: item.attempts,
  }))
})

// Heatmap data (last 30 days)
const heatmapData = computed(() => {
  return (learningDashboard.value?.heatmap || []).map((item: any, index: number) => {
    const minutes = Math.round(item.active_seconds / 60)
    const intensity = minutes === 0 && item.attempts === 0 ? 0 : Math.min(4, Math.max(1, Math.ceil((minutes + item.attempts * 2) / 15)))
    return [new Date(item.date).getDay(), Math.floor(index / 7), intensity, item.date, minutes, item.attempts]
  })
})

// Week-over-week comparison
const weeklyComparison = computed(() => {
  const rows = trendData.value.slice(-7)
  const total = rows.reduce((sum, item) => sum + item.total, 0)
  const correct = rows.reduce((sum, item) => sum + item.correct, 0)
  return { thisWeek: total ? Math.round(correct / total * 100) : null, sampleSize: total }
})

// Load courses for chapter data
async function loadCourses() {
  try {
    const res = await listCourses()
    if (res?.data?.courses?.length) {
      // Could enhance chapterMastery with course data
    }
  } catch {
    // Use local data only
  }
}

// ── Chart helpers ──

function getCSSVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function initTrendChart() {
  if (!trendChartEl.value) return

  const surface = getCSSVar('--surface') || '#FCFBF8'
  const borderSubtle = getCSSVar('--border-subtle') || '#E6E3DA'
  const textPrimary = getCSSVar('--text-primary') || '#20231F'
  const textSecondary = getCSSVar('--text-secondary') || '#72766F'
  const textTertiary = getCSSVar('--text-tertiary') || '#9A9D96'
  const accent = getCSSVar('--accent') || '#416B56'

  trendChart = echarts.init(trendChartEl.value)

  const dates = trendData.value.map(d => d.date)
  const rates = trendData.value.map(d => d.rate)

  trendChart.setOption({
    grid: {
      left: 40,
      right: 20,
      top: 20,
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
        const p = params[0]
        return `<div style="font-size:12px;color:${textSecondary}">${p.axisValue}</div>
                <div style="font-weight:600;color:${accent}">正确率 ${p.value}%</div>`
      },
    },
    xAxis: {
      type: 'category',
      data: dates,
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
        name: '正确率',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        data: rates,
        lineStyle: {
          color: accent,
          width: 2.5,
        },
        itemStyle: {
          color: accent,
          borderColor: surface,
          borderWidth: 2,
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(65, 107, 86, 0.18)' },
            { offset: 1, color: 'rgba(65, 107, 86, 0.02)' },
          ]),
        },
      },
    ],
  })
}

function initHeatmapChart() {
  if (!heatmapChartEl.value) return

  const surface = getCSSVar('--surface') || '#FCFBF8'
  const borderSubtle = getCSSVar('--border-subtle') || '#E6E3DA'
  const textPrimary = getCSSVar('--text-primary') || '#20231F'
  const textSecondary = getCSSVar('--text-secondary') || '#72766F'
  const textTertiary = getCSSVar('--text-tertiary') || '#9A9D96'
  const accent = getCSSVar('--accent') || '#416B56'

  heatmapChart = echarts.init(heatmapChartEl.value)

  const data = heatmapData.value
  const maxVal = Math.max(1, ...data.map(d => d[2]))

  heatmapChart.setOption({
    grid: {
      left: 10,
      right: 10,
      top: 10,
      bottom: 30,
      containLabel: true,
    },
    tooltip: {
      backgroundColor: surface,
      borderColor: borderSubtle,
      borderWidth: 1,
      padding: [8, 12],
      textStyle: { color: textPrimary, fontSize: 12 },
      extraCssText: 'box-shadow: 0 2px 8px rgba(32,35,31,0.06); border-radius: 8px;',
      formatter: (params: any) => {
        const level = params.value[2]
        const labels = ['无', '少量', '一般', '较多', '很多']
        return `<div style="font-size:12px;color:${textSecondary}">${params.value[3]}</div>
                <div style="font-weight:600;color:${accent}">${labels[level]} · ${params.value[4]} 分钟 · ${params.value[5]} 次作答</div>`
      },
    },
    xAxis: {
      type: 'category',
      data: ['日', '一', '二', '三', '四', '五', '六'],
      axisLine: { show: false },
      axisLabel: { color: textTertiary, fontSize: 10 },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'category',
      data: Array.from({ length: Math.max(1, Math.ceil(data.length / 7)) }, (_, i) => `第${i + 1}周`),
      axisLine: { show: false },
      axisLabel: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      inverse: true,
    },
    visualMap: {
      min: 0,
      max: maxVal,
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      show: false,
      inRange: {
        color: ['#F1F2EC', '#D4E5DA', '#A8CBA9', '#7DB890', '#416B56'],
      },
    },
    series: [
      {
        name: '学习热度',
        type: 'heatmap',
        data: data,
        label: { show: false },
        itemStyle: {
          borderColor: surface,
          borderWidth: 2,
          borderRadius: 2,
        },
        emphasis: {
          itemStyle: {
            shadowBlur: 6,
            shadowColor: 'rgba(32, 35, 31, 0.15)',
          },
        },
      },
    ],
  })
}

function handleResize() {
  trendChart?.resize()
  heatmapChart?.resize()
}

// Toggle task completion
function startTask(task: any) {
  if (task.start?.route) router.push({ path: task.start.route, query: task.start.query || {} })
}

// Period text
const periodText = computed(() => {
  return period.value === '7d' ? '近 7 天' : period.value === '30d' ? '近 30 天' : '全部'
})

onMounted(async () => {
  await Promise.all([
    loadCourses(),
    getLearningDashboard(period.value).then(({ data }) => { learningDashboard.value = data }).catch((error) => {
      learningError.value = error?.response?.data?.detail?.message || '暂时无法读取学习状态'
    }),
  ])

  await nextTick()
  initTrendChart()
  initHeatmapChart()

  resizeHandler = () => handleResize()
  window.addEventListener('resize', resizeHandler)

  loading.value = false
})

watch(period, async (value) => {
  loading.value = true
  try {
    const { data } = await getLearningDashboard(value)
    learningDashboard.value = data
    learningError.value = ''
  } catch (error: any) {
    learningError.value = error?.response?.data?.detail?.message || '暂时无法读取学习状态'
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', resizeHandler!)
  trendChart?.dispose()
  heatmapChart?.dispose()
})

// Re-init charts when data changes
watch(trendData, () => {
  if (trendChart) {
    const dates = trendData.value.map(d => d.date)
    const rates = trendData.value.map(d => d.rate)
    trendChart.setOption({
      xAxis: { data: dates },
      series: [{ data: rates }],
    })
  }
}, { deep: true })

watch(heatmapData, () => {
  if (heatmapChart) {
    heatmapChart.setOption({
      series: [{ data: heatmapData.value }],
    })
  }
}, { deep: true })
</script>

<template>
  <AppShell>
    <template #topbar-title>
      <span>学习看板</span>
    </template>
    <template #topbar-actions>
      <label class="period-label">统计周期
        <select v-model="period" class="period-btn" aria-label="选择学习看板统计周期">
          <option value="7d">近 7 天</option><option value="30d">近 30 天</option><option value="90d">近 90 天</option>
        </select>
      </label>
    </template>

    <div class="dashboard-view">
      <div v-if="loading" class="dashboard-loading">加载中...</div>

      <div v-else class="dashboard-body">
        <!-- Greeting line (compact inline) -->
        <div class="greeting-line">
          <span class="greeting-text">{{ greeting }}，{{ greetingSub }}。</span>
        </div>
        <div v-if="learningDashboard?.status === 'discovering'" class="card cold-start-card">
          <h2>尚在了解你</h2>
          <p>{{ learningDashboard.status_message }}。先完成一次基础诊断，之后这里会只展示有真实证据的进步、薄弱点和下一步任务。</p>
          <button
            v-if="learningDashboard.today?.primary?.start"
            class="period-btn cold-start-action"
            @click="startTask(learningDashboard.today.primary)"
          >开始基础诊断</button>
          <p v-else class="dashboard-loading">{{ learningDashboard.today?.primary?.degradation?.message || '诊断题库暂不可用' }}</p>
        </div>
        <template v-else>
        <!-- ── KPI Row ── -->
        <div class="kpi-row">
          <div class="kpi-card">
            <div class="kpi-label">学习时长</div>
            <div class="kpi-value">{{ learningHours }}<span class="kpi-unit">小时</span></div>
            <div class="kpi-sub">累计学习时间</div>
          </div>

          <div class="kpi-card">
            <div class="kpi-label">本周学习天数</div>
            <div class="kpi-value">{{ weekStudyDaysDisplay }}<span class="kpi-unit">天</span></div>
            <div class="kpi-sub" v-if="weekStudyDaysDisplay > 0">保持学习节奏</div>
            <div class="kpi-sub" v-else>本周还未开始学习</div>
          </div>

          <div class="kpi-card">
            <div class="kpi-label">掌握知识点</div>
            <div class="kpi-value">{{ masteredPoints }}<span class="kpi-unit">个</span></div>
            <div class="kpi-sub" v-if="masteredPoints > 0">已掌握的考点</div>
            <div class="kpi-sub" v-else>开始做题记录进步</div>
          </div>

          <div class="kpi-card">
            <div class="kpi-label">正确率</div>
            <div class="kpi-value">{{ accuracyRate == null ? '—' : accuracyRate }}<span v-if="accuracyRate != null" class="kpi-unit">%</span></div>
            <div class="kpi-sub">{{ learningDashboard.metrics?.accuracy?.sample_size || 0 }} 次真实作答</div>
          </div>

          <div class="kpi-card">
            <div class="kpi-label">完成任务</div>
            <div class="kpi-value">{{ completedTasks }}<span class="kpi-unit">/ {{ totalTasks }}</span></div>
            <div class="kpi-sub">{{ taskProgress }}% 今日进度</div>
          </div>
        </div>

        <!-- ── Middle Row: Trend + Weak Points + Goal ── -->
        <div class="middle-row">
          <!-- Accuracy Trend -->
          <div class="card card--trend">
            <div class="card-header">
              <h3 class="card-title">正确率趋势</h3>
              <span class="card-period">{{ periodText }}</span>
            </div>
            <div ref="trendChartEl" class="chart-container chart--trend"></div>
            <div class="card-footer">
              <span>近 7 天正确率 <strong>{{ weeklyComparison.thisWeek == null ? '数据不足' : `${weeklyComparison.thisWeek}%` }}</strong></span>
              <span class="trend-indicator">{{ weeklyComparison.sampleSize }} 次真实作答</span>
            </div>
          </div>

          <!-- Weak Knowledge Points -->
          <div class="card card--weak">
            <div class="card-header">
              <h3 class="card-title">薄弱知识点预警</h3>
              <button class="card-link" type="button" @click="router.push('/error-book')">查看全部 →</button>
            </div>
            <div class="weak-list" v-if="weakPoints.length > 0">
              <div v-for="(wp, i) in weakPoints" :key="i" class="weak-item">
                <span class="weak-name">{{ wp.category }}</span>
                <span class="weak-rate">{{ wp.rate }}%</span>
              </div>
              <button class="weak-action" type="button" @click="router.push({ path: '/apply/practice', query: { knowledge_point: weakPoints[0]?.code } })">去强化 →</button>
            </div>
            <div v-else class="empty-state">
              <p class="empty-text">暂无薄弱知识点记录</p>
              <p class="empty-hint">完成练习后，这里会显示需要加强的知识点</p>
            </div>
          </div>

          <!-- Today's Goal Progress -->
          <div class="card card--goal">
            <div class="card-header">
              <h3 class="card-title">今日目标进度</h3>
            </div>
            <div v-if="goalItems.length" class="goal-ring">
              <svg viewBox="0 0 120 120" class="progress-ring">
                <circle cx="60" cy="60" r="52" class="ring-bg" />
                <circle
                  cx="60" cy="60" r="52"
                  class="ring-fill"
                  :style="{ strokeDasharray: `${overallGoalProgress * 3.26} 326` }"
                />
              </svg>
              <div class="goal-percent">{{ overallGoalProgress }}%</div>
            </div>
            <div class="goal-items">
              <div v-for="(item, i) in goalItems" :key="i" class="goal-item">
                <span class="goal-label">{{ item.label }}</span>
                <span class="goal-target">{{ item.target }}</span>
                <span class="goal-current">{{ item.current }}</span>
              </div>
            </div>
            <div v-if="!goalItems.length" class="empty-state"><p class="empty-text">尚未设置学习目标</p><p class="empty-hint">目标配置上线前不会展示虚假进度</p></div>
          </div>
        </div>

        <!-- ── Bottom Row: Chapters + Tasks + Heatmap ── -->
        <div class="bottom-row">
          <!-- Chapter Mastery -->
          <div class="card card--chapters">
            <div class="card-header">
              <h3 class="card-title">章节知识掌握度</h3>
            </div>
            <div class="chapter-list">
              <div v-for="(ch, i) in chapterMastery" :key="i" class="chapter-item">
                <span class="chapter-name">{{ ch.name }}<small class="evidence-count">证据 {{ ch.evidence_count ?? 0 }} 次</small></span>
                <div class="chapter-bar-wrap">
                  <div class="chapter-bar" :style="{ width: ch.percent + '%' }" :class="{ 'chapter-bar--low': ch.percent < 40 }"></div>
                </div>
                <span class="chapter-percent">{{ ch.percent }}%</span>
              </div>
            </div>
          </div>

          <!-- Today's Tasks -->
          <div class="card card--tasks">
            <div class="card-header">
              <h3 class="card-title">今日任务 <span class="task-count">({{ completedTasks }}/{{ totalTasks }})</span></h3>
              <button class="card-link" type="button" @click="router.push('/apply')">选择学习活动</button>
            </div>
            <div class="task-list">
              <div
                v-for="task in todayTasks"
                :key="task.id"
                class="task-item"
                :class="{ 'task-item--done': task.done }"
                @click="startTask(task)"
              >
                <div class="task-check">
                  <svg v-if="task.done" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
                    <polyline points="20 6 9 17 4 12"/>
                  </svg>
                  <span v-else class="task-check-empty"></span>
                </div>
                <span class="task-title" :title="task.reason">{{ task.title }}</span>
                <span class="task-tag" :class="'task-tag--' + task.type">
                  {{ { review: '复习', practice: '练习', learn: '学习', challenge: '挑战', preview: '预习' }[task.type] || task.type }}
                </span>
              </div>
              <div v-if="!todayTasks.length" class="dashboard-loading">{{ learningError || '尚在了解你，完成一次基础诊断后会生成今日任务' }}</div>
            </div>
          </div>

          <!-- Study Heatmap -->
          <div class="card card--heatmap">
            <div class="card-header">
              <h3 class="card-title">学习热力图</h3>
              <span class="card-period">近 30 天</span>
            </div>
            <div ref="heatmapChartEl" class="chart-container chart--heatmap"></div>
            <div class="heatmap-legend">
              <span class="legend-label">学习时长越深，代表当天投入越多</span>
              <div class="legend-scale">
                <span class="legend-block legend-0"></span>
                <span class="legend-block legend-1"></span>
                <span class="legend-block legend-2"></span>
                <span class="legend-block legend-3"></span>
                <span class="legend-block legend-4"></span>
              </div>
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
  overflow: hidden;
  background: var(--canvas);
}

.dashboard-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
}

/* ── Greeting (compact inline) ── */
.greeting-line {
  margin-bottom: var(--space-4);
}
.greeting-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-weight: 500;
}
.cold-start-card { padding: var(--space-6); max-width: 720px; }
.cold-start-card h2 { margin: 0 0 var(--space-2); }
.cold-start-card p { color: var(--text-secondary); line-height: 1.7; }
.cold-start-action { margin-top: var(--space-3); background: var(--accent); color: white; }

/* ── Period button (used in topbar) ── */
.period-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: 5px 11px;
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-pill);
  background: var(--surface);
  color: var(--text-primary);
  font-size: var(--font-size-sm);
  cursor: pointer;
  transition: border-color var(--transition-fast);
}
.period-btn:hover {
  border-color: var(--accent);
}
.period-btn svg {
  width: 14px;
  height: 14px;
  color: var(--text-tertiary);
}

/* ── Scrollable body ── */
.dashboard-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6);
}

/* ── KPI Row ── */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
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

.card-period {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}

.card-link {
  font-size: var(--font-size-xs);
  color: var(--accent);
  background: none;
  border: none;
  cursor: pointer;
  font-weight: 500;
  transition: color var(--transition-fast);
}
.card-link:hover {
  color: var(--accent-hover);
}

/* ── Middle Row ── */
.middle-row {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: var(--space-4);
  margin-bottom: var(--space-5);
}

/* Trend chart */
.card--trend {
  min-height: 300px;
}
.chart-container {
  flex: 1;
  width: 100%;
  min-height: 220px;
}
.chart--trend {
  min-height: 220px;
}
.card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-subtle);
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}
.card-footer strong {
  color: var(--text-primary);
  font-weight: 600;
}
.trend-indicator {
  font-weight: 600;
}
.trend-up {
  color: var(--success);
}
.trend-down {
  color: var(--danger);
}

/* Weak points */
.card--weak {
  min-height: 300px;
}
.weak-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.weak-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2) var(--space-3);
  background: var(--canvas);
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}
.weak-item:hover {
  background: var(--surface-hover);
}
.weak-name {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: 500;
}
.weak-rate {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--weak);
}
.weak-action {
  margin-top: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--font-size-sm);
  font-weight: 600;
  cursor: pointer;
  transition: background var(--transition-fast);
}
.weak-action:hover {
  background: var(--accent-hover);
}
.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  gap: var(--space-2);
  padding: var(--space-6) var(--space-4);
}
.empty-text {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  font-weight: 500;
}
.empty-hint {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  line-height: 1.5;
}

/* Goal */
.card--goal {
  min-height: 300px;
}
.goal-ring {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: var(--space-2) 0 var(--space-3);
}
.progress-ring {
  width: 120px;
  height: 120px;
  transform: rotate(-90deg);
}
.ring-bg {
  fill: none;
  stroke: var(--surface-muted);
  stroke-width: 10;
}
.ring-fill {
  fill: none;
  stroke: var(--accent);
  stroke-width: 10;
  stroke-linecap: round;
  transition: stroke-dashoffset 0.6s ease;
}
.goal-percent {
  position: absolute;
  font-size: var(--font-size-3xl);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}
.goal-items {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}
.goal-item {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: var(--space-2);
  padding: var(--space-2) 0;
  border-top: 1px solid var(--border-subtle);
  font-size: var(--font-size-xs);
}
.goal-label {
  color: var(--text-secondary);
}
.goal-target {
  color: var(--text-tertiary);
}
.goal-current {
  color: var(--accent);
  font-weight: 600;
}

/* ── Bottom Row ── */
.bottom-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: var(--space-4);
}

/* Chapters */
.card--chapters {
  min-height: 280px;
}
.chapter-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  flex: 1;
}
.chapter-item {
  display: grid;
  grid-template-columns: 80px 1fr 48px;
  gap: var(--space-3);
  align-items: center;
}
.chapter-name {
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.chapter-bar-wrap {
  height: 8px;
  background: var(--surface-muted);
  border-radius: var(--radius-pill);
  overflow: hidden;
}
.chapter-bar {
  height: 100%;
  background: var(--accent);
  border-radius: var(--radius-pill);
  transition: width 0.5s ease;
}
.chapter-bar--low {
  background: var(--weak);
}
.chapter-percent {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text-primary);
  text-align: right;
}

/* Tasks */
.card--tasks {
  min-height: 280px;
}
.task-count {
  color: var(--text-tertiary);
  font-weight: 400;
}
.task-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex: 1;
}
.task-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--canvas);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background var(--transition-fast);
  user-select: none;
}
.task-item:hover {
  background: var(--surface-hover);
}
.task-item--done .task-title {
  color: var(--text-tertiary);
  text-decoration: line-through;
}
.task-check {
  width: 18px;
  height: 18px;
  border-radius: var(--radius-xs);
  display: grid;
  place-items: center;
  flex-shrink: 0;
  color: var(--accent);
}
.task-check svg {
  width: 16px;
  height: 16px;
}
.task-check-empty {
  width: 16px;
  height: 16px;
  border: 1.5px solid var(--border-strong);
  border-radius: var(--radius-xs);
  transition: border-color var(--transition-fast);
}
.task-item--done .task-check-empty {
  border-color: var(--accent);
  background: var(--accent);
}
.task-title {
  flex: 1;
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  font-weight: 500;
}
.task-tag {
  font-size: var(--font-size-xs);
  padding: 2px 8px;
  border-radius: var(--radius-pill);
  font-weight: 500;
  flex-shrink: 0;
}
.task-tag--review {
  background: var(--accent-soft);
  color: var(--accent);
}
.task-tag--practice {
  background: var(--knowledge-soft);
  color: var(--knowledge);
}
.task-tag--learn {
  background: var(--surface-muted);
  color: var(--text-secondary);
}
.task-tag--challenge {
  background: rgba(201, 103, 76, 0.12);
  color: var(--weak);
}
.task-tag--preview {
  background: rgba(200, 145, 61, 0.12);
  color: var(--warning);
}

/* Heatmap */
.card--heatmap {
  min-height: 280px;
}
.chart--heatmap {
  min-height: 180px;
}
.heatmap-legend {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
.legend-label {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
}
.legend-scale {
  display: flex;
  gap: 4px;
}
.legend-block {
  width: 14px;
  height: 14px;
  border-radius: 3px;
}
.legend-0 { background: #F1F2EC; }
.legend-1 { background: #D4E5DA; }
.legend-2 { background: #A8CBA9; }
.legend-3 { background: #7DB890; }
.legend-4 { background: #416B56; }

/* ── Responsive ── */
@media (max-width: 1200px) {
  .kpi-row {
    grid-template-columns: repeat(3, 1fr);
  }
  .middle-row {
    grid-template-columns: 1fr 1fr;
  }
  .card--trend {
    grid-column: span 2;
  }
  .bottom-row {
    grid-template-columns: 1fr 1fr;
  }
  .card--heatmap {
    grid-column: span 2;
  }
}

@media (max-width: 900px) {
  .kpi-row {
    grid-template-columns: repeat(2, 1fr);
  }
  .middle-row {
    grid-template-columns: 1fr;
  }
  .card--trend {
    grid-column: span 1;
  }
  .bottom-row {
    grid-template-columns: 1fr;
  }
  .card--heatmap {
    grid-column: span 1;
  }
}

@media (max-width: 600px) {
  .kpi-row {
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }
  .kpi-value {
    font-size: var(--font-size-2xl);
  }
  .chapter-item {
    grid-template-columns: 72px 1fr 40px;
  }
}
</style>

<style scoped>
.evidence-count { display: block; color: var(--text-secondary); font-size: 12px; font-weight: 400; }
</style>
