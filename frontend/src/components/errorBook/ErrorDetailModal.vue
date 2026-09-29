<template>
  <div class="detail-overlay" @click.self="$emit('close')">
    <div class="detail-container">
      <div class="detail-header">
        <h2 class="t-2">错题详情</h2>
        <button class="icon-btn" aria-label="关闭" @click="$emit('close')">
          <X class="ic-15" :stroke-width="1.75" />
        </button>
      </div>

      <div class="detail-nav">
        <button class="btn btn-ghost btn-sm" :disabled="currentIndex <= 0" @click="$emit('prev')">
          <ChevronLeft class="ic-14" :stroke-width="1.75" />上一题
        </button>
        <span class="nav-counter num">{{ currentIndex + 1 }} / {{ total }}</span>
        <button class="btn btn-ghost btn-sm" :disabled="currentIndex >= total - 1" @click="$emit('next')">
          下一题<ChevronRight class="ic-14" :stroke-width="1.75" />
        </button>
      </div>

      <div class="detail-body">
        <section class="d-section">
          <h3 class="d-label">题目</h3>
          <div class="d-content">
            <template v-if="isImage">
              <img :src="error.question" class="d-image" @click="viewerOpen = true" />
              <p v-if="error.recognized_text" class="recognized"><strong>识别文本：</strong>{{ error.recognized_text }}</p>
            </template>
            <p v-else class="d-text">{{ displayQuestion }}</p>
          </div>
        </section>

        <section v-if="error.error_reason" class="d-section">
          <h3 class="d-label">错误原因</h3>
          <div class="d-content reason-box">
            <p>{{ error.error_reason }}</p>
          </div>
        </section>

        <section class="d-section">
          <h3 class="d-label">正确解答</h3>
          <div class="d-content answer-box math-area" ref="answerBox" v-html="answerHtml"></div>
        </section>

        <section v-if="error.notes" class="d-section">
          <h3 class="d-label">学习笔记</h3>
          <div class="d-content notes-box"><p>{{ error.notes }}</p></div>
        </section>

        <section v-if="error.categories?.length" class="d-section">
          <h3 class="d-label">分类标签</h3>
          <div class="tag-row">
            <span v-for="cat in error.categories" :key="cat" class="tag tag-soft-accent">{{ cat }}</span>
          </div>
        </section>

        <!-- ═══ AI 错题笔记（折叠区,位于弹窗主体内）═══ -->
        <section class="d-section">
          <div class="notes-toggle" role="button" tabindex="0" @click="notesOpen = !notesOpen" @keydown.enter="notesOpen = !notesOpen">
            <h3 class="d-label">AI 错题笔记</h3>
            <ChevronDown v-if="notesOpen" class="ic-14" :stroke-width="1.75" />
            <ChevronRight v-else class="ic-14" :stroke-width="1.75" />
          </div>
          <div v-if="notesOpen" class="d-content notes-box">
            <div class="note-item">
              <span class="note-label">知识点：</span>
              <span class="note-value">{{ notesData.knowledgePoints }}</span>
            </div>
            <div class="note-item">
              <span class="note-label">你的错误：</span>
              <span class="note-value">{{ notesData.myError }}</span>
            </div>
            <div class="note-item">
              <span class="note-label">正确思路：</span>
              <span class="note-value">{{ notesData.correctApproach }}</span>
            </div>
            <div class="note-item">
              <span class="note-label">以后注意：</span>
              <span class="note-value">{{ notesData.futureTip }}</span>
            </div>
          </div>
        </section>

        <section class="d-section">
          <h3 class="d-label">元信息</h3>
          <div class="meta-grid">
            <div class="meta-cell"><strong>添加时间：</strong>{{ error.added_at || '-' }}</div>
            <div class="meta-cell">
              <strong>掌握度：</strong>
              <span class="mastery-meter"><span class="progress"><i :class="masteryBarClass" :style="{ width: masteryPct + '%' }"></i></span><span class="num">{{ error.mastery_level || 3 }}/5</span></span>
            </div>
            <div class="meta-cell" :class="{ mastered: error.is_mastered }">
              <strong>状态：</strong>{{ error.is_mastered ? '已掌握' : '待复习' }}
            </div>
          </div>
        </section>
      </div>

      <div class="detail-footer">
        <button class="ft-btn danger" type="button" @click="$emit('delete')">
          <Trash2 class="ic-14" :stroke-width="1.75" />删除此错题
        </button>
        <button class="btn btn-primary" type="button" @click="$emit('toggleMastery')">
          <CircleCheck class="ic-15" :stroke-width="1.75" />{{ error.is_mastered ? '取消掌握' : '标记为已掌握' }}
        </button>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="viewerOpen" class="img-viewer" @click="viewerOpen = false">
        <img :src="error.question" class="v-img" @click.stop />
        <button class="v-close" aria-label="关闭预览" @click="viewerOpen = false">✕</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ChevronDown, ChevronLeft, ChevronRight, CircleCheck, Trash2, X } from 'lucide-vue-next'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps({
  error: Object,
  currentIndex: Number,
  total: Number
})

defineEmits(['close', 'prev', 'next', 'toggleMastery', 'delete'])

const viewerOpen = ref(false)
const answerBox = ref(null)
const notesOpen = ref(false)

const isImage = computed(() =>
  props.error?.question_type === 'image' ||
  (props.error?.question && props.error.question.startsWith('data:image'))
)

const displayQuestion = computed(() =>
  props.error?.display_question || props.error?.question || ''
)

const answerHtml = computed(() =>
  renderMarkdown(props.error?.correct_answer || '')
)

const masteryPct = computed(() =>
  Math.round(((props.error?.mastery_level || 3) / 5) * 100)
)

const masteryBarClass = computed(() => {
  const level = props.error?.mastery_level || 3
  if (props.error?.is_mastered || level >= 5) return 'green'
  if (level >= 4) return ''
  if (level >= 3) return 'amber'
  return 'rose'
})

/**
 * AI 错题笔记数据
 *
 * 当前使用已有的 error_reason、categories、correct_answer 字段生成笔记。
 * 未来接入 AI 接口后，可以返回更精准的 structured 错题分析笔记。
 */
const notesData = computed(() => {
  const e = props.error
  const cats = (e.categories || []).join('、') || '待分析'
  const errorReason = e.error_reason || '暂无分析'
  const answer = e.correct_answer || ''

  // 从 correct_answer 中提取简短思路摘要
  const approach = answer.length > 80
    ? answer.substring(0, 80) + '…'
    : answer || '查看正确解答了解详细思路'

  // 以后注意的提示——基于错误类型生成
  const futureTip = computeFutureTip(e.error_reason || '', cats)

  return {
    knowledgePoints: cats,
    myError: errorReason,
    correctApproach: approach,
    futureTip
  }
})

function computeFutureTip(errorReason, categories) {
  if (!errorReason) return '建议在 AI 对话中向系统询问针对本知识点的学习建议'
  if (errorReason.includes('定义域') || errorReason.includes('定义')) {
    return '看到根式、对数、分式、反三角函数时，优先检查定义域是否满足条件'
  }
  if (errorReason.includes('概念') || errorReason.includes('混淆')) {
    return `重新梳理「${categories}」相关概念的定义和适用条件，做题时先确认题目考察的知识点`
  }
  if (errorReason.includes('计算') || errorReason.includes('公式')) {
    return '计算时要逐步推导，避免跳步。关键公式建议先默写再代入'
  }
  if (errorReason.includes('条件') || errorReason.includes('遗漏')) {
    return '做题前先标出题目中的已知条件和隐含条件，再选择解题方法'
  }
  return '建议针对本知识点多做同类练习，巩固解题思路'
}
</script>

<style scoped>
/* BaseDialog 规范(§6.3):radius 20 / shadow-3 / 遮罩 rgba(9,11,15,.5) */
.detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(9, 11, 15, 0.5);
  animation: fadeIn 0.2s;
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.detail-container {
  display: flex;
  flex-direction: column;
  width: min(92vw, 880px);
  height: min(90vh, 750px);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 20px;
  box-shadow: var(--shadow-3);
  overflow: hidden;
  animation: modalIn 0.32s var(--ease-pop);
}

@keyframes modalIn {
  from { opacity: 0; transform: scale(0.96) translateY(16px); }
  to { opacity: 1; transform: none; }
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 0;
}
.detail-header h2 {
  margin: 0;
}

.detail-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
}
.nav-counter {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-2);
}
.detail-nav .btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.detail-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 20px;
}

.d-section {
  margin-bottom: 18px;
}
.d-label {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-1);
  letter-spacing: 0.01em;
}

.d-content {
  padding: 14px 16px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  line-height: 1.8;
}

.d-text {
  margin: 0;
  font-size: 14px;
  color: var(--ink-1);
  overflow-wrap: anywhere;
}
.d-image {
  max-width: 100%;
  max-height: 300px;
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: zoom-in;
}

.recognized {
  margin: 10px 0 0;
  font-size: 12.5px;
  color: var(--ink-3);
  font-style: italic;
}

/* 语义色内容盒:错因 rose / 解答 green / 笔记 amber(浅底 + 深字) */
.reason-box {
  background: var(--rose-soft);
  border-color: transparent;
}
.reason-box p {
  margin: 0;
  color: var(--ink-1);
}
.answer-box {
  background: var(--green-soft);
  border-color: transparent;
}
.notes-box {
  background: var(--amber-soft);
  border-color: transparent;
}

.math-area :deep(.katex) { font-size: 1.05em !important; }
.math-area :deep(.katex-display) { margin: 12px 0 !important; }

.notes-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 0;
  cursor: pointer;
  user-select: none;
  color: var(--ink-3);
  border-radius: 8px;
}
.notes-toggle:hover .d-label {
  color: var(--brand-text);
}
.notes-toggle .d-label {
  margin: 0;
}

.note-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 8px;
}
.note-item:last-child {
  margin-bottom: 0;
}
.note-label {
  flex-shrink: 0;
  min-width: 72px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-2);
}
.note-value {
  font-size: 13px;
  color: var(--ink-1);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.tag-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
}
.meta-cell {
  padding: 10px 14px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  font-size: 13px;
  color: var(--ink-2);
}
.meta-cell strong {
  color: var(--ink-1);
  font-weight: 600;
}
.meta-cell.mastered {
  background: var(--green-soft);
  border-color: transparent;
}
.mastery-meter {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 120px;
}
.mastery-meter .progress {
  flex: 1;
  min-width: 64px;
}
.mastery-meter .num {
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-1);
}

.detail-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
}

.ft-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 14px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: none;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.16s ease;
  color: var(--rose);
}
.ft-btn:hover {
  background: var(--rose-soft);
}

.img-viewer {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(9, 11, 15, 0.72);
}
.v-img {
  max-width: 95vw;
  max-height: 95vh;
  object-fit: contain;
  border-radius: 12px;
}
.v-close {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  font-size: 22px;
  cursor: pointer;
}
.v-close:hover {
  background: rgba(255, 255, 255, 0.24);
}
</style>
