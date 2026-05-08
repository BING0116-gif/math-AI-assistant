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
      <button class="send-btn" :class="{ active: hasContent }" @click="send" :disabled="disabled || !hasContent">
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
  padding: 16px 20px 20px;
  background: rgba(255,255,255,0.8);
  backdrop-filter: blur(12px);
  border-top: 1px solid $border-light;
  flex-shrink: 0;
}

.image-preview-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  animation: fadeIn 0.3s;
}

@keyframes fadeIn { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }

.preview-thumb {
  position: relative;
  border-radius: $radius-md;
  overflow: hidden;
  box-shadow: $shadow-md;
  img { max-width: 100px; max-height: 100px; display: block; }
}

.remove-btn {
  position: absolute; top: 4px; right: 4px;
  width: 22px; height: 22px;
  border-radius: 50%;
  border: none;
  background: rgba(0,0,0,0.5);
  color: white;
  cursor: pointer;
  font-size: 14px;
  display: flex; align-items: center; justify-content: center;
  &:hover { background: rgba(0,0,0,0.7); }
}

.hint-text { font-size: 13px; color: $text-tertiary; }

.input-row {
  display: flex;
  gap: 10px;
  align-items: flex-end;
}

.chat-input {
  flex: 1;
  min-height: 42px;
  max-height: 120px;
  padding: 11px 18px;
  border: 1.5px solid $border-color;
  border-radius: $radius-xl;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color $transition-fast;
  background: $bg-tertiary;

  &:focus { border-color: $primary; box-shadow: 0 0 0 3px rgba($primary, 0.08); background: white; }
  &:disabled { opacity: 0.6; cursor: not-allowed; }
}

.send-btn {
  width: 44px; height: 44px;
  border-radius: 50%;
  border: none;
  background: $bg-tertiary;
  color: $text-tertiary;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all $transition-fast;
  flex-shrink: 0;

  &.active {
    background: linear-gradient(135deg, $primary 0%, $primary-light 100%);
    color: white;
    box-shadow: 0 4px 14px rgba($primary, 0.3);
  }
  &:hover:not(:disabled).active {
    transform: scale(1.05);
    box-shadow: 0 6px 18px rgba($primary, 0.4);
  }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}
</style>
