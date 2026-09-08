<template>
  <div class="message-item" :class="[`msg-${message.sender}`, { streaming: isStreaming }]" :id="`msg-${message.id}`">
    <!-- AI 消息：无大气泡，左对齐，占正文宽度 — 文档 §6.3 -->
    <div v-if="message.sender === 'ai'" class="msg-ai-wrap">
      <div class="msg-body msg-body--ai">
        <div v-if="message.type === 'image'" class="msg-image-wrap">
          <img :src="message.content" class="msg-image" alt="图片消息" />
          <div v-if="message.text" class="msg-image-text">{{ message.text }}</div>
        </div>
        <div v-else class="msg-content" v-html="renderedContent"></div>

        <!-- 流式状态指示 -->
        <div v-if="isStreaming && (!message.content || message.content.length === 0)" class="msg-loading">
          <span class="msg-loading-dot"></span>
          <span class="msg-loading-dot"></span>
          <span class="msg-loading-dot"></span>
          <span class="msg-loading-text">正在组织推导…</span>
        </div>

        <!-- 消息操作 — 文档 §6.3: 默认弱化，hover 显示 -->
        <div v-if="!isStreaming" class="msg-actions">
          <template v-if="message.errorBookStatus === 'added'">
            <button class="msg-action-btn msg-action-btn--done" disabled>已加入错题本</button>
          </template>
          <template v-else-if="message.errorBookStatus === 'skipped'">
            <button class="msg-action-btn msg-action-btn--skipped" disabled>已跳过</button>
          </template>
          <template v-else>
            <button class="msg-action-btn" @click.stop="$emit('addToErrorBook', message.id)">
              加入错题本
            </button>
            <button class="msg-action-btn" @click.stop="$emit('skipErrorBook', message.id)">
              跳过
            </button>
          </template>
        </div>
      </div>
      <div class="msg-time">{{ message.timestamp }}</div>
    </div>

    <!-- 用户消息：右对齐，小范围中性背景，最大宽度 80% — 文档 §6.3 -->
    <div v-else class="msg-user-wrap">
      <div class="msg-body msg-body--user">
        <div v-if="message.type === 'image'" class="msg-image-wrap">
          <img :src="message.content" class="msg-image" alt="图片消息" />
          <div v-if="message.text" class="msg-image-text">{{ message.text }}</div>
        </div>
        <div v-else class="msg-content" v-html="renderedContent"></div>
      </div>
      <div class="msg-time">{{ message.timestamp }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps({
  message: { type: Object, required: true },
  isStreaming: { type: Boolean, default: false }
})

defineEmits(['addToErrorBook', 'skipErrorBook'])

const renderedContent = computed(() => {
  if (props.message.sender === 'ai') {
    return renderMarkdown(props.message.content || '')
  }
  // 用户消息做简单转义
  const text = props.message.content || ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
})
</script>

<style scoped>
/* 文档 §6.3:
   - 用户消息右对齐，小范围中性背景，最大宽度 80%
   - AI 消息左对齐、无大气泡、占正文宽度
   - 时间戳和操作按钮默认弱化 */

.message-item {
  width: 100%;
  animation: msgFadeIn 0.3s ease-out;
}

@keyframes msgFadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ---- AI 消息 ---- */
.msg-ai-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
}

.msg-body--ai {
  width: 100%;
  /* 无大气泡：不加背景、边框、阴影 */
  padding: 0;
}

/* ---- 用户消息 ---- */
.msg-user-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  max-width: 80%;
  margin-left: auto; /* 右对齐 */
}

.msg-body--user {
  /* 小范围中性背景 */
  background: var(--surface-muted);
  border-radius: var(--radius-sm);
  padding: var(--space-2) var(--space-4);
  max-width: 100%;
}

/* ---- 内容排版 ---- */
.msg-content {
  font-size: var(--font-size-base);
  line-height: var(--line-height-base);
  color: var(--text-primary);
  word-break: break-word;
}

.msg-body--user .msg-content {
  font-size: var(--font-size-sm);
}

/* Markdown 元素 */
.msg-content :deep(p) {
  margin: var(--space-2) 0;
}
.msg-content :deep(p:first-child) {
  margin-top: 0;
}
.msg-content :deep(p:last-child) {
  margin-bottom: 0;
}

.msg-content :deep(h1),
.msg-content :deep(h2),
.msg-content :deep(h3) {
  font-weight: 600;
  line-height: var(--line-height-tight);
  margin: var(--space-4) 0 var(--space-2);
  color: var(--text-primary);
}
.msg-content :deep(h1) { font-size: var(--font-size-xl); }
.msg-content :deep(h2) { font-size: var(--font-size-lg); }
.msg-content :deep(h3) { font-size: var(--font-size-base); }

.msg-content :deep(strong) {
  font-weight: 600;
  color: var(--text-primary);
}

.msg-content :deep(em) {
  font-style: italic;
}

.msg-content :deep(ul),
.msg-content :deep(ol) {
  margin: var(--space-2) 0;
  padding-left: var(--space-6);
}
.msg-content :deep(li) {
  margin: var(--space-1) 0;
}

.msg-content :deep(code) {
  background: var(--surface-muted);
  padding: 2px 6px;
  border-radius: var(--radius-xs);
  font-family: var(--font-mono);
  font-size: 0.875em;
  color: var(--text-primary);
}

.msg-content :deep(pre) {
  background: var(--surface-muted);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-sm);
  overflow-x: auto;
  margin: var(--space-3) 0;
  border: 1px solid var(--border-subtle);
}
.msg-content :deep(pre code) {
  background: none;
  padding: 0;
  border: none;
  color: var(--text-primary);
}

.msg-content :deep(blockquote) {
  margin: var(--space-3) 0;
  padding: var(--space-2) var(--space-4);
  border-left: 3px solid var(--border-strong);
  color: var(--text-secondary);
  font-style: italic;
}

.msg-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: var(--space-3) 0;
  font-size: var(--font-size-sm);
}
.msg-content :deep(th),
.msg-content :deep(td) {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border-subtle);
  text-align: left;
}
.msg-content :deep(th) {
  background: var(--surface-muted);
  font-weight: 600;
}

/* KaTeX 公式 — 文档 §6.3: 行内公式与文字基线对齐，块级公式上下至少 16px 留白 */
.msg-content :deep(.katex) {
  font-size: 1.05em;
}
.msg-content :deep(.katex-display) {
  margin: var(--space-4) 0 !important;
  padding: var(--space-3) var(--space-4) !important;
  overflow-x: auto;
}
.msg-content :deep(.math-display) {
  display: block;
  margin: var(--space-4) 0;
  padding: var(--space-3) var(--space-4);
  overflow-x: auto;
  text-align: center;
}
.msg-content :deep(.math-inline) {
  display: inline;
}

/* ---- 图片 ---- */
.msg-image-wrap {
  margin: 0;
}
.msg-image {
  max-width: 280px;
  border-radius: var(--radius-sm);
  display: block;
  border: 1px solid var(--border-subtle);
}
.msg-image-text {
  margin-top: var(--space-2);
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  line-height: var(--line-height-base);
  word-break: break-word;
}

/* ---- 时间戳 — 默认弱化 ---- */
.msg-time {
  font-size: var(--font-size-xs);
  color: var(--text-tertiary);
  margin-top: var(--space-1);
  opacity: 0.7;
}
.msg-ai-wrap .msg-time {
  text-align: left;
}
.msg-user-wrap .msg-time {
  text-align: right;
}

/* ---- 消息操作 — 默认弱化 ---- */
.msg-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
  opacity: 0;
  transition: opacity var(--transition-fast);
}
.message-item:hover .msg-actions {
  opacity: 1;
}

.msg-action-btn {
  padding: var(--space-1) var(--space-3);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xs);
  background: var(--surface);
  color: var(--text-secondary);
  font-size: var(--font-size-xs);
  cursor: pointer;
  transition: background var(--transition-fast), color var(--transition-fast);
}
.msg-action-btn:hover {
  background: var(--surface-hover);
  color: var(--text-primary);
}
.msg-action-btn--done {
  color: var(--mastered);
  border-color: var(--mastered);
  cursor: default;
}
.msg-action-btn--skipped {
  color: var(--text-tertiary);
  cursor: default;
  text-decoration: line-through;
}
.msg-action-btn:disabled {
  pointer-events: none;
}

/* ---- 流式加载指示器 ---- */
.msg-loading {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: var(--space-2) 0;
}
.msg-loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary);
  animation: msgDotPulse 1.4s ease-in-out infinite;
}
.msg-loading-dot:nth-child(2) { animation-delay: 0.2s; }
.msg-loading-dot:nth-child(3) { animation-delay: 0.4s; }
.msg-loading-text {
  font-size: var(--font-size-sm);
  color: var(--text-tertiary);
  margin-left: var(--space-1);
}
@keyframes msgDotPulse {
  0%, 80%, 100% { opacity: 0.3; }
  40% { opacity: 1; }
}

/* ---- 流式状态光标 ---- */
.message-item.streaming .msg-content::after {
  content: '▊';
  display: inline;
  color: var(--accent);
  animation: msgCursorBlink 1s step-end infinite;
  margin-left: 2px;
}
@keyframes msgCursorBlink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* ---- 响应式 ---- */
@media (max-width: 768px) {
  .msg-user-wrap {
    max-width: 85%;
  }
  .msg-image {
    max-width: 220px;
  }
}
</style>
