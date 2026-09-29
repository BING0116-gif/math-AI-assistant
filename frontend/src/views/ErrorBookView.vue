<template>
  <AppShell>
    <template #topbar-title>
      <span>错题复盘</span>
    </template>

    <div class="error-book-view" v-loading="store.loading">
      <div v-if="store.lastError && !store.loading" class="app-state" role="alert">
        <p>{{ store.lastError }}</p>
        <button type="button" @click="store.loadErrors">重试</button>
      </div>
      <template v-else>
        <div ref="bodyEl" class="eb-body">
          <!-- 页头 -->
          <div class="page-head">
            <div>
              <h1 class="t-1">错题复盘</h1>
              <div class="sub">共 {{ store.totalErrors }} 道错题 · AI 根据艾宾浩斯遗忘曲线自动排期</div>
            </div>
            <div class="head-actions">
              <button class="btn btn-primary" type="button" @click="startDailyReview">
                <Play class="ic-15" :stroke-width="1.75" />开始今日复习
              </button>
            </div>
          </div>

          <!-- 统计条 -->
          <div class="card stats-strip">
            <div class="cell">
              <div class="k">错题总数</div>
              <div class="v"><span v-count-up="{ value: store.totalErrors }">{{ store.totalErrors }}</span><small>道</small></div>
            </div>
            <div class="cell">
              <div class="k">今日待复盘</div>
              <div class="v due"><span v-count-up="{ value: todayReviewCount }">{{ todayReviewCount }}</span><small>道</small></div>
            </div>
            <div class="cell">
              <div class="k">已掌握</div>
              <div class="v ok"><span v-count-up="{ value: store.masteredCount }">{{ store.masteredCount }}</span><small>道</small></div>
            </div>
            <div class="cell">
              <div class="k">复习完成率</div>
              <div class="v"><span v-count-up="{ value: reviewCompleteRate }">{{ reviewCompleteRate }}</span><small>%</small></div>
            </div>
            <div class="cell">
              <div class="k">平均掌握度</div>
              <div class="v"><span v-count-up="{ value: avgMastery }">{{ avgMastery }}</span><small>/100</small></div>
            </div>
          </div>

          <!-- 工具栏 -->
          <div class="toolbar">
            <div class="segmented" role="group" aria-label="按状态筛选错题">
              <button
                v-for="tab in filterTabs"
                :key="tab.key"
                type="button"
                :class="{ on: activeTab === tab.key }"
                @click="activeTab = tab.key"
              >{{ tab.label }} {{ tab.count }}</button>
            </div>
            <select v-model="store.filter.category" class="filter-select" aria-label="按分类筛选" @change="onFilterChange">
              <option value="">科目：全部</option>
              <option v-for="cat in store.availableCategories" :key="cat" :value="cat">科目：{{ cat }}</option>
            </select>
            <label class="eb-search">
              <Search class="ic-14" :stroke-width="1.75" aria-hidden="true" />
              <input v-model="store.filter.search" placeholder="搜索错题关键词" @input="onFilterChange" />
            </label>
          </div>

          <!-- 内容网格:左列表 / 右分析 -->
          <div class="grid-2">
            <div class="errors-col">
              <TransitionGroup name="list-item">
                <ErrorCard
                  v-for="(error, idx) in filteredForTab"
                  :key="error.id"
                  :error="error"
                  :index="getFilteredIndex(idx)"
                  :due="dueErrorIds.has(error.id)"
                  @view-detail="openDetail"
                  @toggle-mastery="store.toggleMastery(error.id)"
                  @delete="handleDelete(error)"
                />
              </TransitionGroup>
              <div v-if="filteredForTab.length === 0 && !store.loading" class="app-state">
                <p>{{ store.totalErrors === 0 ? '暂无错题记录' : '没有匹配的错题' }}</p>
                <p class="caption">{{ store.totalErrors === 0 ? '在对话中点击「加入错题本」来添加第一道错题' : '尝试调整筛选条件' }}</p>
              </div>
            </div>

            <div class="col-stack">
              <!-- AI 错因画像 -->
              <div class="card ai-card">
                <div class="card-head">
                  <span class="ai-head"><Sparkles class="ic" :stroke-width="1.75" />AI 错因画像</span>
                  <span class="caption">基于 {{ store.totalErrors }} 道错题</span>
                </div>
                <div class="ai-body">
                  <template v-if="errorPatterns.length">
                    <div v-for="(p, i) in errorPatterns" :key="p.name" class="hbar-row">
                      <span class="hn">{{ p.name }}</span>
                      <span class="hbar"><i :style="{ width: p.percent + '%', background: patternColor(i) }"></i></span>
                      <span class="hv">{{ p.percent }}%</span>
                    </div>
                    <p v-if="patternSummary" class="caption pattern-note">{{ patternSummary }}</p>
                    <div class="card-foot">
                      <button class="btn btn-primary btn-block" type="button" @click="handleTrainClick">
                        <Crosshair class="ic-15" :stroke-width="1.75" />专项训练薄弱模式
                      </button>
                    </div>
                  </template>
                  <p v-else class="caption eb-empty">暂无足够数据进行分析</p>
                </div>
              </div>

              <!-- 复习计划 -->
              <div class="card">
                <div class="card-head">
                  <span class="t-3">复习计划</span>
                  <span class="tag tag-soft-accent">艾宾浩斯</span>
                </div>
                <div class="plan-list">
                  <div v-for="(slot, idx) in reviewPlanBars" :key="slot.label" class="bar-row plan-bar" :title="slot.title">
                    <span class="bn" :class="{ 'bn-strong': idx === 0 }">{{ slot.label }}</span>
                    <span class="progress"><i :class="slot.barClass" :style="{ width: slot.width + '%' }"></i></span>
                    <span class="bv"><b>{{ slot.count }}</b> 道</span>
                  </div>
                  <p v-if="!reviewPlanBars.length" class="caption eb-empty">暂无复习排期，新错题会自动进入计划</p>
                </div>
                <div class="card-foot">
                  <button class="btn btn-primary btn-block" type="button" @click="startDailyReview">开始今日复习</button>
                </div>
              </div>

              <!-- 掌握分布 -->
              <div class="card">
                <div class="card-head"><span class="t-3">掌握分布</span></div>
                <div class="donut-wrap">
                  <svg width="104" height="104" viewBox="0 0 42 42" role="img" aria-label="错题掌握分布环图">
                    <circle cx="21" cy="21" r="15.915" fill="none" stroke="var(--surface-2)" stroke-width="5.5" />
                    <circle
                      v-for="seg in donutSegments"
                      :key="seg.key"
                      cx="21" cy="21" r="15.915" fill="none"
                      :stroke="seg.color" stroke-width="5.5"
                      :stroke-dasharray="`${seg.pct} ${100 - seg.pct}`"
                      :stroke-dashoffset="seg.offset"
                    />
                    <text x="21" y="20.5" text-anchor="middle" style="font-family:var(--font-disp);font-size:8px;font-weight:700;fill:var(--ink-1)"><tspan>{{ reviewCompleteRate }}</tspan>%</text>
                    <text x="21" y="27" text-anchor="middle" style="font-size:3.2px;fill:var(--ink-3)">复习完成率</text>
                  </svg>
                  <div class="donut-legend">
                    <div class="dl"><i style="background:var(--green)"></i>已掌握<b>{{ store.masteredCount }} 道</b></div>
                    <div class="dl"><i style="background:var(--amber)"></i>复习中<b>{{ reviewingCount }} 道</b></div>
                    <div class="dl"><i style="background:var(--rose)"></i>薄弱<b>{{ weakCount }} 道</b></div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
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
import { Crosshair, Play, Search, Sparkles } from 'lucide-vue-next'
import AppShell from '@/components/shell/AppShell.vue'
import ErrorCard from '@/components/errorBook/ErrorCard.vue'
import ErrorDetailModal from '@/components/errorBook/ErrorDetailModal.vue'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { getDueReviews } from '@/api/learning'
import { useErrorBookMetrics } from '@/composables/useErrorBookMetrics'
import { useEntranceAnimation } from '@/composables/useEntranceAnimation'

const route = useRoute()
const router = useRouter()
const store = useErrorBookStore()
const canonicalReviews = ref([])

const detailVisible = ref(false)
const detailIndex = ref(-1)
const activeTab = ref('all')
const bodyEl = ref(null)

const detailError = computed(() =>
  detailIndex.value >= 0 ? store.filteredErrors[detailIndex.value] : null
)

/* 开屏动效:数据异步加载,内容渲染完成后手动重放 */
const playEntrance = useEntranceAnimation(() => bodyEl.value ?? undefined, { skipCountUp: true, autoplay: false })

const {
  todayReviewCount,
  topErrorPattern,
  inProgressCount,
  graduationProgressText,
  weeklyMasteredCount,
  errorPatterns,
  patternSummary,
  todayReviewPlan,
  reviewSchedule,
  graduationStages,
  graduationStats,
  filterTabs,
  filteredForTab,
  getFilteredIndex,
  knowledgeOverview,
  learningTips,
} = useErrorBookMetrics(store, canonicalReviews, activeTab)

/* ── 统计条/环图派生值(全部来自 store 与 composable 真实数据)── */
const reviewCompleteRate = computed(() =>
  store.totalErrors ? Math.round((store.masteredCount / store.totalErrors) * 100) : 0
)

const avgMastery = computed(() => {
  const list = store.errors
  if (!list.length) return 0
  const sum = list.reduce((acc, item) => acc + (item.mastery_level || 3), 0)
  return Math.round((sum / list.length / 5) * 100)
})

const reviewingCount = computed(() => {
  const stage = graduationStages.value.find(item => item.key === 'understanding')
  const consolidating = graduationStages.value.find(item => item.key === 'consolidating')
  return (stage?.count || 0) + (consolidating?.count || 0)
})

const weakCount = computed(
  () => graduationStages.value.find(item => item.key === 'new')?.count || 0
)

/* 掌握分布环图:绿色已掌握 / 琥珀复习中 / 玫红薄弱;r=15.915 时周长≈100 */
const donutSegments = computed(() => {
  const total = store.totalErrors || 0
  if (!total) return []
  const stageCount = key => graduationStages.value.find(item => item.key === key)?.count || 0
  const segs = [
    { key: 'mastered', pct: Math.round((stageCount('mastered') / total) * 100), color: 'var(--green)' },
    { key: 'reviewing', pct: Math.round((reviewingCount.value / total) * 100), color: 'var(--amber)' },
    { key: 'weak', pct: Math.round((weakCount.value / total) * 100), color: 'var(--rose)' },
  ]
  let acc = 0
  for (const seg of segs) {
    seg.offset = 25 - acc
    acc += seg.pct
  }
  return segs.filter(seg => seg.pct > 0)
})

/* 复习计划条:按到期日分组取前 4 组,宽度相对最大组 */
const reviewPlanBars = computed(() => {
  const groups = reviewSchedule.value.slice(0, 4)
  const max = Math.max(1, ...groups.map(group => group.tasks.length))
  return groups.map((group, idx) => ({
    label: group.label,
    count: group.tasks.length,
    width: Math.round((group.tasks.length / max) * 100),
    barClass: idx === 0 ? 'today' : idx === groups.length - 1 ? 'green' : '',
    title: group.tasks.join('\n'),
  }))
})

/* AI 画像横条配色:按占比排名 rose/sky/amber/teal(与原型一致) */
function patternColor(index) {
  return ['var(--rose)', 'var(--sky)', 'var(--amber)', 'var(--teal)', 'var(--ink-4)'][index] || 'var(--ink-4)'
}

/* 今日到期错题 id 集(用于卡片 pill-alert;口径与复习计划"今天"行一致:当天内到期) */
const dueErrorIds = computed(() => {
  const todayEnd = new Date()
  todayEnd.setHours(23, 59, 59, 999)
  const end = todayEnd.getTime()
  const ids = new Set()
  canonicalReviews.value.forEach((review) => {
    const due = new Date(review.due_at).getTime()
    if (!Number.isFinite(due) || due > end) return
    if (review.error_item_id) {
      ids.add(review.error_item_id)
      return
    }
    store.errors.forEach((item) => {
      if ((item.knowledge_point_codes || item.categories || []).includes(review.knowledge_point_code)) ids.add(item.id)
    })
  })
  return ids
})

/* ============================================================
 * Actions
 * ============================================================ */
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
  await nextTick()
  playEntrance()
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

<style scoped>
.error-book-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

/* 滚动由 shell-content 承担;内容列限宽居中(§3.3) */
.eb-body {
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

/* ── 统计条(原子类之上补语义色)── */
.stats-strip .v.due {
  color: var(--rose);
}
.stats-strip .v.ok {
  color: var(--green);
}

/* ── 工具栏 ── */
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}
.filter-select {
  height: 30px;
  padding: 0 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  color: var(--ink-2);
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.filter-select:hover {
  border-color: var(--border-strong);
  color: var(--ink-1);
}
.eb-search {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 220px;
  height: 34px;
  margin-left: auto;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
  color: var(--ink-3);
  font-size: 13px;
  box-shadow: var(--shadow-1);
}
.eb-search input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--ink-1);
  font: inherit;
}
.eb-search input::placeholder {
  color: var(--ink-4);
}

/* ── 内容网格:左列表 / 右分析 ── */
.errors-col {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.eb-empty {
  padding: 20px 0;
  text-align: center;
}
.card-foot {
  padding: 8px 20px 16px;
}
.card-foot .btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* ── AI 错因画像 ── */
.ai-head {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.ai-head .ic {
  color: var(--brand);
}
.ai-body {
  padding: 4px 20px 0;
}
.hbar-row .hn {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pattern-note {
  margin-top: 6px;
  padding: 8px 0 2px;
  border-top: 1px dashed var(--border);
}

/* ── 复习计划 ── */
.plan-list {
  padding: 8px 0 4px;
}
.plan-bar {
  grid-template-columns: 64px 1fr 52px;
}
.plan-bar .bn-strong {
  font-weight: 600;
  color: var(--ink-1);
}
.progress > i.today {
  background: var(--accent-bright);
}

/* ── 掌握分布 ── */
.donut-wrap {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 6px 20px 16px;
}
.donut-legend {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.donut-legend .dl {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: var(--ink-2);
}
.donut-legend .dl i {
  width: 9px;
  height: 9px;
  border-radius: 3px;
}
.donut-legend .dl b {
  font-family: var(--font-disp);
  color: var(--ink-1);
  margin-left: auto;
  padding-left: 14px;
  font-variant-numeric: tabular-nums;
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

/* ── 响应式(≤768 时 grid-2 单列由 global 负责;统计条转 2 列网格)── */
@media (max-width: 768px) {
  .eb-body {
    padding: 20px var(--space-4) 36px;
  }

  .page-head {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .stats-strip {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 16px;
    padding: 12px 16px;
  }

  .stats-strip .cell {
    padding: 8px 0;
    border-left: none;
    border-bottom: 1px dashed var(--border);
  }

  .stats-strip .cell:last-child {
    border-bottom: none;
  }

  .eb-search {
    width: 100%;
    margin-left: 0;
  }
}
</style>
