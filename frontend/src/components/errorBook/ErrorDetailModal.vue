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
import { renderMathInElement } from '@/utils/mathRender'
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
  nextTick(() => {
    if (answerBox.value) renderMathInElement(answerBox.value)
  })
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.detail-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.55); z-index: 9999;
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(3px); animation: fadeIn 0.3s;
}

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

.detail-container {
  background: white; border-radius: $radius-xl; width: min(92vw, 880px);
  height: min(90vh, 750px); display: flex; flex-direction: column;
  box-shadow: 0 20px 60px rgba(0,0,0,0.25);
  animation: modalIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes modalIn {
  from { opacity: 0; transform: scale(0.95) translateY(24px); }
  to { opacity: 1; transform: scale(1) translateY(0); }
}

.detail-header {
  padding: 18px 24px; border-bottom: 1px solid $border-color;
  display: flex; justify-content: space-between; align-items: center;
  background: $bg-primary; border-radius: $radius-xl $radius-xl 0 0;
  h2 { font-size: 18px; color: $primary; display: flex; align-items: center; gap: 8px; }
}

.close-btn {
  background: none; border: none; font-size: 22px; color: $text-tertiary;
  cursor: pointer; padding: 4px 10px; border-radius: $radius-sm;
  &:hover { background: $bg-tertiary; color: $text-primary; }
}

.detail-nav {
  padding: 10px 24px; display: flex; justify-content: space-between; align-items: center;
  background: white; border-bottom: 1px solid $border-light;
}

.nav-btn {
  padding: 8px 18px; border: 1px solid $border-color; border-radius: $radius-full;
  background: white; font-size: 13px; cursor: pointer; color: $text-secondary;
  font-family: inherit; display: flex; align-items: center; gap: 6px; transition: all $transition-fast;
  &:hover:not(:disabled) { border-color: $primary; color: $primary; }
  &:disabled { opacity: 0.4; cursor: not-allowed; }
}

.nav-counter { font-size: 14px; font-weight: 600; color: $text-secondary; }

.detail-body {
  flex: 1; overflow-y: auto; padding: 20px 24px;
}

.d-section { margin-bottom: 20px;
  h3 { font-size: 15px; font-weight: 700; margin-bottom: 10px; color: $text-primary; display: flex; align-items: center; gap: 6px; }
}

.d-content {
  padding: 14px 18px; background: $bg-tertiary; border: 1px solid $border-light;
  border-radius: $radius-md; line-height: 1.8;
}

.d-text { font-size: 14px; }
.d-image {
  max-width: 100%; max-height: 300px; border-radius: $radius-sm;
  cursor: zoom-in; border: 1px solid $border-color;
}

.recognized { margin-top: 10px; font-size: 13px; color: $text-tertiary; font-style: italic; }

.reason-box { background: $danger-light; border-color: #fecaca; }
.answer-box { background: $success-light; border-color: #a7f3d0; }
.notes-box { background: $warning-light; border-color: #fde68a; }

.math-area :deep(.katex) { font-size: 1.05em !important; }
.math-area :deep(.katex-display) { margin: 12px 0 !important; }

.tag-row { display: flex; gap: 8px; flex-wrap: wrap; }
.tag { padding: 4px 14px; background: $primary-bg; border-radius: $radius-full; font-size: 12px; color: $primary; font-weight: 500; }

.meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
.meta-cell {
  padding: 12px 16px; background: $bg-tertiary; border-radius: $radius-md; font-size: 13px;
  &.mastered { background: $success-light; }
}
.stars { color: $accent; letter-spacing: 1px; }

.detail-footer {
  padding: 14px 24px; border-top: 1px solid $border-color;
  display: flex; justify-content: flex-end; gap: 12px;
  background: $bg-primary; border-radius: 0 0 $radius-xl $radius-xl;
}

.ft-btn {
  padding: 9px 22px; border-radius: $radius-full; font-size: 13px;
  border: 1px solid $border-color; background: white; cursor: pointer;
  font-family: inherit; font-weight: 500; transition: all $transition-fast;
  &.primary { background: $primary; border-color: $primary; color: white;
    &:hover { background: $primary-dark; }
  }
  &.danger { color: $danger;
    &:hover { background: $danger-light; border-color: $danger; }
  }
}

.img-viewer {
  position: fixed; inset: 0; background: rgba(0,0,0,0.85); z-index: 99999;
  display: flex; align-items: center; justify-content: center;
}
.v-img { max-width: 95vw; max-height: 95vh; object-fit: contain; border-radius: $radius-md; }
.v-close {
  position: absolute; top: 20px; right: 20px;
  width: 44px; height: 44px; border: none; border-radius: 50%;
  background: rgba(255,255,255,0.12); color: white;
  font-size: 24px; cursor: pointer;
  &:hover { background: rgba(255,255,255,0.22); }
}
</style>
