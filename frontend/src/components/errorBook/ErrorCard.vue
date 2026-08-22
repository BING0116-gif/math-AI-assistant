<template>
  <div class="error-card" :class="graduationStage.class">
    <!-- Top Row: categories + status -->
    <div class="card-top">
      <div class="card-categories">
        <span v-for="cat in error.categories?.slice(0, 3)" :key="cat" class="cat-tag">{{ cat }}</span>
      </div>
      <span class="card-stage-badge" :class="graduationStage.class">
        {{ graduationStage.label }}
      </span>
    </div>

    <!-- Question Summary -->
    <div class="card-question" @click="openDetail">
      <div v-if="isImage" class="image-question">
        <img :src="error.question" class="q-thumb" @click.stop="openViewer" @error="onImgError" />
        <span class="recognized-preview">{{ error.recognized_text || '[图片题目]' }}</span>
      </div>
      <div v-else class="text-question">{{ displayQuestion }}</div>
    </div>

    <!-- Error Reason -->
    <div class="card-error-info">
      <span class="error-label">你的错误：</span>
      <span class="error-text">{{ error.error_reason || '暂无分析，点击查看详情' }}</span>
    </div>

    <!-- Error Type Tags + Meta -->
    <div class="card-meta-row">
      <div class="card-error-tags">
        <span v-for="cat in error.categories" :key="cat" class="error-type-tag">#{{ cat }}</span>
      </div>
      <div class="card-meta">
        <span class="meta-dot" :class="graduationStage.class"></span>
        <span class="meta-stage">{{ graduationStage.label }}</span>
        <span class="meta-sep">·</span>
        <span class="meta-time">{{ timeText }}</span>
      </div>
    </div>

    <!-- Action Buttons -->
    <div class="card-actions">
      <button class="action-btn" @click.stop="toggleSolution">
        {{ solutionVisible ? '收起解析' : '查看解析' }}
      </button>
      <button class="action-btn" @click.stop="openDetail">再次练习</button>
      <button
        class="action-btn variant"
        @click.stop="handleVariant"
        :class="{ disabled: !hasVariantSupport }"
      >
        变式训练
      </button>
    </div>

    <!-- Expandable Solution -->
    <div v-if="solutionVisible" class="card-solution">
      <div class="solution-header">正确解答</div>
      <div class="solution-content math-area" v-html="solutionHtml"></div>
    </div>

    <Teleport to="body">
      <div v-if="viewerOpen" class="image-viewer-overlay" @click="viewerOpen = false">
        <img :src="error.question" class="viewer-img" @click.stop />
        <button class="viewer-close" @click="viewerOpen = false">✕</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps({
  error: { type: Object, required: true },
  index: Number
})

const emit = defineEmits(['viewDetail', 'toggleMastery', 'delete'])

const viewerOpen = ref(false)
const solutionVisible = ref(false)

const isImage = computed(() =>
  props.error.question_type === 'image' ||
  (props.error.question && props.error.question.startsWith('data:image'))
)

const displayQuestion = computed(() =>
  props.error.display_question || props.error.question || ''
)

const solutionHtml = computed(() =>
  renderMarkdown(props.error.correct_answer || '暂无解析内容')
)

const timeText = computed(() => {
  if (!props.error.added_at) return ''
  try {
    const date = new Date(props.error.added_at)
    if (isNaN(date.getTime())) return props.error.added_at
    const now = new Date()
    const diff = Math.floor((now - date) / 86400000)
    if (diff === 0) return '今天'
    if (diff === 1) return '1 天前'
    if (diff < 30) return `${diff} 天前`
    return props.error.added_at
  } catch {
    return props.error.added_at
  }
})

/**
 * 毕业状态映射（前端计算，基于现有数据）
 *
 * 后端目前只有 is_mastered / mastery_level 两个状态字段，
 * 以下映射为四阶段毕业体系：
 *   新错 → 理解中 → 巩固中 → 稳定掌握
 *
 * 如需精确状态管理，需要后端扩展 graduation_status 字段。
 */
const graduationStage = computed(() => {
  const e = props.error
  const serverStages = {
    new: { label: '新错', class: 'new', level: 0 },
    understanding: { label: '理解中', class: 'understanding', level: 1 },
    consolidating: { label: '巩固中', class: 'consolidating', level: 3 },
    mastered: { label: '稳定掌握', class: 'mastered', level: 4 }
  }
  if (serverStages[e.review_state]) return serverStages[e.review_state]
  if (e.is_mastered) {
    return { label: '稳定掌握', class: 'mastered', level: 4 }
  }
  if ((e.mastery_level || 3) >= 4) {
    return { label: '巩固中', class: 'consolidating', level: 3 }
  }
  try {
    const added = new Date(e.added_at || Date.now()).getTime()
    const days = Math.floor((Date.now() - added) / 86400000)
    if (days <= 3) {
      return { label: '新错', class: 'new', level: 0 }
    }
  } catch { /* ignore */ }
  return { label: '理解中', class: 'understanding', level: 1 }
})

/**
 * 变式训练：前端标记是否需要后端支持
 * 当前项目无 POST /api/practice/generate-variant 端点
 */
const hasVariantSupport = computed(() => false)

function handleVariant() {
  ElMessage.info('变式练习生成需要后端 AI 支持，即将开放')
}

function toggleSolution() {
  solutionVisible.value = !solutionVisible.value
}

function openDetail() {
  emit('viewDetail', props.index)
}

function openViewer() { viewerOpen.value = true }
function onImgError(e) { e.target.style.display = 'none' }
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.error-card {
  padding: 18px 20px;
  background: var(--surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);

  &:hover {
    border-color: var(--border-strong);
    box-shadow: var(--shadow-sm);
  }

  /* Graduation stage left accent */
  border-left: 3px solid var(--border-subtle);
  &.new { border-left-color: var(--warning); }
  &.understanding { border-left-color: var(--accent); }
  &.consolidating { border-left-color: var(--teal); }
  &.mastered { border-left-color: var(--success); }
}

/* ── Top Row ── */
.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.card-categories {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.cat-tag {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  letter-spacing: 0.01em;
}

.card-stage-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  letter-spacing: 0.03em;
  flex-shrink: 0;

  &.new { color: var(--warning); background: rgba(200, 145, 61, 0.12); }
  &.understanding { color: var(--accent); background: var(--accent-soft); }
  &.consolidating { color: var(--teal); background: rgba(65, 137, 125, 0.12); }
  &.mastered { color: var(--success); background: rgba(95, 148, 124, 0.12); }
}

/* ── Question ── */
.card-question {
  margin-bottom: 10px;
  cursor: pointer;
}

.text-question {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.5;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.image-question {
  display: flex;
  align-items: center;
  gap: 12px;

  .q-thumb {
    max-width: 90px;
    max-height: 60px;
    object-fit: cover;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
    cursor: pointer;
    transition: transform var(--transition-fast);
    &:hover { transform: scale(1.05); }
  }

  .recognized-preview {
    font-size: 13px;
    color: var(--text-tertiary);
    font-style: italic;
  }
}

/* ── Error Reason ── */
.card-error-info {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 8px;
  padding: 6px 10px;
  background: #F8F4EA;
  border: 1px solid #F0EAD8;
  border-radius: var(--radius-sm);
}

.error-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--weak);
  flex-shrink: 0;
}

.error-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── Meta Row ── */
.card-meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.card-error-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.error-type-tag {
  font-size: 12px;
  color: var(--text-tertiary);
  font-weight: 500;
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.meta-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
  &.new { background: var(--warning); }
  &.understanding { background: var(--accent); }
  &.consolidating { background: var(--teal); }
  &.mastered { background: var(--success); }
}

.meta-stage {
  font-weight: 600;
  &.new { color: var(--warning); }
  &.understanding { color: var(--accent); }
  &.consolidating { color: var(--teal); }
  &.mastered { color: var(--success); }
}

.meta-sep { opacity: 0.4; }
.meta-time { font-weight: 400; }

/* ── Action Buttons ── */
.card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.action-btn {
  padding: 6px 16px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition-fast);
  white-space: nowrap;

  &:hover {
    border-color: var(--accent);
    color: var(--accent);
    background: var(--accent-soft);
  }

  &.variant {
    &.disabled {
      opacity: 0.6;
      cursor: not-allowed;
      &:hover {
        border-color: var(--border-strong);
        color: var(--text-tertiary);
        background: var(--surface);
      }
    }
    &:not(.disabled):hover {
      border-color: var(--teal);
      color: var(--teal);
      background: rgba(65, 137, 125, 0.08);
    }
  }
}

/* ── Expandable Solution ── */
.card-solution {
  margin-top: 14px;
  padding: 12px 14px;
  background: var(--surface-muted);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-sm);
  animation: slideDown 0.2s ease-out;
}

.solution-header {
  font-size: 13px;
  font-weight: 700;
  color: var(--success);
  margin-bottom: 8px;
}

.solution-content {
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary);

  :deep(.katex) { font-size: 1.05em !important; }
  :deep(.katex-display) { margin: 10px 0 !important; }
}

@keyframes slideDown {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ── Image Viewer ── */
.image-viewer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.8);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeIn 0.3s;
}

.viewer-img {
  max-width: 92vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: var(--radius-md);
}

.viewer-close {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.15);
  color: white;
  font-size: 22px;
  cursor: pointer;
  transition: background var(--transition-fast);
  &:hover { background: rgba(255, 255, 255, 0.25); }
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
