<template>
  <div class="card err-card" :class="{ 'err-card--due': due }">
    <!-- 头部:科目标签 + 今日到期 pill + 录入时间 -->
    <div class="head">
      <span v-if="primaryCategory" class="tag tag-soft-accent">{{ primaryCategory }}</span>
      <span v-if="due" class="pill-alert">
        <Clock class="pill-ic" :stroke-width="2" aria-hidden="true" />今日待复习
      </span>
      <span v-if="addedShort" class="when">录入于 {{ addedShort }}</span>
    </div>

    <!-- 题目 -->
    <div class="q" role="button" tabindex="0" @click="openDetail" @keydown.enter="openDetail">
      <span v-if="isImage" class="image-q">
        <img :src="error.question" class="q-thumb" @click.stop="openViewer" @error="onImgError" />
        <span class="recognized-preview">{{ error.recognized_text || '[图片题目]' }}</span>
      </span>
      <div v-else class="q-text math-area" v-html="questionHtml"></div>
    </div>

    <!-- 错因 -->
    <div class="why">{{ error.error_reason || '暂无分析，点击查看详情与解析' }}</div>

    <!-- 掌握度 -->
    <div class="foot">
      <span class="caption foot-label">掌握度</span>
      <span class="progress"><i :class="stageBarClass" :style="{ width: masteryPct + '%' }"></i></span>
      <span class="pv">{{ masteryPct }}</span>
      <span class="caption">{{ graduationStage.label }}</span>
    </div>

    <!-- 操作 -->
    <div class="acts">
      <button class="act" type="button" @click.stop="toggleSolution">
        {{ solutionVisible ? '收起解析' : '查看解析' }}
      </button>
      <button class="act" type="button" @click.stop="openDetail">再次练习</button>
      <button
        class="act variant"
        type="button"
        :class="{ disabled: !hasVariantSupport || variantLoading }"
        :disabled="!hasVariantSupport || variantLoading"
        @click.stop="handleVariant"
      >
        {{ variantLoading ? '正在生成…' : '变式训练' }}
      </button>
    </div>

    <!-- 展开解析 -->
    <div v-if="solutionVisible" class="card-solution">
      <div class="solution-header">正确解答</div>
      <div class="solution-content math-area" v-html="solutionHtml"></div>
    </div>

    <Teleport to="body">
      <div v-if="viewerOpen" class="image-viewer-overlay" @click="viewerOpen = false">
        <img :src="error.question" class="viewer-img" @click.stop />
        <button class="viewer-close" aria-label="关闭预览" @click="viewerOpen = false">✕</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Clock } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { renderMarkdown } from '@/utils/markdown'
import { createVariantSession } from '@/api/errorBook'

const props = defineProps({
  error: { type: Object, required: true },
  index: Number,
  /** 该错题今日到期(由父视图按复习排期计算) */
  due: Boolean
})

const emit = defineEmits(['viewDetail', 'toggleMastery', 'delete'])

const viewerOpen = ref(false)
const solutionVisible = ref(false)
const variantLoading = ref(false)
const router = useRouter()

const isImage = computed(() =>
  props.error.question_type === 'image' ||
  (props.error.question && props.error.question.startsWith('data:image'))
)

const displayQuestion = computed(() =>
  props.error.display_question || props.error.question || ''
)

/* 题干含 $...$ LaTeX,与解析同走 markdown-it + KaTeX 渲染 */
const questionHtml = computed(() => renderMarkdown(displayQuestion.value))

const solutionHtml = computed(() =>
  renderMarkdown(props.error.correct_answer || '暂无解析内容')
)

const primaryCategory = computed(() => props.error.categories?.[0] || '')

const addedShort = computed(() => {
  if (!props.error.added_at) return ''
  try {
    const date = new Date(props.error.added_at)
    if (isNaN(date.getTime())) return ''
    return `${date.getMonth() + 1}/${date.getDate()}`
  } catch {
    return ''
  }
})

const masteryPct = computed(() =>
  Math.round(((props.error.mastery_level || 3) / 5) * 100)
)

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

/* 掌握度条颜色语义(§3.1):薄弱 rose / 复习中 amber / 巩固 brand / 已掌握 green */
const stageBarClass = computed(() => {
  const cls = graduationStage.value.class
  if (cls === 'new') return 'rose'
  if (cls === 'understanding') return 'amber'
  if (cls === 'mastered') return 'green'
  return ''
})

const hasVariantSupport = computed(() => props.error.variant_supported === true)

async function handleVariant() {
  if (!hasVariantSupport.value || variantLoading.value) {
    ElMessage.info('该题暂不支持可验证变式')
    return
  }
  variantLoading.value = true
  try {
    const idempotencyKey = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`
    const response = await createVariantSession(props.error.id, { idempotency_key: idempotencyKey })
    const data = response?.data?.data ?? response?.data
    if (!data?.session_id) throw new Error('服务端未返回练习会话')
    ElMessage.success('变式已通过数学验证')
    await router.push(`/apply/practice/sessions/${data.session_id}`)
  } catch (error) {
    const detail = error?.response?.data?.detail
    const code = detail?.code
    const fallback = code === 'VARIANT_DUPLICATE_EXHAUSTED'
      ? '暂时没有生成不重复的变式，请稍后重试'
      : code === 'VARIANT_NOT_SUPPORTED'
        ? '该题暂不支持可验证变式'
        : '变式生成失败，请重试'
    ElMessage.error(detail?.message || error?.message || fallback)
  } finally {
    variantLoading.value = false
  }
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

<style scoped>
/* err-card(对照 error-book.html;卡片基底用全局 .card) */
.err-card {
  padding: 16px 18px;
  transition: border-color 0.16s, box-shadow 0.16s;
}
.err-card:hover {
  border-color: var(--brand);
  box-shadow: var(--shadow-3);
}
.err-card--due {
  border-color: var(--accent);
}

/* ── 头部 ── */
.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 9px;
}
.head .when {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--ink-3);
}
.pill-ic {
  width: 11px;
  height: 11px;
}

/* ── 题目 ── */
.q {
  margin-bottom: 5px;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.55;
  color: var(--ink-1);
  cursor: pointer;
  overflow-wrap: anywhere;
}
.q-text :deep(p) {
  margin: 0;
}
.q-text :deep(.katex) {
  font-size: 1.02em;
}
.image-q {
  display: flex;
  align-items: center;
  gap: 12px;
}
.q-thumb {
  max-width: 90px;
  max-height: 60px;
  object-fit: cover;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: zoom-in;
  transition: transform 0.15s;
}
.q-thumb:hover {
  transform: scale(1.04);
}
.recognized-preview {
  font-size: 12.5px;
  color: var(--ink-3);
  font-style: italic;
}

/* ── 错因 ── */
.why {
  font-size: 12.5px;
  color: var(--ink-3);
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ── 掌握度 ── */
.foot {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
}
.foot-label {
  flex: none;
}
.foot .progress {
  flex: 1;
}
.pv {
  font-family: var(--font-disp);
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}

/* ── 操作 ── */
.acts {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-top: 10px;
}
.act {
  padding: 2px 0;
  border: 0;
  background: none;
  color: var(--ink-3);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: color 0.15s;
}
.act:hover {
  color: var(--brand-text);
}
.act:disabled,
.act.disabled {
  color: var(--ink-4);
  cursor: not-allowed;
}

/* ── 展开解析 ── */
.card-solution {
  margin-top: 12px;
  padding: 12px 14px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 12px;
}
.solution-header {
  margin-bottom: 8px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--green);
}
.solution-content {
  font-size: 13.5px;
  line-height: 1.8;
  color: var(--ink-1);
  overflow-wrap: anywhere;
}
.solution-content :deep(.katex) { font-size: 1.05em !important; }
.solution-content :deep(.katex-display) { margin: 10px 0 !important; }

/* ── 图片预览 ── */
.image-viewer-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(9, 11, 15, 0.72);
}
.viewer-img {
  max-width: 92vw;
  max-height: 90vh;
  object-fit: contain;
  border-radius: 12px;
}
.viewer-close {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  font-size: 20px;
  cursor: pointer;
  transition: background 0.15s;
}
.viewer-close:hover {
  background: rgba(255, 255, 255, 0.24);
}
</style>
