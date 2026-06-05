<template>
  <div class="detail-overlay" @click.self="$emit('close')">
    <div class="detail-container">
      <div class="detail-header">
        <h2>📋 错题详情</h2>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </div>

      <div class="detail-nav">
        <button class="nav-btn" :disabled="currentIndex <= 0" @click="$emit('prev')">◀ 上一题</button>
        <span class="nav-counter">{{ currentIndex + 1 }} / {{ total }}</span>
        <button class="nav-btn" :disabled="currentIndex >= total - 1" @click="$emit('next')">下一题 ▶</button>
      </div>

      <div class="detail-body">
        <section class="d-section">
          <h3>📝 题目</h3>
          <div class="d-content">
            <template v-if="isImage">
              <img :src="error.question" class="d-image" @click="viewerOpen = true" />
              <p v-if="error.recognized_text" class="recognized"><strong>识别文本：</strong>{{ error.recognized_text }}</p>
            </template>
            <p v-else class="d-text">{{ displayQuestion }}</p>
          </div>
        </section>

        <section v-if="error.error_reason" class="d-section">
          <h3>❌ 错误原因</h3>
          <div class="d-content reason-box">
            <p>{{ error.error_reason }}</p>
          </div>
        </section>

        <section class="d-section">
          <h3>✅ 正确解答</h3>
          <div class="d-content answer-box math-area" ref="answerBox" v-html="answerHtml"></div>
        </section>

        <section v-if="error.notes" class="d-section">
          <h3>📝 学习笔记</h3>
          <div class="d-content notes-box"><p>{{ error.notes }}</p></div>
        </section>

        <section v-if="error.categories?.length" class="d-section">
          <h3>🏷️ 分类标签</h3>
          <div class="tag-row">
            <span v-for="cat in error.categories" :key="cat" class="tag">{{ cat }}</span>
          </div>
        </section>

        <section class="d-section">
          <h3>📊 元信息</h3>
          <div class="meta-grid">
            <div class="meta-cell"><strong>添加时间：</strong>{{ error.added_at || '-' }}</div>
            <div class="meta-cell">
              <strong>掌握度：</strong>
              <span class="stars">{{ '★'.repeat(error.mastery_level || 3) }}{{ '☆'.repeat(5 - (error.mastery_level || 3)) }}</span>
              ({{ error.mastery_level || 3 }}/5)
            </div>
            <div class="meta-cell" :class="{ mastered: error.is_mastered }">
              <strong>状态：</strong>{{ error.is_mastered ? '✅ 已掌握' : '⏳ 待复习' }}
            </div>
          </div>
        </section>
      </div>

      <div class="detail-footer">
        <button class="ft-btn primary" @click="$emit('toggleMastery')">✓ {{ error.is_mastered ? '取消掌握' : '标记为已掌握' }}</button>
        <button class="ft-btn danger" @click="$emit('delete')">🗑️ 删除此错题</button>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="viewerOpen" class="img-viewer" @click="viewerOpen = false">
        <img :src="error.question" class="v-img" @click.stop />
        <button class="v-close" @click="viewerOpen = false">✕</button>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps({
  error: Object,
  currentIndex: Number,
  total: Number
})

defineEmits(['close', 'prev', 'next', 'toggleMastery', 'delete'])

const viewerOpen = ref(false)
const answerBox = ref(null)

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

onMounted(() => {
  // 公式已由 markdown.js 中的 @mdit/plugin-katex 在渲染阶段完成
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.detail-overlay {
  position: fixed; inset: 0; background: var(--bg-overlay); z-index: 9999;
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px); animation: fadeIn 0.3s;
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.detail-container {
  background: var(--bg-card);
  border-radius: var(--radius-xl);
  width: min(92vw, 880px);
  height: min(90vh, 750px);
  display: flex; flex-direction: column;
  box-shadow: var(--shadow-lg);
  animation: modalIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
}

@keyframes modalIn {
  from { opacity: 0; transform: scale(0.95) translateY(24px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.detail-header {
  padding: 18px 24px; border-bottom: 1px solid var(--border-light);
  display: flex; justify-content: space-between; align-items: center;
  background: var(--bg-card); border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  h2 { font-size: 18px; color: var(--primary); display: flex; align-items: center; gap: 8px; }
}

.close-btn {
  background: none; border: none; font-size: 22px; color: var(--text-tertiary);
  cursor: pointer; padding: 4px 10px; border-radius: var(--radius-sm);
  &:hover { background: var(--primary-ghost); color: var(--text-primary); }
}

.detail-nav {
  padding: 10px 24px; display: flex; justify-content: space-between; align-items: center;
  background: var(--bg-card); border-bottom: 1px solid var(--border-light);
}

.nav-btn {
  padding: 8px 18px; border: 1px solid var(--border-default); border-radius: $radius-full;
  background: var(--bg-card); font-size: 13px; cursor: pointer; color: var(--text-secondary);
  font-family: inherit; display: flex; align-items: center; gap: 6px; transition: all var(--transition-fast);
  &:hover:not(:disabled) { border-color: var(--primary); color: var(--primary); }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
}

.nav-counter { font-size: 14px; font-weight: 600; color: var(--text-secondary); }

.detail-body {
  flex: 1; overflow-y: auto; padding: 20px 24px;
}

.d-section { margin-bottom: 20px;
  h3 { font-size: 15px; font-weight: 700; margin-bottom: 10px; color: var(--text-primary); display: flex; align-items: center; gap: 6px; }
}

.d-content {
  padding: 14px 18px; background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-md); line-height: 1.8;
}

.d-text { font-size: 14px; color: var(--text-primary); }
.d-image {
  max-width: 100%; max-height: 300px; border-radius: var(--radius-sm);
  cursor: zoom-in; border: 1px solid var(--border-default);
}

.recognized { margin-top: 10px; font-size: 13px; color: var(--text-tertiary); font-style: italic; }

.reason-box { background: rgba(239, 68, 68, 0.08); border-color: rgba(239, 68, 68, 0.15); }
.answer-box { background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.15); }
.notes-box { background: rgba(245, 158, 11, 0.08); border-color: rgba(245, 158, 11, 0.15); }

.math-area :deep(.katex) { font-size: 1.05em !important; }
.math-area :deep(.katex-display) { margin: 12px 0 !important; }

.tag-row { display: flex; gap: 8px; flex-wrap: wrap; }
.tag {
  padding: 4px 14px; background: var(--primary-ghost);
  border-radius: $radius-full; font-size: 12px; color: var(--primary); font-weight: 500;
}

.meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.meta-cell {
  padding: 12px 16px; background: var(--bg-card); border: 1px solid var(--border-light);
  border-radius: var(--radius-md); font-size: 13px; color: var(--text-secondary);
  &.mastered { background: rgba(16, 185, 129, 0.08); border-color: rgba(16, 185, 129, 0.15); }
}
.stars { color: var(--accent); letter-spacing: 1px; }

.detail-footer {
  padding: 14px 24px; border-top: 1px solid var(--border-light);
  display: flex; justify-content: flex-end; gap: 12px;
  background: var(--bg-card); border-radius: 0 0 var(--radius-xl) var(--radius-xl);
}

.ft-btn {
  padding: 9px 22px; border-radius: $radius-full; font-size: 13px;
  border: 1px solid var(--border-default); background: var(--bg-card); cursor: pointer;
  font-family: inherit; font-weight: 500; transition: all var(--transition-fast);
  color: var(--text-secondary);
  &.primary {
    background: var(--primary); border-color: var(--primary); color: white;
    &:hover { background: var(--primary-hover); }
  }
  &.danger { color: var(--danger);
    &:hover { background: rgba(239, 68, 68, 0.08); border-color: var(--danger); }
  }
}

.img-viewer {
  position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 99999;
  display: flex; align-items: center; justify-content: center;
}
.v-img { max-width: 95vw; max-height: 95vh; object-fit: contain; border-radius: var(--radius-md); }
.v-close {
  position: absolute; top: 20px; right: 20px;
  width: 44px; height: 44px; border: none; border-radius: 50%;
  background: rgba(255,255,255,0.12); color: white;
  font-size: 24px; cursor: pointer;
  &:hover { background: rgba(255,255,255,0.22); }
}
</style>