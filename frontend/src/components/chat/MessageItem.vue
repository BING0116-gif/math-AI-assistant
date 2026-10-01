<template>
  <div class="message-item" :class="[`msg-${message.sender}`, { streaming: isStreaming }]" :id="`msg-${message.id}`">
    <!-- AI 消息:∑ 头像 + 左对齐正文列(原型 chat.html .msg-ai) -->
    <div v-if="message.sender === 'ai'" class="msg-ai-wrap">
      <span class="ai-avatar" aria-hidden="true">∑</span>
      <div class="ai-body">
        <div v-if="message.type === 'image'" class="msg-image-wrap">
          <img :src="message.content" class="msg-image" alt="图片消息" />
          <div v-if="message.text" class="msg-image-text">{{ message.text }}</div>
        </div>
        <div v-else class="msg-content" v-html="renderedContent"></div>

        <MathVisualCard
          v-if="message.visualization"
          :spec="message.visualization"
          :verification="message.visualizationVerification"
        />
        <p
          v-else-if="message.visualizationStatus === 'failed'"
          class="visual-fallback"
          role="status"
        >
          图形暂时不可用，文字解答不受影响。
        </p>

        <MathAnimationCard v-if="message.animation" :initial-job="message.animation" />

        <!-- 流式状态指示 -->
        <div v-if="isStreaming && (!message.content || message.content.length === 0)" class="msg-loading">
          <span class="msg-loading-dot"></span>
          <span class="msg-loading-dot"></span>
          <span class="msg-loading-dot"></span>
          <span class="msg-loading-text">正在组织推导…</span>
        </div>

        <!-- 消息操作 — 默认弱化,hover 显示(原型 .msg-meta) -->
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
    </div>

    <!-- 用户消息:右对齐橙色气泡(原型 .msg-user .bubble) -->
    <div v-else class="msg-user-wrap">
      <div class="msg-bubble">
        <div v-if="message.type === 'image'" class="msg-image-wrap">
          <img :src="message.content" class="msg-image" alt="图片消息" />
          <div v-if="message.text" class="msg-image-text">{{ message.text }}</div>
        </div>
        <div v-else class="msg-content" v-html="renderedContent"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import MathVisualCard from '@/components/math/MathVisualCard.vue'
import MathAnimationCard from '@/components/math/MathAnimationCard.vue'

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
/* 原型 chat.html:
   - 用户消息右对齐橙色气泡(白字,16/16/4/16 圆角)
   - AI 消息 ∑ 头像 + 无气泡正文列(14px/1.75)
   - 操作默认弱化,hover 显示 */

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
  gap: 13px;
  width: 100%;
}
.ai-avatar {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  flex: none;
  margin-top: 2px;
  font-family: var(--font-disp);
  font-size: 14px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #17A98A, #0B7A5E 45%, #0AA2C4);
}
.ai-body {
  flex: 1;
  min-width: 0;
}

/* ---- 用户消息 ---- */
.msg-user-wrap {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  max-width: 82%;
  margin-left: auto;
}
.msg-bubble {
  background: var(--accent);
  color: #fff;
  padding: 11px 16px;
  border-radius: 16px 16px 4px 16px;
  font-size: 14px;
  line-height: 1.65;
  box-shadow: 0 2px 8px rgba(244, 87, 10, 0.3);
  max-width: 100%;
  overflow-wrap: break-word;
}
[data-theme='dark'] .msg-bubble {
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35);
}

/* ---- 内容排版 ---- */
.msg-content {
  font-size: 14px;
  line-height: 1.75;
  color: var(--ink-1);
  word-break: break-word;
}

.msg-bubble .msg-content {
  font-size: 14px;
  line-height: 1.65;
  color: #fff;
}

.visual-fallback {
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-left: 3px solid var(--amber);
  color: var(--ink-2);
  background: var(--surface-2);
  font-size: 13px;
  border-radius: 0 var(--r-s) var(--r-s) 0;
}

/* Markdown 元素(AI 正文对齐原型 ai-body) */
.msg-content :deep(p) {
  margin: 0 0 10px;
}
.msg-content :deep(p:last-child) {
  margin-bottom: 0;
}

.msg-content :deep(h1),
.msg-content :deep(h2),
.msg-content :deep(h3),
.msg-content :deep(h4) {
  font-size: 14.5px;
  font-weight: 600;
  line-height: 1.4;
  margin: 2px 0 8px;
  color: var(--ink-1);
}

.msg-content :deep(strong) {
  font-weight: 600;
  color: var(--ink-1);
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
  background: var(--surface-2);
  padding: 2px 6px;
  border-radius: var(--r-s);
  font-family: var(--font-mono);
  font-size: 0.875em;
  color: var(--ink-1);
}

.msg-content :deep(pre) {
  background: var(--surface-2);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--r-m);
  overflow-x: auto;
  margin: var(--space-3) 0;
  border: 1px solid var(--border);
}
.msg-content :deep(pre code) {
  background: none;
  padding: 0;
  border: none;
}

.msg-content :deep(blockquote) {
  margin: var(--space-3) 0;
  padding: var(--space-2) var(--space-4);
  border-left: 3px solid var(--border-strong);
  color: var(--ink-2);
  font-style: italic;
}

.msg-content :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: var(--space-3) 0;
  font-size: 13px;
}
.msg-content :deep(th),
.msg-content :deep(td) {
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--border);
  text-align: left;
}
.msg-content :deep(th) {
  background: var(--surface-2);
  font-weight: 600;
}

/* KaTeX 公式 — 块级公式走公式卡样式(math.scss .formula 语言) */
.msg-content :deep(.katex) {
  font-size: 1.05em;
}
.msg-content :deep(.katex-display) {
  margin: var(--space-4) 0 !important;
  padding: 14px 18px !important;
  overflow-x: auto;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
  text-align: center;
}
.msg-content :deep(.math-display) {
  display: block;
  margin: var(--space-4) 0;
  padding: 14px 18px;
  overflow-x: auto;
  text-align: center;
  font-family: var(--font-math);
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--r-m);
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
  border-radius: var(--r-m);
  display: block;
  border: 1px solid var(--border);
}
.msg-image-text {
  margin-top: var(--space-2);
  font-size: 13px;
  color: var(--ink-2);
  line-height: 1.6;
  word-break: break-word;
}
.msg-bubble .msg-image {
  border-color: rgba(255, 255, 255, 0.35);
}
.msg-bubble .msg-image-text {
  color: rgba(255, 255, 255, 0.92);
}

/* ---- 消息操作 — 默认弱化 ---- */
.msg-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-2);
  opacity: 0;
  transition: opacity var(--dur-fast);
}
.message-item:hover .msg-actions,
.message-item:focus-within .msg-actions {
  opacity: 1;
}

.msg-action-btn {
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: var(--r-pill);
  background: var(--surface);
  color: var(--ink-3);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast), border-color var(--dur-fast);
}
.msg-action-btn:hover {
  background: var(--brand-soft);
  color: var(--brand-text);
  border-color: var(--brand);
}
.msg-action-btn--done {
  color: var(--green);
  border-color: var(--green);
  background: var(--green-soft);
  cursor: default;
}
.msg-action-btn--skipped {
  color: var(--ink-3);
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
  background: var(--brand);
  animation: msgDotPulse 1.4s ease-in-out infinite;
}
.msg-loading-dot:nth-child(2) { animation-delay: 0.2s; }
.msg-loading-dot:nth-child(3) { animation-delay: 0.4s; }
.msg-loading-text {
  font-size: 13px;
  color: var(--ink-3);
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
    max-width: 92%;
  }
  .msg-image {
    max-width: 220px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .message-item,
  .msg-loading-dot,
  .message-item.streaming .msg-content::after {
    animation: none;
  }
}
</style>
