<template>
  <AppShell>
    <template #topbar-title>
      <span>知识星球</span>
    </template>
    <template #topbar-actions>
      <span v-if="tree" class="version-badge">{{ tree.version.name }}</span>
    </template>

    <div ref="bodyEl" class="catalog" :aria-busy="loading">
      <!-- Inline title + desc -->
      <div class="catalog-intro">
        <h1 class="catalog-title">高等数学知识图谱</h1>
        <p class="catalog-desc">浏览课程知识结构，点击节点查看详细内容</p>
      </div>
      <div v-if="loading" class="state">正在绘制课程知识图谱…</div>
      <section v-else-if="error" class="state error-state" role="alert">
        <h2>{{ requiresAuth ? '登录后即可查看知识图谱' : '知识图谱暂时无法加载' }}</h2>
        <p>{{ error }}</p>
        <button v-if="requiresAuth" @click="openLogin()">登录或注册</button>
        <button v-else @click="loadCatalog">重试</button>
      </section>
      <template v-else-if="tree">
        <!-- 视图控制 -->
        <div class="legend-bar">
          <span class="legend-hint">{{ viewHint }}</span>
          <div class="view-toggle">
            <button type="button" :class="{ active: viewMode === '3d' }" @click="viewMode = '3d'">3D 知识星球</button>
            <button type="button" :class="{ active: viewMode === 'network' }" @click="viewMode = 'network'">知识网络</button>
            <button type="button" :class="{ active: viewMode === '2d' }" @click="viewMode = '2d'">依赖路径</button>
          </div>
        </div>

        <!-- 图谱 + 详情面板 -->
        <div class="graph-layout">
          <nav class="chapter-nav card" aria-label="课程章节">
            <p class="chapter-nav-label">章节</p>
            <button v-for="chapter in chapterList" :key="chapter.id" type="button" :class="{ active: chapter.id === activeChapterId }" :aria-current="chapter.id === activeChapterId ? 'true' : undefined" @click="selectChapter(chapter.id)">
              <span>{{ chapter.name }}</span><small>{{ chapter.pointCount }} 个知识点</small>
            </button>
          </nav>
          <div class="graph-area">
            <KnowledgeGraph2D v-if="viewMode !== '3d'" :tree="tree" :mastery="masteryMap" :active-chapter-id="activeChapterId" :selected-point-id="selectedPoint?.id || ''" :layout-mode="viewMode === 'network' ? 'force' : 'path'" @chapter-change="selectChapter" @select-point="selectPoint" />
            <KnowledgeGalaxy v-else :tree="tree" @select-point="selectPoint" @select-branch="selectBranch" />
          </div>
          <aside class="detail-panel card" :class="{ 'detail-panel--empty': !hasSelection }">
            <!-- 空状态 -->
            <div v-if="!hasSelection" class="detail-empty">
              <div class="detail-empty-icon" aria-hidden="true"><Network :size="22" :stroke-width="1.75" /></div>
              <p class="start-kicker">{{ primaryRecommendation ? '今日主推荐' : '推荐起点' }}</p>
              <h2>{{ startingPoint?.name || '从当前章节开始' }}</h2>
              <p>{{ primaryRecommendation?.reason || startingPoint?.description || '按章节顺序建立基础，再沿箭头进入下一步。' }}</p>
              <ul v-if="primaryRecommendation"><li>推荐依据：{{ primaryRecommendation.reason_code }}</li><li>同一时刻只保留一个主行动</li><li>完成练习后会重新计算路径</li></ul>
              <ul v-else><li>先理解当前知识点</li><li>沿实线箭头检查必要前置</li><li>学习后进入正式练习</li></ul>
              <button v-if="startingPoint" type="button" class="start-button" @click="selectPoint(startingPoint.id)">查看学习起点</button>
            </div>

            <!-- 加载中 -->
            <div v-else-if="pointLoading" class="detail-loading">
              <div class="spinner"></div>
              <p>加载知识内容…</p>
            </div>

            <!-- 知识点详情 -->
            <article v-else-if="selectedPoint" class="point-detail">
              <div class="detail-header">
                <h2 class="detail-title">{{ selectedPoint.name }}</h2>
                <span class="difficulty-badge">难度 {{ selectedPoint.difficulty }} / 5</span>
              </div>

              <p class="detail-desc">{{ selectedPoint.description }}</p>

              <div v-if="selectedLearningState?.status === 'locked'" class="unlock-notice" role="status">
                <strong>尚未解锁</strong>
                <p>还需掌握：{{ missingPrerequisiteNames.join('、') }}</p>
              </div>
              <div v-else-if="selectedLearningState?.review_due" class="review-notice" role="status">
                <strong>到期复习优先</strong>
                <p>现在复习这个知识点，有助于降低遗忘。</p>
              </div>

              <!-- 掌握度 -->
              <div class="detail-section">
                <div class="section-label">掌握度</div>
                <div class="progress mastery-progress"><i :style="{ width: masteryPercent + '%' }"></i></div>
                <span class="mastery-text">
                  <em v-if="masteryInfo" class="mastery-status" :class="masteryInfo.status">{{ masteryLabel }}</em>
                  <em v-else>{{ masteryLabel }} · 证据 0 次</em>
                  <template v-if="masteryInfo">· 练习 {{ masteryInfo.attempts }} 次 · 正确 {{ masteryInfo.correct }} 次 · 证据 {{ masteryInfo.evidence_count ?? 0 }} 次</template>
                </span>
              </div>

              <!-- 学习资源 -->
              <div v-if="selectedResources.length" class="detail-section">
                <div class="section-label">学习资源</div>
                <div class="resource-list">
                  <div v-for="res in selectedResources" :key="res.id" class="resource-item">
                    <span class="resource-type">{{ RESOURCE_TYPE_LABELS[res.type] || res.type }}</span>
                    <div class="resource-body">
                      <div class="resource-title">{{ res.title }}</div>
                      <p v-if="res.body" class="resource-desc">{{ res.body }}</p>
                    </div>
                  </div>
                </div>
              </div>

              <!-- 关联错题 -->
              <div v-if="relatedErrors.length" class="detail-section">
                <div class="section-label">关联错题</div>
                <div class="related-errors">
                  <button v-for="e in relatedErrors" :key="e.id" class="related-error-item" @click="router.push(`/error-book/${e.id}`)">
                    <span class="related-error-q">{{ (e.question_preview || e.question || '').slice(0, 40) || '未命名错题' }}</span>
                    <span class="related-error-state" :class="e.is_mastered ? 'ok' : 'bad'">{{ e.is_mastered ? '已掌握' : '待复习' }}</span>
                  </button>
                </div>
              </div>

              <!-- 关键概念 -->
              <div v-if="selectedPoint.key_concepts?.length" class="detail-section">
                <div class="section-label">关键概念</div>
                <ul class="detail-list">
                  <li v-for="(item, i) in selectedPoint.key_concepts" :key="i">{{ item }}</li>
                </ul>
              </div>

              <!-- 关键公式 -->
              <div v-if="selectedPoint.key_formulas?.length" class="detail-section">
                <div class="section-label">关键公式</div>
                <ul class="detail-list formula-list">
                  <li v-for="(item, i) in selectedPoint.key_formulas" :key="i">{{ item }}</li>
                </ul>
              </div>

              <!-- 常见易错点 -->
              <div v-if="selectedPoint.common_errors?.length" class="detail-section">
                <div class="section-label">常见易错点</div>
                <ul class="detail-list">
                  <li v-for="(item, i) in selectedPoint.common_errors" :key="i">{{ item }}</li>
                </ul>
              </div>

              <!-- 子知识点 -->
              <div v-if="childPoints.length" class="detail-section">
                <div class="section-label">子知识点</div>
                <div class="child-points">
                  <span v-for="cp in childPoints" :key="cp.id" class="child-point-tag" @click="selectPoint(cp.id)">{{ cp.name }}</span>
                </div>
              </div>

              <!-- 操作按钮 -->
              <div class="detail-actions">
                <button class="action-btn primary" @click="openLearning(selectedPoint)"><BookOpen :size="15" :stroke-width="1.75" />进入学习空间</button>
                <button class="action-btn" @click="goToPractice(selectedPoint)"><Target :size="15" :stroke-width="1.75" />推荐练习</button>
                <button class="action-btn" @click="askAi(selectedPoint)"><MessageCircle :size="15" :stroke-width="1.75" />让 AI 讲解</button>
                <button class="action-btn" @click="goToRelatedErrors(selectedPoint)"><BookX :size="15" :stroke-width="1.75" />查看全部关联错题</button>
              </div>
            </article>

            <!-- 章节/小节详情 -->
            <article v-else-if="selectedBranch" class="branch-detail">
              <div class="detail-header">
                <h2 class="detail-title">{{ selectedBranch.name }}</h2>
              </div>
              <p class="detail-desc">{{ selectedBranch.description || '选择下方知识点查看详情。' }}</p>
              <div class="detail-section">
                <div class="section-label">所含知识点</div>
                <div class="branch-points">
                  <button v-for="point in branchPoints" :key="point.id" class="branch-point-btn" @click="selectPoint(point.id)">
                    <span class="branch-point-name">{{ point.name }}</span>
                    <ChevronRight :size="14" :stroke-width="1.75" />
                  </button>
                </div>
              </div>
            </article>
          </aside>
        </div>
      </template>
    </div>
  </AppShell>
</template>

<script setup>
import { computed, defineAsyncComponent, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { BookOpen, BookX, ChevronRight, MessageCircle, Network, Target } from 'lucide-vue-next'
import AppShell from '@/components/shell/AppShell.vue'
import KnowledgeGraph2D from '@/components/knowledge/KnowledgeGraph2D.vue'
import { useEntranceAnimation } from '@/composables/useEntranceAnimation'
import { getCourseLearningMap, getCourseTree, getKnowledgePoint, getKnowledgePointLearning, listCourses } from '@/api/knowledge'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { useAuthStore } from '@/stores/authStore'
import { useLoginDialog } from '@/composables/useLoginDialog'

const router = useRouter()
const route = useRoute()
const errorBookStore = useErrorBookStore()
const authStore = useAuthStore()
const { openLogin } = useLoginDialog()
// Three.js is the primary knowledge-space view. The 2D dependency path remains
// available as a complementary, keyboard-friendly view for precise sequencing.
const KnowledgeGalaxy = defineAsyncComponent(() => import('@/components/knowledge/KnowledgeGalaxy.vue'))
const tree = ref(null)
const loading = ref(true)
const error = ref('')
const requiresAuth = ref(false)
const bodyEl = ref(null)
const playEntrance = useEntranceAnimation(() => bodyEl.value ?? undefined, { autoplay: false })
const selectedPoint = ref(null)
const selectedBranch = ref(null)
const pointLoading = ref(false)
const viewMode = ref('network')
const masteryMap = ref({}) // { code: { mastery, attempts, correct, status } }
const learningMap = ref(null)
const selectedResources = ref([])
const activeChapterId = ref('')
const viewHint = computed(() => ({
  '3d': '拖动旋转知识星球，滚轮缩放，点击节点查看学习内容。',
  network: '像 Obsidian 一样浏览知识网络：拖动节点、缩放画布，点击节点查看关联内容。',
  '2d': '按依赖顺序查看当前章节，箭头表示必要前置。'
}[viewMode.value]))

// 资源类型展示名
const RESOURCE_TYPE_LABELS = { lesson: '讲解', formula: '公式', example: '例题', exercise: '练习', intuition: '直觉', concept: '概念', definition: '定义', visual: '图解', animation: '动画', worked_example: '例题', common_error: '易错', exam_focus: '考点', checkpoint: '自检', exercise_set: '练习', summary: '小结', source_reference: '来源' }

// 登录成功后自动重新加载图谱
watch(() => authStore.isAuthenticated, (val) => {
  if (val && requiresAuth.value) {
    loadCatalog()
  }
})

const hasSelection = computed(() => selectedPoint.value || selectedBranch.value)

const chapterList = computed(() => (tree.value?.chapters || []).map(chapter => ({
  id: chapter.id,
  name: chapter.name,
  pointCount: (chapter.knowledge_points || []).length + (chapter.children || []).reduce((count, section) => count + (section.knowledge_points || []).length, 0)
})).filter(chapter => chapter.pointCount > 0))

const allPoints = computed(() => (tree.value?.chapters || []).flatMap(chapter => [
  ...(chapter.knowledge_points || []),
  ...(chapter.children || []).flatMap(section => section.knowledge_points || [])
].map(point => ({ ...point, chapterId: chapter.id }))))

const startingPoint = computed(() => {
  const recommendedId = learningMap.value?.primary_recommendation?.knowledge_point_id
  const recommended = allPoints.value.find(point => point.id === recommendedId)
  if (recommended) return recommended
  const inChapter = allPoints.value.filter(point => point.chapterId === activeChapterId.value)
  return inChapter.find(point => !(point.prerequisites || []).length) || inChapter[0] || allPoints.value[0] || null
})
const primaryRecommendation = computed(() => learningMap.value?.primary_recommendation || null)
const learningStateByCode = computed(() => Object.fromEntries((learningMap.value?.points || []).map(point => [point.code, point])))
const selectedLearningState = computed(() => selectedPoint.value ? learningStateByCode.value[selectedPoint.value.code] : null)
const missingPrerequisiteNames = computed(() => (selectedLearningState.value?.missing_prerequisites || []).map(code => allPoints.value.find(point => point.code === code)?.name || code))

const branchPoints = computed(() => {
  if (!selectedBranch.value) return []
  return selectedBranch.value.knowledge_points || selectedBranch.value.children?.flatMap(section => section.knowledge_points || []) || []
})

const childPoints = computed(() => {
  if (!selectedPoint.value || !tree.value) return []
  const all = []
  tree.value.chapters.forEach(ch => {
    ch.children.forEach(sec => {
      sec.knowledge_points?.forEach(kp => {
        if (kp.id !== selectedPoint.value.id) {
          if (kp.name?.includes(selectedPoint.value.name?.slice(0, 2)) ||
              selectedPoint.value.name?.includes(kp.name?.slice(0, 2))) {
            all.push({ id: kp.id, name: kp.name })
          }
        }
      })
    })
  })
  return all.slice(0, 6)
})

const MASTERY_LABELS = {
  mastered: '已掌握',
  learning: '学习中',
  weak: '薄弱',
  untouched: '未学'
}

// 掌握度只展示后端答题证据；无记录时明确提示证据不足。
const masteryInfo = computed(() => {
  if (!selectedPoint.value) return null
  const entry = masteryMap.value[selectedPoint.value.code]
  if (entry && entry.attempts > 0) return entry
  return null
})

const masteryPercent = computed(() => {
  const info = masteryInfo.value
  if (info) return Math.round(info.mastery * 100)
  return 0 // 没有独立答题证据，不能用错题自评或固定 60% 代替。
})

const masteryLabel = computed(() => {
  const info = masteryInfo.value
  if (info) return MASTERY_LABELS[info.status] || '未学'
  return '证据不足'
})

const relatedErrors = computed(() => {
  if (!selectedPoint.value) return []
  return errorBookStore.errors
    .filter(e => e.categories?.some(c => selectedPoint.value.name?.includes(c) || c?.includes(selectedPoint.value.name)))
    .slice(0, 3)
})

async function loadCatalog() {
  loading.value = true; error.value = ''; requiresAuth.value = false
  try {
    const { data } = await listCourses()
    if (!data.courses?.length) throw new Error('暂时没有可学习的已发布课程。')
    const courseId = data.courses[0].id
    tree.value = (await getCourseTree(courseId)).data
    const requestedPoint = allPoints.value.find(point => point.id === route.query.point)
    activeChapterId.value = requestedPoint?.chapterId || (chapterList.value.some(chapter => chapter.id === route.query.chapter) ? route.query.chapter : chapterList.value[0]?.id || '')
    await loadLearningMap(courseId)
    const recommended = allPoints.value.find(point => point.id === learningMap.value?.primary_recommendation?.knowledge_point_id)
    if (!requestedPoint && recommended?.chapterId) activeChapterId.value = recommended.chapterId
    if (requestedPoint) await selectPoint(requestedPoint.id, { updateRoute: false })
    await nextTick()
    playEntrance()
  } catch (err) {
    requiresAuth.value = err.response?.status === 401
    error.value = requiresAuth.value
      ? '课程图谱只向已登录的学习用户开放。'
      : (err.response?.data?.detail || err.message || '课程图谱加载失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

async function loadLearningMap(courseId) {
  try {
    const { data } = await getCourseLearningMap(courseId)
    learningMap.value = data
    masteryMap.value = Object.fromEntries((data.points || []).map(point => [point.code, { ...point, status: point.status === 'unlearned' ? 'untouched' : point.status }]))
  } catch {
    // 个人投影失败不影响公共课程结构浏览。
    learningMap.value = null
    masteryMap.value = {}
  }
}

function selectBranch(branch) {
  selectedPoint.value = null
  selectedBranch.value = branch
}

function selectChapter(chapterId, { updateRoute = true } = {}) {
  if (!chapterId || activeChapterId.value === chapterId) return
  activeChapterId.value = chapterId
  selectedPoint.value = null
  selectedBranch.value = null
  selectedResources.value = []
  if (updateRoute) router.push({ query: { ...route.query, chapter: chapterId, point: undefined } })
}

async function selectPoint(id, { updateRoute = true } = {}) {
  const summary = allPoints.value.find(point => point.id === id)
  if (summary?.chapterId) activeChapterId.value = summary.chapterId
  selectedBranch.value = null
  pointLoading.value = true
  selectedPoint.value = null
  selectedResources.value = []
  try {
    const [pointResp, learningResp] = await Promise.all([
      getKnowledgePoint(id),
      getKnowledgePointLearning(id)
    ])
    selectedPoint.value = pointResp.data
    selectedResources.value = learningResp.data?.resources || []
    if (updateRoute && route.query.point !== id) router.push({ query: { ...route.query, chapter: summary?.chapterId || activeChapterId.value, point: id } })
  } catch {
    ElMessage.error('知识点详情加载失败，请重试。')
  } finally {
    pointLoading.value = false
  }
}

watch(() => [route.query.chapter, route.query.point], async ([chapterId, pointId]) => {
  if (!tree.value) return
  if (pointId && pointId !== selectedPoint.value?.id) {
    await selectPoint(pointId, { updateRoute: false })
  } else if (!pointId) {
    selectedPoint.value = null
    selectedResources.value = []
    if (chapterId && chapterId !== activeChapterId.value) selectChapter(chapterId, { updateRoute: false })
  }
})

function openLearning(point) {
  router.push(`/knowledge/points/${point.id}/learn`)
}

function goToRelatedErrors(point) {
  router.push({ path: '/error-book', query: { search: point.name } })
}

function goToPractice(point) {
  router.push({ path: '/apply/practice', query: { knowledge_point: point.code } })
}

function askAi(point) {
  router.push({ path: '/chat', query: { course_id: tree.value.course.id, version_id: tree.value.version.id, knowledge_point: point.code, q: `请结合课程内容讲解「${point.name}」，先确认我的理解，再分步引导。` } })
}

onMounted(loadCatalog)
</script>

<style lang="scss" scoped>
.catalog {
  overflow: hidden;
  display: flex;
  flex-direction: column;
  padding: 20px 24px 24px;
  width: 100%;
  height: 100%;
}

.catalog-intro {
  margin-bottom: var(--space-4);
}
.catalog-title {
  margin: 0;
  font-size: 24px;
  letter-spacing: -0.01em;
  color: var(--ink-1);
  font-weight: 700;
}
.catalog-desc {
  margin: 4px 0 0;
  font-size: 13.5px;
  color: var(--ink-2);
}

.version-badge {
  padding: 4px 10px;
  border-radius: var(--r-pill);
  background: var(--brand-soft);
  color: var(--brand-text);
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

/* 图例栏 */
.legend-bar {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 10px 14px;
  margin: 12px 0 14px;
  border-radius: 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-1);
  font-size: 12.5px;
  color: var(--ink-2);
}
.legend-bar .legend-hint { margin-left: 0; font-size: 13px; }

.legend-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.02em;
}

.view-toggle {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--surface);
  box-shadow: var(--shadow-1);
}

.view-toggle button {
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font: inherit;
  font-size: 12.5px;
  font-weight: 500;
  padding: 5px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}

.view-toggle button.active {
  background: var(--brand-soft-2);
  color: var(--brand-text);
  font-weight: 600;
}

/* 图谱 + 详情布局 */
.graph-layout {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
}

.chapter-nav {
  width: 210px;
  flex: 0 0 auto;
  padding: 14px;
  overflow-y: auto;
}

.chapter-nav-label { margin: 0 8px 10px; color: var(--ink-3); font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.chapter-nav button { width: 100%; min-height: 56px; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 3px; margin-bottom: 4px; padding: 8px 10px; border: 0; border-radius: 10px; background: transparent; color: var(--ink-1); font: inherit; text-align: left; cursor: pointer; transition: background .15s; }
.chapter-nav button:hover { background: var(--surface-2); }
.chapter-nav button.active { background: var(--brand-soft-2); }
.chapter-nav button:focus-visible { outline: 2px solid var(--brand); outline-offset: 2px; }
.chapter-nav button span { font-size: 13.5px; font-weight: 600; }
.chapter-nav button.active span { color: var(--brand-text); }
.chapter-nav button small { color: var(--ink-3); font-size: 12px; }

.graph-area {
  flex: 1;
  min-width: 0;
  border-radius: var(--r-l);
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--surface-2);
}

/* 右侧详情面板 */
.detail-panel {
  width: 340px;
  flex-shrink: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.detail-panel--empty {
  justify-content: flex-start;
}

/* 空状态 */
.detail-empty {
  padding: 28px 24px;
  color: var(--ink-2);
}

.detail-empty-icon {
  width: 42px;
  height: 42px;
  margin-bottom: 16px;
  display: grid;
  place-items: center;
  border-radius: 12px;
  background: var(--brand-soft);
  color: var(--brand-text);
}

.detail-empty p {
  margin: 0 0 14px;
  font-size: 13.5px;
  line-height: 1.6;
}
.detail-empty .start-kicker { margin-bottom: 4px; color: var(--accent-text); font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }
.detail-empty h2 { margin: 0 0 10px; color: var(--ink-1); font-size: 20px; line-height: 1.35; }
.detail-empty ul { margin: 18px 0; padding-left: 20px; color: var(--ink-2); font-size: 13.5px; line-height: 1.8; }
.start-button { width: 100%; min-height: 44px; border: 1px solid var(--accent); border-radius: 10px; background: var(--accent); color: #fff; font: inherit; font-weight: 600; font-size: 14px; cursor: pointer; transition: background .15s, box-shadow .15s; }
.start-button:hover { background: var(--accent-strong); box-shadow: var(--glow); }

/* 加载中 */
.detail-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 24px;
  color: var(--ink-3);
  font-size: 13px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

/* 知识点详情 */
.point-detail {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.detail-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.detail-title {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
  color: var(--ink-1);
  line-height: 1.4;
}

.difficulty-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--ink-2);
  white-space: nowrap;
}

.detail-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink-2);
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
  letter-spacing: 0.03em;
}

.mastery-progress { width: 100%; }

.mastery-text {
  font-size: 12px;
  color: var(--ink-3);
}

.mastery-status {
  font-style: normal;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: var(--r-pill);
  margin-right: 2px;
}

.mastery-status.mastered { background: var(--green-soft); color: var(--green); }
.mastery-status.learning { background: var(--amber-soft); color: var(--amber); }
.mastery-status.weak { background: var(--rose-soft); color: var(--rose); }
.mastery-status.untouched { background: var(--surface-2); color: var(--ink-2); }

/* 学习资源 */
.resource-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.resource-item {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--surface-2);
}

.resource-type {
  flex-shrink: 0;
  align-self: flex-start;
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: var(--r-pill);
  background: var(--brand-soft);
  color: var(--brand-text);
}

.resource-body {
  min-width: 0;
}

.resource-title {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--ink-1);
  line-height: 1.4;
}

.resource-desc {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 1.55;
  color: var(--ink-3);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 关联错题 */
.related-errors {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.related-error-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--surface);
  cursor: pointer;
  font: inherit;
  text-align: left;
  transition: border-color .15s, background .15s;
}

.related-error-item:hover {
  background: var(--surface-2);
  border-color: var(--border-strong);
}

.related-error-q {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12.5px;
  color: var(--ink-2);
}

.related-error-state {
  flex-shrink: 0;
  font-size: 10.5px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: var(--r-pill);
}

.related-error-state.ok { background: var(--green-soft); color: var(--green); }
.related-error-state.bad { background: var(--rose-soft); color: var(--rose); }

/* 列表 */
.detail-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-list li {
  padding: 6px 10px;
  border-radius: 8px;
  background: var(--surface-2);
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--ink-2);
}

.formula-list li {
  font-family: var(--font-mono);
  font-size: 12.5px;
}

/* 子知识点标签 */
.child-points {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.child-point-tag {
  padding: 4px 10px;
  border-radius: var(--r-pill);
  background: var(--brand-soft);
  color: var(--brand-text);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.child-point-tag:hover {
  background: var(--brand-soft-2);
}

/* 操作按钮 */
.detail-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  min-height: 44px;
  border-radius: 10px;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--ink-2);
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  font-family: inherit;
}

.action-btn:hover {
  background: var(--brand-soft);
  color: var(--brand-text);
  border-color: var(--brand);
}

.action-btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.action-btn.primary:hover {
  background: var(--accent-strong);
  border-color: var(--accent-strong);
  box-shadow: var(--glow);
}

/* 章节/分支详情 */
.branch-detail {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.branch-points {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.branch-point-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--surface);
  cursor: pointer;
  text-align: left;
  transition: background 0.15s, border-color 0.15s;
  font-family: inherit;
  color: var(--ink-1);
  width: 100%;
}

.branch-point-btn:hover {
  background: var(--surface-2);
  border-color: var(--border-strong);
}

.branch-point-btn svg {
  color: var(--ink-3);
  flex-shrink: 0;
}

.branch-point-name {
  font-size: 13px;
  font-weight: 500;
}

/* 状态 */
.state {
  padding: 64px 20px;
  text-align: center;
  color: var(--ink-2);
}

.state.error-state h2 {
  color: var(--ink-1);
  font-size: 18px;
  margin-bottom: 8px;
}

.state.error-state p {
  color: var(--ink-3);
  margin-bottom: 16px;
}

.state.error-state button {
  min-height: 40px;
  border: 0;
  border-radius: 10px;
  padding: 0 18px;
  background: var(--accent);
  color: #fff;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition: background .15s;
}

.state.error-state button:hover { background: var(--accent-strong); }

/* 响应式 */
@media (max-width: 1100px) {
  .graph-layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 300px;
    grid-template-rows: auto minmax(0, 1fr);
  }
  .chapter-nav {
    grid-column: 1 / -1;
    width: 100%;
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding: 10px;
  }
  .chapter-nav-label { display: none; }
  .chapter-nav button { min-width: 180px; margin: 0; }
  .detail-panel {
    width: 300px;
  }
}

@media (max-width: 900px) {
  .graph-layout {
    display: flex;
    flex-direction: column;
  }

  .graph-area {
    flex: 1;
    min-height: 400px;
  }

  .chapter-nav { width: 100%; display: flex; gap: 8px; overflow-x: auto; padding: 10px; }
  .chapter-nav-label { display: none; }.chapter-nav button { min-width: 160px; margin: 0; }

  .detail-panel {
    width: 100%;
    max-height: 45vh;
    flex-shrink: 0;
  }

  .legend-hint {
    display: none;
  }
}

@media (max-width: 600px) {
  .catalog {
    padding: 12px 10px 16px;
    height: auto;
    min-height: 100%;
    overflow: visible;
  }

  .catalog-title {
    font-size: 20px;
  }

  .catalog-desc {
    font-size: 12px;
  }

  .legend-bar {
    gap: 10px;
    padding: 8px 10px;
    font-size: 11px;
    flex-wrap: wrap;
  }

  .graph-area {
    min-height: 0;
    overflow: visible;
  }

  .detail-panel {
    max-height: none;
    overflow: visible;
  }

  .view-toggle button { min-height: 44px; padding-inline: 14px; }
}

.unlock-notice,
.review-notice {
  margin: 0 0 16px;
  padding: 12px 14px;
  border: 1px dashed var(--border-strong);
  border-radius: 10px;
  background: var(--surface-2);
  color: var(--ink-1);
}
.review-notice { border-style: solid; border-color: var(--accent); background: var(--accent-soft); }
.review-notice strong { color: var(--accent-text); }
.unlock-notice p,
.review-notice p { margin: 4px 0 0; color: var(--ink-2); line-height: 1.5; }

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
</style>
