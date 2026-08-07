<template>
  <div class="error-card" :class="{ expanded }">
    <div class="card-header" @click="toggleExpand">
      <div class="card-main">
        <div class="question-area">
          <div v-if="isImage" class="image-question">
            <img :src="error.question" class="q-thumb" @click.stop="openViewer" @error="onImgError" />
            <span class="recognized-preview">{{ error.recognized_text || '[图片题目]' }}</span>
          </div>
          <div v-else class="text-question">{{ displayQuestion }}</div>
        </div>

        <div class="card-meta">
          <span class="meta-date">{{ error.added_at }}</span>
          <span class="meta-stars">{{ '★'.repeat(error.mastery_level || 3) }}{{ '☆'.repeat(5 - (error.mastery_level || 3)) }}</span>
          <span class="meta-status" :class="{ done: error.is_mastered }">{{ error.is_mastered ? '已掌握' : '待复习' }}</span>
        </div>
      </div>

      <button class="expand-btn" :class="{ rotated: expanded }">▼</button>
    </div>

    <div class="card-body">
      <div class="body-inner">
        <div v-if="error.error_reason" class="section reason-section">
          <div class="section-label">错误原因</div>
          <div class="section-text">{{ error.error_reason }}</div>
        </div>

        <div class="section answer-section">
          <div class="section-label">正确答案</div>
          <div class="section-text math-area" v-html="answerPreview" ref="answerRef"></div>
        </div>

        <div v-if="error.notes" class="section notes-section">
          <div class="section-label">学习笔记</div>
          <div class="section-text">{{ error.notes }}</div>
        </div>

        <div v-if="error.categories?.length" class="tags-row">
          <span v-for="cat in error.categories" :key="cat" class="tag">{{ cat }}</span>
        </div>

        <div class="card-actions">
          <button class="act-btn primary" @click.stop="$emit('viewDetail', index)">查看详情</button>
          <button class="act-btn" @click.stop="$emit('toggleMastery')">{{ error.is_mastered ? '取消掌握' : '标记掌握' }}</button>
          <button class="act-btn danger" @click.stop="$emit('delete')">删除</button>
        </div>
      </div>
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
import { ref, computed, watch, nextTick } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { escapeHtml } from '@/utils/helpers'

const props = defineProps({
  error: { type: Object, required: true },
  index: Number
})

defineEmits(['viewDetail', 'toggleMastery', 'delete'])

const expanded = ref(false)
const viewerOpen = ref(false)
const answerRef = ref(null)

const isImage = computed(() =>
  props.error.question_type === 'image' ||
  (props.error.question && props.error.question.startsWith('data:image'))
)

const displayQuestion = computed(() =>
  props.error.display_question || props.error.question || ''
)

const answerPreview = computed(() =>
  props.error.answer_preview || renderMarkdown(props.error.correct_answer || '')
)

watch(expanded, (val) => {
  if (val) {
    // 公式已由 renderMarkdown 在 computed 中渲染完成，无需二次处理
  }
})

function toggleExpand() { expanded.value = !expanded.value }

function openViewer() { viewerOpen.value = true }

function onImgError(e) {
  e.target.style.display = 'none'
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.error-card {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border-light);
  overflow: hidden;
  transition: all var(--transition-fast);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);

  &:hover { box-shadow: var(--shadow-md); }
  &.expanded { box-shadow: var(--shadow-md); }
}

.card-header {
  padding: 20px 22px;
  cursor: pointer; display: flex; gap: 16px;
  align-items: flex-start; user-select: none;
}

.card-main { flex: 1; min-width: 0; }

.question-area { margin-bottom: 10px; }

.text-question {
  font-size: 15px; font-weight: 600; line-height: 1.6;
  color: var(--text-primary);
}

.image-question {
  display: flex; align-items: center; gap: 14px;
  .q-thumb {
    max-width: 110px; max-height: 75px; object-fit: cover;
    border-radius: var(--radius-sm); border: 1px solid var(--border-default);
    cursor: pointer; transition: transform var(--transition-fast);
    &:hover { transform: scale(1.05); }
  }
  .recognized-preview { font-size: 13px; color: var(--text-tertiary); font-style: italic; }
}

.card-meta {
  display: flex; gap: 16px; align-items: center; font-size: 12px;
  color: var(--text-tertiary); flex-wrap: wrap;
}

.meta-stars { color: var(--accent); font-size: 13px; letter-spacing: 1px; }
.meta-status { font-weight: 600;
  &.done { color: var(--success); }
}

.expand-btn {
  background: none; border: none; font-size: 12px; color: var(--text-tertiary);
  cursor: pointer; padding: 5px 8px; border-radius: 4px;
  transition: all var(--transition-fast); margin-top: 2px;
  &.rotated { transform: rotate(180deg); color: var(--primary); }
  &:hover { background: var(--primary-ghost); }
}

.card-body {
  max-height: 0; overflow: hidden;
  transition: max-height 0.45s cubic-bezier(0.4, 0, 0.2, 1);
  .expanded & { max-height: 2000px; }
}

.body-inner {
  padding: 0 22px 22px;
  opacity: 0; transform: translateY(-8px);
  transition: all 0.3s ease 0.08s;
  .expanded & { opacity: 1; transform: translateY(0); }
}

.section { margin-bottom: 16px; }
.section-label { font-size: 13px; font-weight: 700; margin-bottom: 8px; }
.section-text { font-size: 14px; line-height: 1.8; color: var(--text-secondary); }

.reason-section {
  padding: 12px 16px;
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.15);
  border-radius: var(--radius-md);
  .section-label { color: var(--danger); }
}
.answer-section {
  padding: 14px 18px;
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.15);
  border-radius: var(--radius-md);
  .section-label { color: var(--success); }
}
.notes-section {
  padding: 10px 14px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.15);
  border-radius: var(--radius-md);
}

.math-area :deep(.katex) { font-size: 1.05em !important; }
.math-area :deep(.katex-display) { margin: 12px 0 !important; }

.tags-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.tag {
  padding: 4px 14px;
  background: var(--primary-ghost);
  border-radius: $radius-full;
  font-size: 12px;
  color: var(--primary);
  font-weight: 500;
}

.card-actions {
  display: flex; gap: 10px; justify-content: flex-end;
  padding-top: 14px; border-top: 1px solid var(--border-light);
}

.act-btn {
  padding: 8px 18px; border-radius: $radius-full; font-size: 13px;
  border: 1px solid var(--border-default); background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer; font-family: inherit; font-weight: 500;
  transition: all var(--transition-fast);

  &:hover { border-color: var(--primary); color: var(--primary); }
  &.primary {
    background: var(--primary); border-color: var(--primary); color: white;
    &:hover { background: var(--primary-hover); }
  }
  &.danger { color: var(--danger);
    &:hover { background: rgba(239, 68, 68, 0.08); border-color: var(--danger); }
  }
}

.image-viewer-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.8); z-index: 9999;
  display: flex; align-items: center; justify-content: center;
  animation: fadeIn 0.3s;
}
.viewer-img { max-width: 92vw; max-height: 90vh; object-fit: contain; border-radius: var(--radius-md); }
.viewer-close {
  position: absolute; top: 20px; right: 20px;
  width: 44px; height: 44px; border: none; border-radius: 50%;
  background: rgba(255,255,255,0.15); color: white;
  font-size: 22px; cursor: pointer; transition: background var(--transition-fast);
  &:hover { background: rgba(255,255,255,0.25); }
}
</style>
