<template>
  <div class="chat-input-container">
    <div class="input-wrapper">
      <textarea
        ref="inputRef"
        class="chat-textarea"
        :value="modelValue"
        @input="handleInput"
        @keydown="handleKeydown"
        :placeholder="placeholder"
        :disabled="disabled"
        rows="1"
        aria-label="输入你的数学问题"
      ></textarea>
      <div class="input-actions">
        <button
          class="voice-btn"
          @click="$emit('voiceInput')"
          title="语音输入"
          aria-label="语音输入"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"/>
            <path d="M19 10v2a7 7 0 01-14 0v-2"/>
            <line x1="12" y1="19" x2="12" y2="23"/>
            <line x1="8" y1="23" x2="16" y2="23"/>
          </svg>
        </button>
        <button
          class="send-btn"
          :class="{ active: hasContent }"
          @click="handleSend"
          :disabled="disabled || !hasContent"
          title="发送"
          aria-label="发送消息"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
    </div>
    <QuickTools @tool-click="handleToolClick" />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import QuickTools from './QuickTools.vue'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: '输入你的数学问题...'
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'send', 'voiceInput', 'toolClick'])

const inputRef = ref(null)

const hasContent = computed(() => props.modelValue.trim().length > 0)

function handleInput(e) {
  emit('update:modelValue', e.target.value)
  e.target.style.height = 'auto'
  e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    handleSend()
  }
}

function handleSend() {
  if (!hasContent.value || props.disabled) return
  emit('send', { text: props.modelValue.trim() })
}

function handleToolClick(tool) {
  emit('toolClick', tool)
}

function focus() {
  inputRef.value?.focus()
}

defineExpose({ focus })
</script>

<style lang="scss" scoped>
.chat-input-container {
  max-width: 720px;
  margin: 0 auto;
  padding: 0 24px 30px;
  width: 100%;
}

.input-wrapper {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  background: var(--bg-card);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  padding: 14px 18px;
  border-radius: var(--radius-xl);
  border: 2px solid var(--border-light);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--shadow-sm);
  margin-bottom: 16px;

  &:hover,
  &:focus-within {
    border-color: var(--primary);
    box-shadow: var(--shadow-glow);
  }

  &:focus-within {
    box-shadow: var(--shadow-glow), 0 0 0 4px var(--primary-ghost);
  }
}

.chat-textarea {
  flex: 1;
  min-height: 44px;
  max-height: 120px;
  padding: 10px 0;
  border: none;
  border-radius: var(--radius-lg);
  resize: none;
  font-size: 15px;
  font-family: inherit;
  outline: none;
  transition: all 0.25s ease;
  background: transparent;
  color: var(--text-primary);
  line-height: 1.6;

  &::placeholder {
    color: var(--text-tertiary);
  }

  &:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
}

.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.voice-btn {
  width: 38px;
  height: 38px;
  border: 1.5px solid var(--border-light);
  border-radius: var(--radius-md);
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.3s ease;

  &:hover {
    color: var(--primary);
    border-color: var(--primary);
    background: var(--primary-ghost);
  }
}

.send-btn {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-lg);
  border: 2px solid var(--border-light);
  background: var(--bg-card);
  color: var(--text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
  position: relative;
  overflow: hidden;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
    opacity: 0;
    transition: opacity 0.35s ease;
  }

  svg {
    position: relative;
    z-index: 1;
    transition: all 0.3s ease;
  }

  &.active {
    border-color: transparent;

    &::before {
      opacity: 1;
    }

    svg {
      color: white;
    }
  }

  &:hover:not(:disabled).active {
    transform: scale(1.08) translateY(-2px);
    box-shadow: var(--shadow-glow);
  }

  &:active:not(:disabled) {
    transform: scale(0.94);
  }

  &:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
}

@media (max-width: 768px) {
  .chat-input-container {
    padding: 0 16px 24px;
  }

  .input-wrapper {
    padding: 12px 14px;
  }

  .send-btn {
    width: 44px;
    height: 44px;
  }
}
</style>