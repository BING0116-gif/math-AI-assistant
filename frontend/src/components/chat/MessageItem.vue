<template>
  <div class="message-item" :class="[`msg-${message.sender}`, { streaming: isStreaming }]" :id="`msg-${message.id}`">
    <div class="msg-avatar" v-if="message.sender === 'ai'">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="20" height="20">
        <path d="M12 2a4 4 0 014 4v1a4 4 0 01-4 4 4 4 0 01-4-4V6a4 4 0 014-4z"/>
        <path d="M9 20h6a4 4 0 014 4H5a4 4 0 014-4z"/>
        <circle cx="12" cy="10" r="3"/>
      </svg>
    </div>
    <div class="msg-body">
      <div v-if="message.type === 'image'" class="msg-image-wrap">
        <img :src="message.content" class="msg-image" alt="图片消息" />
      </div>
      <div v-else class="msg-content" v-html="renderedContent"></div>

      <div v-if="message.sender === 'ai' && !isStreaming" class="error-book-actions">
        <template v-if="message.errorBookStatus === 'added'">
          <button class="eb-btn added" disabled>✓ 已加入错题本</button>
        </template>
        <template v-else-if="message.errorBookStatus === 'skipped'">
          <button class="eb-btn skipped" disabled>⏭️ 已跳过</button>
        </template>
        <template v-else>
          <button class="eb-btn add" @click.stop="$emit('addToErrorBook', message.id)">
            📚 加入错题本
          </button>
          <button class="eb-btn skip" @click.stop="$emit('skipErrorBook', message.id)">
            不加入
          </button>
        </template>
      </div>

      <div class="msg-time">{{ message.timestamp }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, watch, nextTick } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { renderMathInElement } from '@/utils/mathRender'

const props = defineProps({
  message: { type: Object, required: true },
  isStreaming: { type: Boolean, default: false }
})

defineEmits(['addToErrorBook', 'skipErrorBook'])

const renderedContent = computed(() => {
  if (props.message.sender === 'ai') {
    return renderMarkdown(props.message.content || '')
  }
  return props.message.content || ''
})

onMounted(() => {
  if (props.message.sender === 'ai') {
    nextTick(() => {
      const el = document.getElementById(`msg-${props.message.id}`)
      if (el) renderMathInElement(el)
    })
  }
})

watch(() => [props.isStreaming, props.message.content], () => {
  if (props.message.sender === 'ai' && !props.isStreaming) {
    nextTick(() => {
      const el = document.getElementById(`msg-${props.message.id}`)
      if (el) renderMathInElement(el)
    })
  }
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.message-item {
  display: flex;
  gap: 14px;
  max-width: 88%;

  &.msg-user {
    align-self: flex-end;
    flex-direction: row-reverse;
    max-width: 72%;

    .msg-body {
      background: linear-gradient(135deg, $primary 0%, $primary-dark 100%);
      color: white;
      border-radius: $radius-xl $radius-xl 4px $radius-xl;
      padding: 14px 20px;
      box-shadow: 0 4px 14px rgba($primary, 0.25);
    }
    .msg-content { color: white; }
    .msg-time { color: rgba(255,255,255,0.7); }
  }

  &.msg-ai {
    align-self: flex-start;
    .msg-body {
      background: white;
      border-radius: 4px $radius-xl $radius-xl $radius-xl;
      padding: 16px 22px;
      box-shadow: $shadow-sm;
      border: 1px solid $border-light;
    }
  }
}

.msg-avatar {
  width: 38px; height: 38px;
  background: $primary-bg;
  border-radius: $radius-md;
  display: flex;
  align-items: center;
  justify-content: center;
  color: $primary;
  flex-shrink: 0;
}

.msg-body {
  flex: 1;
  min-width: 0;
  position: relative;
}

.msg-content {
  font-size: 15px;
  line-height: 1.8;
  word-break: break-word;

  :deep(p) { margin: 10px 0; }
  :deep(h1) { font-size: 21px; font-weight: 700; margin: 18px 0 12px; border-bottom: 2px solid $primary-light; padding-bottom: 8px; }
  :deep(h2) { font-size: 18px; font-weight: 600; margin: 16px 0 10px; }
  :deep(h3) { font-size: 16px; font-weight: 600; margin: 14px 0 8px; }
  :deep(strong) { font-weight: 700; }
  :deep(code) {
    background: $bg-tertiary; padding: 2px 7px; border-radius: 4px;
    font-family: $font-mono; font-size: 13px; color: #e53e3e;
  }
  :deep(pre) {
    background: #1e293b; color: #e2e8f0; padding: 16px 20px;
    border-radius: $radius-md; overflow-x: auto; margin: 14px 0;
    code { background: none; color: inherit; padding: 0; }
  }
  :deep(blockquote) {
    margin: 14px 0; padding: 12px 18px;
    border-left: 4px solid $primary;
    background: $primary-bg; border-radius: 0 $radius-sm $radius-sm 0;
  }
  :deep(hr) { margin: 20px 0; border: none; height: 1px; background: linear-gradient(to right, transparent, $border-color, transparent); }
  :deep(.katex) { font-size: 1.12em !important; }
  :deep(.katex-display) {
    margin: 18px 0 !important; padding: 16px 20px !important;
    background: #f8fafc !important; border-radius: $radius-md !important;
    overflow-x: auto !important;
  }
  :deep(.math-display) {
    display: block;
    margin: 18px 0;
    padding: 16px 20px;
    background: #f8fafc;
    border-radius: $radius-md;
    overflow-x: auto;
    text-align: center;
  }
  :deep(.math-inline) {
    display: inline;
  }
  :deep(.math-error) {
    color: #cc0000;
    font-style: italic;
    background: #fef2f2;
    padding: 2px 6px;
    border-radius: 4px;
  }
}

.msg-image-wrap { margin: 0; }
.msg-image { max-width: 260px; border-radius: $radius-md; display: block; }

.msg-time {
  font-size: 11px;
  color: $text-tertiary;
  margin-top: 8px;
  text-align: right;
}

.msg-ai .msg-time { text-align: left; }

.error-book-actions {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid $border-light;
  display: flex;
  gap: 10px;
}

.eb-btn {
  padding: 6px 16px;
  border-radius: $radius-full;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: none;
  font-family: inherit;
  transition: all 0.25s ease;
  display: inline-flex;
  align-items: center;
  gap: 4px;

  &.add {
    background: linear-gradient(135deg, $primary 0%, $primary-light 100%);
    color: white;
    box-shadow: 0 2px 8px rgba($primary, 0.3);
    &:hover { transform: translateY(-1px); box-shadow: 0 4px 14px rgba($primary, 0.4); }
    &:active { transform: scale(0.96); }
  }
  &.skip {
    background: $bg-tertiary; color: $text-secondary;
    &:hover { background: #e2e8f0; }
  }
  &.added {
    background: $success-light; color: $success; cursor: default;
  }
  &.skipped {
    background: #f8fafc; color: $text-tertiary; cursor: default; text-decoration: line-through;
  }
}
</style>
