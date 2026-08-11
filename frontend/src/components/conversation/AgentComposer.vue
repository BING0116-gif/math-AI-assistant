<script setup lang="ts">
import { ref, nextTick, onMounted, onUnmounted, computed } from 'vue'

const props = withDefaults(defineProps<{
  large?: boolean
}>(), {
  large: false,
})

const emit = defineEmits<{
  send: [text: string]
  sendImage: [text: string, imageData: string]
}>()

const text = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const imagePreview = ref<string | null>(null)
const isComposing = ref(false) // IME 输入法状态

const placeholder = computed(() => {
  if (imagePreview.value) return '添加文字说明...'
  return '输入问题，或拖入一道题目……'
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
  const trimmed = text.value.trim()
  if (imagePreview.value) {
    emit('sendImage', trimmed, imagePreview.value)
    text.value = ''
    imagePreview.value = null
    autoResize()
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
    :class="{ 'agent-composer--large': large }"
  >
    <div
      class="agent-composer__box"
      @drop.prevent="handleDrop"
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
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6 6 18M6 6l12 12"/></svg>
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
          @compositionstart="isComposing = true"
          @compositionend="isComposing = false"
          @keydown="handleKeydown"
          @input="autoResize"
          @paste="handlePaste"
          aria-label="输入数学问题"
        />
      </div>

      <!-- 工具栏：参考豆包 Chat Composer 的底部操作条布局 -->
      <div class="agent-composer__tools">
        <button
          class="agent-composer__tool-btn agent-composer__tool-btn--round"
          aria-label="上传图片"
          title="上传图片"
          @click="handleFileSelect"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
            <circle cx="8.5" cy="8.5" r="1.5"/>
            <polyline points="21 15 16 10 5 21"/>
          </svg>
        </button>

        <span class="agent-composer__spacer" />

        <button
          class="agent-composer__send-btn"
          :disabled="!text.trim() && !imagePreview"
          aria-label="发送"
          @click="handleSend"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M5 12h14M12 5l7 7-7 7"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- 提示行 -->
    <div class="agent-composer__hint">
      <span>Enter 发送 · Shift+Enter 换行 · 可粘贴或拖入图片</span>
    </div>
  </div>
</template>

<style scoped>
/* 外层包装，保持与外部布局约束（max-width、width）兼容 */
.agent-composer {
  display: flex;
  flex-direction: column;
  width: 100%;
}

/* 参考豆包 Chat Composer：大圆角、轻边框、内部 padding 上松下紧 */
.agent-composer__box {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-strong);
  border-radius: 22px;
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  padding: 14px 16px 12px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
}

.agent-composer__box:focus-within {
  border-color: var(--accent);
  box-shadow: var(--shadow-sm), var(--shadow-focus);
}

/* 大模式 — 首页用，更突出 */
.agent-composer--large .agent-composer__box {
  border-radius: 24px;
  padding: 18px 20px 14px;
}

.agent-composer__preview {
  position: relative;
  display: inline-block;
  max-width: 100%;
  padding-bottom: 12px;
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
  top: 8px;
  right: 8px;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  cursor: pointer;
  border: none;
  transition: background var(--transition-fast);
}

.agent-composer__preview-remove:hover {
  background: var(--danger);
}

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
  font-size: 15px;
  line-height: 1.55;
  min-height: 28px;
  max-height: 160px;
  font-family: inherit;
  padding: 2px 0;
}

.agent-composer--large .agent-composer__textarea {
  font-size: 16px;
  line-height: 1.6;
  min-height: 48px;
  max-height: 192px;
}

.agent-composer__textarea::placeholder {
  color: var(--text-tertiary);
}

/* 底部工具栏：左上传、右发送，中间 spacer 顶开 */
.agent-composer__tools {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.agent-composer__spacer {
  flex: 1;
  min-width: 8px;
}

.agent-composer__tool-btn {
  display: grid;
  place-items: center;
  border-radius: var(--radius-sm);
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  transition: color var(--transition-fast), background var(--transition-fast);
}

.agent-composer__tool-btn--round {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  background: transparent;
}

.agent-composer__tool-btn:hover {
  color: var(--accent);
  background: var(--surface-muted);
}

.agent-composer__tool-btn svg {
  width: 18px;
  height: 18px;
}

.agent-composer__send-btn {
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--accent);
  color: var(--color-text-inverse, #fff);
  border: none;
  cursor: pointer;
  transition: background var(--transition-fast), transform var(--transition-fast);
}

.agent-composer__send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
  transform: scale(1.05);
}

.agent-composer__send-btn:active:not(:disabled) {
  transform: scale(0.96);
}

.agent-composer__send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.agent-composer__send-btn svg {
  width: 18px;
  height: 18px;
}

.agent-composer__hint {
  margin-top: 8px;
  padding: 0 12px;
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  text-align: center;
  line-height: 1.4;
}

@media (max-width: 768px) {
  .agent-composer__box {
    padding: 12px 14px 10px;
    border-radius: 20px;
  }

  .agent-composer--large .agent-composer__box {
    padding: 14px 16px 12px;
    border-radius: 22px;
  }

  .agent-composer__textarea {
    font-size: 16px; /* 防止 iOS 缩放 */
  }
}
</style>
