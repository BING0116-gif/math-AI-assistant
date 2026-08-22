<template>
  <AppShell>
    <template #topbar-title>
      <span>知识星球</span>
    </template>
    <template #topbar-actions>
      <span v-if="tree" class="version-badge">{{ tree.version.name }}</span>
    </template>

    <div class="catalog" :aria-busy="loading">
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
        <!-- 顶部图例 -->
        <div class="legend-bar">
          <span class="legend-item"><span class="legend-dot root"></span>课程</span>
          <span class="legend-item"><span class="legend-dot chapter"></span>章节</span>
          <span class="legend-item"><span class="legend-dot section"></span>小节</span>
          <span class="legend-item"><span class="legend-dot point"></span>知识点</span>
          <span class="legend-hint">拖动旋转 · 滚轮缩放 · 点击节点查看详情</span>
        </div>

        <!-- 图谱 + 详情面板 -->
        <div class="graph-layout">
          <div class="graph-area">
            <KnowledgeGalaxy :tree="tree" @select-point="selectPoint" @select-branch="selectBranch" />
          </div>
          <aside class="detail-panel" :class="{ 'detail-panel--empty': !hasSelection }">
            <!-- 空状态 -->
            <div v-if="!hasSelection" class="detail-empty">
              <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.2" class="detail-empty-icon">
                <circle cx="24" cy="24" r="20"/>
                <path d="M24 14v12M24 30v2"/>
              </svg>
              <p>点击图谱中的知识点节点查看详情</p>
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

              <!-- 掌握度 -->
              <div class="detail-section">
                <div class="section-label">掌握度</div>
                <div class="mastery-bar-track">
                  <div class="mastery-bar-fill" :style="{ width: masteryPercent + '%' }"></div>
                </div>
                <span class="mastery-text">{{ masteryLabel }}</span>
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
                <button class="action-btn primary" @click="openLearning(selectedPoint)">进入学习空间</button>
                <button class="action-btn" @click="goToRelatedErrors(selectedPoint)">关联错题</button>
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
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 18 6-6-6-6"/></svg>
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
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AppShell from '@/components/shell/AppShell.vue'
import KnowledgeGalaxy from '@/components/knowledge/KnowledgeGalaxy.vue'
import { getCourseTree, getKnowledgePoint, listCourses } from '@/api/knowledge'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { useAuthStore } from '@/stores/authStore'
import { useLoginDialog } from '@/composables/useLoginDialog'

const router = useRouter()
const errorBookStore = useErrorBookStore()
const authStore = useAuthStore()
const { openLogin } = useLoginDialog()
const tree = ref(null)
const loading = ref(true)
const error = ref('')
const requiresAuth = ref(false)
const selectedPoint = ref(null)
const selectedBranch = ref(null)
const pointLoading = ref(false)

// 登录成功后自动重新加载图谱
watch(() => authStore.isAuthenticated, (val) => {
  if (val && requiresAuth.value) {
    loadCatalog()
  }
})

const hasSelection = computed(() => selectedPoint.value || selectedBranch.value)

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

const masteryPercent = computed(() => {
  if (!selectedPoint.value) return 0
  const relatedErrors = errorBookStore.errors.filter(e =>
    e.categories?.some(c => selectedPoint.value.name?.includes(c) || c?.includes(selectedPoint.value.name))
  )
  if (relatedErrors.length === 0) return 60
  const mastered = relatedErrors.filter(e => e.is_mastered).length
  return Math.round((mastered / relatedErrors.length) * 100)
})

const masteryLabel = computed(() => {
  const p = masteryPercent.value
  if (p >= 80) return '掌握良好'
  if (p >= 60) return '基本掌握'
  if (p >= 40) return '部分掌握'
  return '需要加强'
})

async function loadCatalog() {
  loading.value = true; error.value = ''; requiresAuth.value = false
  try {
    const { data } = await listCourses()
    if (!data.courses?.length) throw new Error('暂时没有可学习的已发布课程。')
    tree.value = (await getCourseTree(data.courses[0].id)).data
  } catch (err) {
    requiresAuth.value = err.response?.status === 401
    error.value = requiresAuth.value
      ? '课程图谱只向已登录的学习用户开放。'
      : (err.response?.data?.detail || err.message || '课程图谱加载失败，请稍后重试。')
  } finally {
    loading.value = false
  }
}

function selectBranch(branch) {
  selectedPoint.value = null
  selectedBranch.value = branch
}

async function selectPoint(id) {
  selectedBranch.value = null
  pointLoading.value = true
  selectedPoint.value = null
  try {
    selectedPoint.value = (await getKnowledgePoint(id)).data
  } catch {
    ElMessage.error('知识点详情加载失败，请重试。')
  } finally {
    pointLoading.value = false
  }
}

function openLearning(point) {
  router.push(`/knowledge/points/${point.id}/learn`)
}

function goToRelatedErrors(point) {
  router.push({ path: '/error-book', query: { search: point.name } })
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
  font-size: var(--font-size-xl);
  color: var(--text-primary);
  font-weight: 700;
}
.catalog-desc {
  margin: 2px 0 0;
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
}

.version-badge {
  padding: 5px 10px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent);
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
  border-radius: var(--radius-sm);
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  font-size: 12px;
  color: var(--text-secondary);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-dot.root { background: #C8913D; }
.legend-dot.chapter { background: #5F947C; }
.legend-dot.section { background: #417E7A; }
.legend-dot.point { background: #5A8A8A; }

.legend-hint {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-tertiary);
  letter-spacing: 0.02em;
}

/* 图谱 + 详情布局 */
.graph-layout {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
  overflow: hidden;
}

.graph-area {
  flex: 1;
  min-width: 0;
  border-radius: var(--radius-lg);
  overflow: hidden;
  border: 1px solid var(--border-subtle);
  background: #0B1924;
}

/* 右侧详情面板 */
.detail-panel {
  width: 340px;
  flex-shrink: 0;
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
  background: var(--surface);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}

.detail-panel--empty {
  align-items: center;
  justify-content: center;
}

/* 空状态 */
.detail-empty {
  text-align: center;
  padding: 48px 24px;
  color: var(--text-tertiary);
}

.detail-empty-icon {
  width: 48px;
  height: 48px;
  margin-bottom: 16px;
  opacity: 0.4;
}

.detail-empty p {
  font-size: 13px;
  line-height: 1.6;
}

/* 加载中 */
.detail-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 60px 24px;
  color: var(--text-tertiary);
  font-size: 13px;
}

.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border-subtle);
  border-top-color: var(--accent);
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
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.4;
}

.difficulty-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: var(--radius-pill);
  background: var(--accent-soft);
  color: var(--accent);
  white-space: nowrap;
}

.detail-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.section-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0.03em;
}

/* 掌握度条 */
.mastery-bar-track {
  height: 6px;
  border-radius: 999px;
  background: var(--surface-muted);
  overflow: hidden;
}

.mastery-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.4s ease;
}

.mastery-text {
  font-size: 12px;
  color: var(--text-tertiary);
}

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
  border-radius: 6px;
  background: var(--surface-muted);
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.formula-list li {
  font-family: var(--font-mono);
  font-size: 12px;
}

/* 子知识点标签 */
.child-points {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.child-point-tag {
  padding: 4px 10px;
  border-radius: var(--radius-pill);
  background: var(--knowledge-soft);
  color: var(--knowledge);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.child-point-tag:hover {
  background: var(--accent-soft);
  color: var(--accent);
}

/* 操作按钮 */
.detail-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
}

.action-btn {
  width: 100%;
  min-height: 38px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border-subtle);
  background: var(--surface);
  color: var(--text-secondary);
  transition: background 0.15s, color 0.15s, border-color 0.15s;
  font-family: inherit;
}

.action-btn:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
  border-color: var(--border-strong);
}

.action-btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.action-btn.primary:hover {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
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
  border-radius: 8px;
  border: 1px solid var(--border-subtle);
  background: var(--surface);
  cursor: pointer;
  text-align: left;
  transition: background 0.15s, border-color 0.15s;
  font-family: inherit;
  color: var(--text-primary);
  width: 100%;
}

.branch-point-btn:hover {
  background: var(--surface-hover);
  border-color: var(--border-strong);
}

.branch-point-btn svg {
  color: var(--text-tertiary);
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
  color: var(--text-secondary);
}

.state.error-state h2 {
  color: var(--text-primary);
  font-size: 18px;
  margin-bottom: 8px;
}

.state.error-state p {
  color: var(--text-tertiary);
  margin-bottom: 16px;
}

.state.error-state button {
  min-height: 40px;
  border: 0;
  border-radius: var(--radius-sm);
  padding: 0 18px;
  background: var(--accent);
  color: #fff;
  font: inherit;
  font-weight: 600;
  cursor: pointer;
}

/* 响应式 */
@media (max-width: 1100px) {
  .detail-panel {
    width: 300px;
  }
}

@media (max-width: 900px) {
  .graph-layout {
    flex-direction: column;
  }

  .graph-area {
    flex: 1;
    min-height: 400px;
  }

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
  }

  .catalog-header h1 {
    font-size: 17px;
  }

  .header-desc {
    font-size: 12px;
  }

  .legend-bar {
    gap: 10px;
    padding: 8px 10px;
    font-size: 11px;
    flex-wrap: wrap;
  }

  .graph-area {
    min-height: 320px;
  }

  .detail-panel {
    max-height: 50vh;
  }
}

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
</style>