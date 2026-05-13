<template>
  <div class="input-area-wrap">
    <div v-if="imagePreview" class="image-preview-bar">
      <div class="preview-thumb">
        <img :src="imagePreview" alt="预览" />
        <button class="remove-btn" @click="removeImage">×</button>
      </div>
      <span class="hint-text">解释图片 →</span>
    </div>
    <div class="input-row">
      <textarea
        ref="inputRef"
        class="chat-input"
        :value="inputText"
        @input="handleInput"
        @keydown="handleKeydown"
        @paste="handlePaste"
        placeholder="输入你的数学问题..."
        :disabled="disabled"
        rows="1"
      ></textarea>
      <button class="send-btn" :class="{ active: hasContent, glow: hasContent }" @click="send" :disabled="disabled || !hasContent">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ disabled: Boolean })
const emit = defineEmits(['send'])

const inputRef = ref(null)
const inputText = ref('')
const imagePreview = ref(null)
let pendingImageData = null

const hasContent = computed(() => inputText.value.trim().length > 0 || pendingImageData)

function handleInput(e) {
  inputText.value = e.target.value
  e.target.style.height = 'auto'
  e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function handlePaste(e) {
  const items = e.clipboardData?.items
  if (!items) return
  for (let i = 0; i < items.length; i++) {
    if (items[i].type.startsWith('image/')) {
      e.preventDefault()
      const file = items[i].getAsFile()
      const reader = new FileReader()
      reader.onload = (evt) => {
        pendingImageData = evt.target.result
        imagePreview.value = evt.target.result
      }
      reader.readAsDataURL(file)
      break
    }
  }
}

function removeImage() {
  pendingImageData = null
  imagePreview.value = null
}

function send() {
  if (!hasContent.value || props.disabled) return

  if (pendingImageData) {
    emit('send', {
      text: inputText.value.trim(),
      image: pendingImageData
    })
    removeImage()
    inputText.value = ''
    if (inputRef.value) inputRef.value.style.height = 'auto'
  } else if (inputText.value.trim()) {
    emit('send', { text: inputText.value.trim(), image: null })
    inputText.value = ''
    if (inputRef.value) inputRef.value.style.height = 'auto'
  }
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.input-area-wrap {
  padding: 18px 24px 22px;
  background: var(--bg-card);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-top: 1px solid var(--border-light);
  flex-shrink: 0;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 50%;
    transform: translateX(-50%);
    width: 60%;
    height: 1px;
    background: linear-gradient(90deg, transparent 0%, rgba(99, 102, 241, 0.3) 50%, transparent 100%);
  }
}

.image-preview-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 12px;
  animation: slideInUp 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes slideInUp { 
  from { 
    opacity: 0; 
    transform: translateY(10px); 
  } 
  to { 
    opacity: 1; 
    transform: translateY(0); 
  } 
}

.preview-thumb {
  position: relative;
  border-radius: $radius-lg;
  overflow: hidden;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.15), 0 2px 8px rgba(0, 0, 0, 0.06);
  border: 2px solid rgba(99, 102, 241, 0.15);
  transition: all 0.3s ease;

  &:hover {
    transform: scale(1.03);
    box-shadow: 0 8px 24px rgba(99, 102, 241, 0.25), 0 4px 12px rgba(0, 0, 0, 0.08);
    border-color: rgba(99, 102, 241, 0.3);
  }

  img { 
    max-width: 110px; 
    max-height: 110px; 
    display: block; 
    object-fit: cover;
  }
}

.remove-btn {
  position: absolute; 
  top: 6px; 
  right: 6px;
  width: 24px; height: 24px;
  border-radius: 50%;
  border: none;
  background: rgba(239, 68, 68, 0.9);
  backdrop-filter: blur(8px);
  color: white;
  cursor: pointer;
  font-size: 15px;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover { 
    background: #dc2626; 
    transform: scale(1.15) rotate(90deg);
    box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
  }

  &:active {
    transform: scale(0.95);
  }
}

.hint-text { 
  font-size: 13px; 
  color: var(--primary); 
  font-weight: 600;
  letter-spacing: 0.02em;
}

.input-row {
  display: flex;
  gap: 12px;
  align-items: flex-end;
  background: var(--bg-card);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  padding: 14px 18px;
  border-radius: $radius-xl;
  border: 2px solid var(--border-light);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: var(--shadow-md);

  &:hover,
  &:focus-within {
    border-color: rgba(99, 102, 241, 0.3);
    box-shadow: 0 8px 30px rgba(99, 102, 241, 0.08), 0 4px 12px rgba(0, 0, 0, 0.04);
  }

  &:focus-within {
    border-color: var(--primary-hover);
    box-shadow: 0 8px 30px rgba(99, 102, 241, 0.12), 0 0 0 4px rgba(99, 102, 241, 0.06);
  }
}

.chat-input {
  flex: 1;
  min-height: 44px;
  max-height: 120px;
  padding: 10px 0;
  border: none;
  border-radius: $radius-lg;
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
    font-style: italic;
  }

  &:focus {
    background: transparent;
  }

  &:disabled { 
    opacity: 0.55; 
    cursor: not-allowed; 
  }
}

.send-btn {
  width: 48px; height: 48px;
  border-radius: $radius-lg;
  border: 2px solid var(--border-light);
  background: linear-gradient(135deg, rgba(241, 245, 249, 0.9) 0%, rgba(248, 250, 252, 0.95) 100%);
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
      filter: drop-shadow(0 2px 4px rgba(0, 0, 0, 0.1));
    }
  }

  &.glow {
    animation: btn-glow 2s ease-in-out infinite;
  }

  @keyframes btn-glow {
    0%, 100% { 
      box-shadow: 0 4px 16px rgba(99, 102, 241, 0.2);
    }
    50% { 
      box-shadow: 0 6px 28px rgba(99, 102, 241, 0.4), 0 0 40px rgba(99, 102, 241, 0.15);
    }
  }

  &:hover:not(:disabled).active {
    transform: scale(1.08) translateY(-2px);
    box-shadow: 0 8px 32px rgba(99, 102, 241, 0.45), 0 0 60px rgba(99, 102, 241, 0.2);
  }

  &:active:not(:disabled) {
    transform: scale(0.94);
  }

  &:disabled { 
    opacity: 0.4; 
    cursor: not-allowed;
    
    &:hover:not(.active) {
      transform: none;
      box-shadow: none;
    }
  }
}

@media (max-width: 768px) {
  .input-area-wrap {
    padding: 14px 16px 18px;
  }

  .input-row {
    padding: 12px 14px;
  }

  .send-btn {
    width: 44px;
    height: 44px;
  }

  .preview-thumb img {
    max-width: 90px;
    max-height: 90px;
  }
}
</style>