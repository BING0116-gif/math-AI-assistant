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
        <div v-if="message.text" class="msg-image-text">{{ message.text }}</div>
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
}, { flush: 'post' })
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.message-item {
  display: flex;
  gap: 16px;
  max-width: 88%;
  animation: messageSlideIn 0.45s cubic-bezier(0.34, 1.56, 0.64, 1);

  &.msg-user {
    align-self: flex-end;
    flex-direction: row-reverse;
    max-width: 75%;

    .msg-body {
      background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
      color: white;
      border-radius: $radius-xl $radius-xl 6px $radius-xl;
      padding: 16px 22px;
      box-shadow: 0 8px 24px rgba(99, 102, 241, 0.28), 0 2px 8px rgba(99, 102, 241, 0.15);
      
      &:hover {
        box-shadow: 0 12px 32px rgba(99, 102, 241, 0.35), 0 4px 12px rgba(99, 102, 241, 0.2);
        transform: translateY(-2px);
      }
    }
    
    .msg-content { 
      color: white; 
      text-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
    }
    
    .msg-time { 
      color: rgba(255, 255, 255, 0.75); 
    }
  }

  &.msg-ai {
    align-self: flex-start;

    .msg-body {
      background: var(--bg-card);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border-radius: 6px $radius-xl $radius-xl $radius-xl;
      padding: 18px 24px;
      box-shadow: var(--shadow-md);
      border: 1px solid var(--border-light);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

      &:hover {
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.08), 0 2px 8px rgba(0, 0, 0, 0.06);
        transform: translateY(-1px);
        border-color: var(--border-light);
      }
    }

    &.streaming {
      .msg-body {
        background: linear-gradient(135deg, rgba(238, 242, 255, 0.95) 0%, rgba(255, 255, 255, 0.98) 100%);
        border-color: rgba(99, 102, 241, 0.15);
        
        &::after {
          content: '';
          position: absolute;
          bottom: 0;
          left: 50%;
          transform: translateX(-50%);
          width: 40%;
          height: 2px;
          background: linear-gradient(90deg, transparent 0%, var(--primary) 50%, transparent 100%);
          animation: typing-indicator 1.5s ease-in-out infinite;
        }
      }
    }
  }
}

@keyframes messageSlideIn {
  0% {
    opacity: 0;
    transform: translateY(30px) scale(0.95);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes typing-indicator {
  0%, 100% {
    opacity: 0.3;
    width: 30%;
  }
  50% {
    opacity: 1;
    width: 60%;
  }
}

.msg-avatar {
  width: 40px; height: 40px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(129, 140, 248, 0.15) 100%);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary);
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.12), inset 0 1px 0 rgba(255, 255, 255, 0.8);
  transition: all 0.3s ease;

  svg {
    filter: drop-shadow(0 1px 2px rgba(99, 102, 241, 0.2));
  }
}

.msg-body {
  flex: 1;
  min-width: 0;
  position: relative;
  overflow: hidden;
}

.msg-content {
  font-size: 15px;
  line-height: 1.85;
  word-break: break-word;

  :deep(p) { margin: 11px 0; }
  :deep(h1) { 
    font-size: 22px; 
    font-weight: 700; 
    margin: 20px 0 14px; 
    border-bottom: 2.5px solid linear-gradient(90deg, var(--primary) 0%, var(--primary-hover) 100%);
    padding-bottom: 10px; 
    background: linear-gradient(135deg, var(--text-primary) 0%, var(--primary) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  :deep(h2) { 
    font-size: 19px; 
    font-weight: 600; 
    margin: 18px 0 12px; 
    color: var(--primary-dark);
  }
  :deep(h3) { 
    font-size: 17px; 
    font-weight: 600; 
    margin: 15px 0 10px; 
  }
  :deep(strong) { 
    font-weight: 700; 
    color: var(--text-primary);
  }
  :deep(code) {
    background: linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(254, 202, 202, 0.12) 100%);
    padding: 3px 8px; 
    border-radius: 6px;
    font-family: $font-mono; 
    font-size: 13px; 
    color: #dc2626;
    border: 1px solid rgba(239, 68, 68, 0.15);
  }
  :deep(pre) {
    background: linear-gradient(135deg, #1e293b 0%, #334155 100%); 
    color: #e2e8f0; 
    padding: 18px 22px;
    border-radius: var(--radius-lg); 
    overflow-x: auto; 
    margin: 16px 0;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15), inset 0 1px 0 rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(51, 65, 85, 0.5);
    
    code { 
      background: none; 
      color: inherit; 
      padding: 0; 
      border: none;
    }
  }
  :deep(blockquote) {
    margin: 16px 0; 
    padding: 14px 20px;
    border-left: 4px solid var(--primary); 
    background: linear-gradient(90deg, rgba(99, 102, 241, 0.04) 0%, rgba(129, 140, 248, 0.02) 100%);
    border-radius: 0 $radius-md $radius-md 0;
    font-style: italic;
    color: var(--text-secondary);
  }
  :deep(hr) { 
    margin: 22px 0; 
    border: none; 
    height: 1.5px; 
    background: linear-gradient(90deg, transparent 0%, rgba(226, 232, 240, 0.8) 50%, transparent 100%); 
  }
  :deep(.katex) { 
    font-size: 1.13em !important; 
  }
  :deep(.katex-display) {
    margin: 20px 0 !important; 
    padding: 18px 24px !important;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%) !important;
    border-radius: var(--radius-lg) !important;
    overflow-x: auto !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
    border: 1px solid var(--border-light);
  }
  :deep(.math-display) {
    display: block;
    margin: 20px 0;
    padding: 18px 24px;
    background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
    border-radius: var(--radius-lg);
    overflow-x: auto;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }
  :deep(.math-inline) {
    display: inline;
  }
  :deep(.math-error) {
    color: #dc2626;
    font-style: italic;
    background: linear-gradient(135deg, rgba(254, 202, 202, 0.3) 0%, rgba(254, 226, 226, 0.4) 100%);
    padding: 3px 7px;
    border-radius: 5px;
    border: 1px solid rgba(239, 68, 68, 0.2);
  }
}

.msg-image-wrap { 
  margin: 0; 
}

.msg-image { 
  max-width: 280px; 
  border-radius: var(--radius-lg); 
  display: block; 
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1), 0 2px 6px rgba(0, 0, 0, 0.06);
  border: 2px solid rgba(255, 255, 255, 0.8);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    transform: scale(1.03);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15), 0 4px 12px rgba(0, 0, 0, 0.08);
  }
}

.msg-image-text {
  margin-top: 12px;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.25);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border-radius: $radius-md;
  font-size: 14px;
  line-height: 1.65;
  word-break: break-word;
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: rgba(255, 255, 255, 0.95);
}

.msg-time {
  font-size: 11.5px;
  color: var(--text-tertiary);
  margin-top: 10px;
  text-align: right;
  font-weight: 500;
  letter-spacing: 0.02em;
  opacity: 0.85;
}

.msg-ai .msg-time { 
  text-align: left; 
  color: var(--text-tertiary);
}

.error-book-actions {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1.5px solid var(--border-light);
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.eb-btn {
  padding: 8px 18px;
  border-radius: $radius-full;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 1.5px solid var(--border-light);
  font-family: inherit;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: inline-flex;
  align-items: center;
  gap: 5px;

  &.add {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(129, 140, 248, 0.12) 100%);
    color: var(--primary);
    border-color: rgba(99, 102, 241, 0.25);
    box-shadow: 0 2px 8px rgba(99, 102, 241, 0.08);

    &:hover { 
      background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
      color: white;
      transform: translateY(-2px); 
      box-shadow: 0 6px 20px rgba(99, 102, 241, 0.25);
      border-color: transparent;
    }
    
    &:active {
      transform: translateY(0);
    }
  }
  
  &.skip {
    background: rgba(241, 245, 249, 0.9); 
    color: var(--text-secondary);
    
    &:hover { 
      background: rgba(226, 232, 240, 0.9);
      transform: translateY(-1px);
    }
  }
  
  &.added {
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(209, 250, 229, 0.15) 100%);
    color: #059669;
    cursor: default;
    border-color: rgba(16, 185, 129, 0.25);
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.1);
  }
  
  &.skipped {
    background: rgba(241, 245, 249, 0.6); 
    color: var(--text-tertiary);
    cursor: default; 
    text-decoration: line-through;
    opacity: 0.7;
  }

  &:disabled {
    pointer-events: none;
  }
}

@media (max-width: 768px) {
  .message-item {
    max-width: 92%;
    
    &.msg-user {
      max-width: 85%;
    }
  }

  .msg-body {
    padding: 14px 18px;
  }

  .msg-avatar {
    width: 36px;
    height: 36px;
  }

  .msg-image {
    max-width: 220px;
  }
}
</style>