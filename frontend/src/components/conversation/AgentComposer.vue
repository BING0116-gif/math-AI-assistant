<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, computed } from 'vue'

const props = withDefaults(defineProps<{
  large?: boolean
  disabled?: boolean
  disabledReason?: string
}>(), {
  large: false,
  disabled: false,
  disabledReason: '',
})

const emit = defineEmits<{
  send: [text: string]
  sendImage: [text: string, imageData: string]
}>()

const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const imagePreview = ref<string | null>(null)
const isComposing = ref(false)

const placeholder = computed(() => {
  if (imagePreview.value) return '添加文字说明...'
  return '输入问题，或粘贴一道题目……'
})

function autoResize() {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    const lineHeight = props.large ? 28 : 26
    const maxRows = 6
    const maxHeight = lineHeight * maxRows
    const minHeight = props.large ? 52 : 30
    const scrollHeight = textareaRef.value.scrollHeight
    textareaRef.value.style.height = Math.max(minHeight, Math.min(scrollHeight, maxHeight)) + 'px'
  }
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !isComposing.value) {
    e.preventDefault()
    handleSend()
  }
}

function handleSend() {
  if (props.disabled) return
  const trimmed = text.value.trim()
  if (imagePreview.value) {
    emit('sendImage', trimmed, imagePreview.value)
    text.value = ''
    imagePreview.value = null
    nextTick(autoResize)
    return
  }
  if (trimmed) {
    emit('send', trimmed)
    text.value = ''
    autoResize()
  }
}

function handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of Array.from(items)) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      const file = item.getAsFile()
      if (file) {
        const reader = new FileReader()
        reader.onload = () => {
          imagePreview.value = reader.result as string
          nextTick(autoResize)
        }
        reader.readAsDataURL(file)
      }
      break
    }
  }
}

function handleDrop(e: DragEvent) {
  const files = e.dataTransfer?.files
  if (!files || files.length === 0) return
  const file = files[0]
  if (file.type.startsWith('image/')) {
    e.preventDefault()
    const reader = new FileReader()
    reader.onload = () => {
      imagePreview.value = reader.result as string
      nextTick(autoResize)
    }
    reader.readAsDataURL(file)
  }
}

function handleFileSelect() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/jpeg,image/png,image/webp'
  input.onchange = () => {
    const file = input.files?.[0]
    if (file) {
      const reader = new FileReader()
      reader.onload = () => {
        imagePreview.value = reader.result as string
        nextTick(autoResize)
      }
      reader.readAsDataURL(file)
    }
  }
  input.click()
}

function removeImage() {
  imagePreview.value = null
  nextTick(autoResize)
}

onMounted(() => {
  autoResize()
})

onUnmounted(() => {
  if (imagePreview.value) {
    URL.revokeObjectURL(imagePreview.value)
  }
})
</script>

<template>
  <div
    class="agent-composer"
    :class="{ 'agent-composer--large': large, 'agent-composer--disabled': disabled }"
  >
    <!-- AI 不可用提示 -->
    <div v-if="disabled" class="agent-composer__offline-banner">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" class="agent-composer__offline-icon">
        <circle cx="12" cy="12" r="10"/>
        <path d="M12 8v4M12 16h.01"/>
      </svg>
      <span>{{ disabledReason || 'AI 功能当前不可用，请稍后再试' }}</span>
    </div>

    <div
      class="agent-composer__box"
      :class="{
        'agent-composer__box--with-image': imagePreview,
        'agent-composer__box--disabled': disabled
      }"
      @drop.prevent="disabled ? null : handleDrop"
      @dragover.prevent
    >
      <!-- 图片预览 -->
      <div v-if="imagePreview" class="agent-composer__preview">
        <img :src="imagePreview" alt="上传的图片" class="agent-composer__preview-img" />
        <button
          class="agent-composer__preview-remove"
          aria-label="移除图片"
          @click="removeImage"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>

      <!-- 输入区 -->
      <div class="agent-composer__input-row">
        <textarea
          ref="textareaRef"
          v-model="text"
          class="agent-composer__textarea"
          :placeholder="placeholder"
          :rows="1"
          :disabled="disabled"
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          @keydown="disabled ? null : handleKeydown"
          @input="autoResize"
          @paste="disabled ? null : handlePaste"
          aria-label="输入数学问题"
        />
      </div>

      <!-- 工具栏 -->
      <div class="agent-composer__tools">
        <div class="agent-composer__tools-left">
          <button
            class="agent-composer__tool-btn agent-composer__tool-btn--icon"
            aria-label="添加图片"
            title="添加图片"
            :disabled="disabled"
            @click="disabled ? null : handleFileSelect"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 5v14M5 12h14"/>
            </svg>
          </button>
          <button
            class="agent-composer__tool-btn agent-composer__tool-btn--text"
            aria-label="拍照或上传题目"
            :disabled="disabled"
            @click="disabled ? null : handleFileSelect"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <rect x="3" y="5" width="18" height="15" rx="2"/>
              <circle cx="12" cy="12" r="3.5"/>
            </svg>
            <span>拍照 / 上传题目</span>
          </button>
        </div>

        <button
          class="agent-composer__send-btn"
          :disabled="disabled || (!text.trim() && !imagePreview)"
          aria-label="发送"
          @click="handleSend"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true">
            <path d="M12 19V5M5 12l7-7 7 7"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-composer {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.agent-composer--disabled {
  opacity: 0.85;
}

.agent-composer__offline-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-bottom: 8px;
  border-radius: var(--radius-sm);
  background: var(--surface-warning, rgba(200, 145, 61, 0.08));
  border: 1px solid var(--border-warning, rgba(200, 145, 61, 0.2));
  color: var(--text-warning, #b8860b);
  font-size: var(--font-size-sm);
  line-height: 1.5;
}

.agent-composer__offline-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
}

.agent-composer__box--disabled {
  opacity: 0.6;
  pointer-events: none;
}

.agent-composer__tool-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.agent-composer__box {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 12px 14px 10px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.agent-composer__box:focus-within {
  border-color: var(--accent);
  box-shadow: var(--shadow-sm), var(--shadow-focus);
}

.agent-composer--large .agent-composer__box {
  border-radius: var(--radius-lg);
  padding: 16px 18px 12px;
}

/* 图片预览 */
.agent-composer__preview {
  position: relative;
  display: inline-flex;
  max-width: 100%;
  padding-bottom: 10px;
}

.agent-composer__preview-img {
  max-width: 180px;
  max-height: 140px;
  border-radius: var(--radius-sm);
  object-fit: contain;
  border: 1px solid var(--border-subtle);
}

.agent-composer__preview-remove {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  cursor: pointer;
  border: none;
  transition: background var(--transition-fast);
}

.agent-composer__preview-remove:hover {
  background: var(--danger);
}

/* 输入区 */
.agent-composer__input-row {
  display: flex;
  align-items: flex-end;
  gap: var(--space-2);
}

.agent-composer__textarea {
  flex: 1;
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  background: transparent;
  color: var(--text-primary);
  font-size: var(--font-size-base);
  line-height: 1.6;
  min-height: 28px;
  max-height: 160px;
  font-family: inherit;
  padding: 2px 0;
}

.agent-composer--large .agent-composer__textarea {
  font-size: 16px;
  line-height: 1.6;
  min-height: 44px;
  max-height: 200px;
}

.agent-composer__textarea::placeholder {
  color: var(--text-tertiary);
}

/* 工具栏 */
.agent-composer__tools {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 8px;
}

.agent-composer__tools-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.agent-composer__tool-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: var(--radius-sm);
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast);
  font-family: inherit;
}

.agent-composer__tool-btn:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}

.agent-composer__tool-btn svg {
  width: 16px;
  height: 16px;
}

.agent-composer__tool-btn--icon {
  width: 32px;
  height: 32px;
  justify-content: center;
  border: 1px solid var(--border-subtle);
  background: var(--surface);
}

.agent-composer__tool-btn--icon:hover {
  border-color: var(--border-strong);
  background: var(--surface-hover);
}

.agent-composer__tool-btn--text {
  padding: 6px 12px;
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--text-secondary);
}

.agent-composer__tool-btn--text:hover {
  color: var(--accent);
}

/* 发送按钮 */
.agent-composer__send-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  border: none;
  cursor: pointer;
  transition: background var(--transition-fast), transform var(--transition-fast);
  flex-shrink: 0;
}

.agent-composer__send-btn svg {
  width: 18px;
  height: 18px;
}

.agent-composer__send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.agent-composer__send-btn:active:not(:disabled) {
  transform: scale(0.94);
}

.agent-composer__send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

@media (max-width: 768px) {
  .agent-composer__box {
    padding: 10px 12px 8px;
    border-radius: var(--radius-md);
  }

  .agent-composer--large .agent-composer__box {
    padding: 12px 14px 10px;
    border-radius: var(--radius-md);
  }

  .agent-composer__textarea {
    font-size: 16px;
  }

  .agent-composer__tool-btn--text {
    font-size: var(--font-size-xs);
    padding: 6px 8px;
  }

  .agent-composer__tool-btn--text span {
    display: none;
  }

  .agent-composer__send-btn {
    width: 34px;
    height: 34px;
  }
}
</style>
