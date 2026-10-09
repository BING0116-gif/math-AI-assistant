<template>
  <div class="message-item" :class="[`msg-${message.sender}`, { streaming: isStreaming }]" :id="`msg-${message.id}`">
    <!-- AI 消息:∑ 头像 + 左对齐正文列(原型 chat.html .msg-ai) -->
    <div v-if="message.sender === 'ai'" class="msg-ai-wrap">
      <span class="ai-avatar" aria-hidden="true">∑</span>
      <div class="ai-body">
        <!-- 思考过程：只在自由辅导模式渲染，面板不走打字机，直接呈现已确定的轮次纪要 -->
        <details v-if="showTrace" class="agent-thinking" :open="isStreaming">
          <summary>
            <span class="agent-thinking__title">{{ traceTitle }}</span>
            <span class="agent-thinking__count">（{{ traceRounds.length }} 轮）</span>
          </summary>
          <p class="agent-thinking__note">以下为 Agent 实际执行与决策纪要</p>
          <div
            v-for="round in traceRounds"
            :key="`round-${round.round}`"
            class="thinking-round"
            :class="{ 'thinking-round--draft': !round.kind }"
          >
            <div class="thinking-round__head">
              <span class="thinking-round__label">{{ labelOfTraceRound(round) }}</span>
              <span v-if="elapsedText(round.elapsedMs)" class="thinking-round__time">{{ elapsedText(round.elapsedMs) }}</span>
            </div>
            <p v-if="textOfTraceRound(round)" class="thinking-round__text" v-text="textOfTraceRound(round)"></p>
            <p v-else-if="isDraftRound(round)" class="thinking-round__draft">思考中，本轮文本定性后归档为纪要。</p>
            <div v-for="(tool, toolIndex) in round.tools" :key="`tool-${tool.tool}-${toolIndex}`" class="thinking-tool" :class="`thinking-tool--${stepState(tool.status)}`">
              <span class="thinking-tool__name" v-text="tool.label"></span>
              <span v-if="tool.status" class="thinking-tool__status" v-text="toolRowStatusText(tool.status)"></span>
              <span v-if="tool.inputSummary" class="thinking-tool__io" v-text="tool.inputSummary"></span>
              <span v-if="tool.outputSummary" class="thinking-tool__io thinking-tool__io--out" v-text="tool.outputSummary"></span>
            </div>
            <p v-if="round.truncated" class="thinking-round__cut">该轮纪要过长，已截断。</p>
          </div>
        </details>
        <details v-if="message.agentSteps?.length" class="agent-timeline" :open="isStreaming">
          <summary>Agent 执行过程 · {{ message.agentSteps.length }} 步</summary>
          <div v-for="(step, index) in message.agentSteps" :key="`${step.type}-${step.tool}-${index}`" class="agent-step" :class="`agent-step--${stateOfStep(step)}`">
            <span class="agent-step__icon" :class="{ 'agent-step__icon--tool': step.type === 'tool_start' || step.type === 'tool_end' || step.type === 'tool_error', 'agent-step__icon--error': stateOfStep(step) === 'failed' }" aria-hidden="true"></span>
            <span class="agent-step__label">{{ step.label }}</span>
            <span v-if="stateOfStep(step) === 'running'" class="agent-step__spinner" :aria-label="textOfStep(step)"></span>
            <span v-else-if="textOfStep(step)" class="agent-step__status">{{ textOfStep(step) }}</span>
          </div>
        </details>
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

        <!-- Critic 可信度徽标(阶段五 5-C):后验质量检查结果 -->
        <div v-if="message.critic?.verdict && !isStreaming" class="critic-badge" :class="`critic-badge--${message.critic.verdict}`" :title="criticTitle">
          <ShieldCheck :size="13" />
          <span>{{ criticLabel }}</span>
        </div>

        <!-- 消息操作 — 默认弱化,hover 显示(原型 .msg-meta);系统欢迎语不可加入错题本 -->
        <div v-if="!isStreaming && !message.system" class="msg-actions">
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
import { ShieldCheck } from 'lucide-vue-next'
import { renderMarkdown } from '@/utils/markdown'
import {
  isDraftRound,
  labelOfTraceRound,
  stateOfStep,
  stepState,
  textOfStep,
  textOfTraceRound,
  toolRowStatusText,
  traceSeconds,
  visibleTraceRounds,
} from '@/utils/toolActivity'
import { isFreeTutorMode } from '@/utils/tutorModes'
import MathVisualCard from '@/components/math/MathVisualCard.vue'
import MathAnimationCard from '@/components/math/MathAnimationCard.vue'

const props = defineProps({
  message: { type: Object, required: true },
  isStreaming: { type: Boolean, default: false },
  // 当前会话的辅导方式：只有自由对话允许看思考面板，工具时间线四种模式照旧
  tutorMode: { type: String, default: '' }
})

defineEmits(['addToErrorBook', 'skipErrorBook'])

const traceRounds = computed(() => visibleTraceRounds(props.message.trace))
const showTrace = computed(
  () => isFreeTutorMode(props.tutorMode) && traceRounds.value.length > 0,
)
const traceElapsed = computed(() => traceSeconds(props.message.trace))
// 没带耗时（旧数据、只有工具行的轮次）时不拼一个假的「· 0s」。
const traceTitle = computed(() =>
  traceElapsed.value > 0 ? `思考过程 · ${traceElapsed.value}s` : '思考过程',
)

function elapsedText(ms) {
  if (!Number.isFinite(ms) || ms <= 0) return ''
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)}s`
}

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

// Critic 徽标文案(阶段五 5-C):verdict → 展示语义
const criticLabel = computed(() => {
  const verdict = props.message.critic?.verdict
  if (verdict === 'pass') return '已通过质量检查'
  if (verdict === 'warn') return '存在小瑕疵'
  if (verdict === 'fail') return '质量存疑,建议追问'
  return ''
})
const criticTitle = computed(() => {
  const issues = props.message.critic?.issues || []
  return issues.length ? `问题: ${issues.join('、')}` : 'Answer Critic 后验检查'
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
.agent-timeline {
  display: grid;
  gap: 6px;
  margin: 0 0 12px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface-2);
  color: var(--ink-2);
  font-size: 12px;
}
.agent-timeline summary { cursor: pointer; color: var(--ink-1); font-weight: 650; min-height: 24px; }
.agent-timeline summary::marker { color: var(--brand); }
.agent-step { display: flex; align-items: center; gap: 8px; min-height: 24px; }
.agent-step__icon { width: 18px; height: 18px; position: relative; flex: 0 0 18px; border-radius: 50%; background: var(--brand-soft); }
.agent-step__icon::after { content: ''; position: absolute; inset: 5px; border: 1.5px solid var(--brand-text); border-radius: 50%; }
.agent-step__icon--tool::after { inset: 4px 5px; border-radius: 2px; transform: rotate(45deg); }
.agent-step__label { flex: 1; min-width: 0; }
.agent-step__status { color: var(--ink-3); font-size: 11px; }
.agent-step--done .agent-step__status { color: var(--green, #1E9E6A); }
.agent-step--failed .agent-step__status { color: var(--danger, #d14b4b); }
.agent-step__icon--error { background: color-mix(in srgb, var(--danger, #d14b4b) 16%, transparent); }
.agent-step__icon--error::after { border-color: var(--danger, #d14b4b); }
.agent-step__spinner { width: 10px; height: 10px; border: 1.5px solid var(--border-strong); border-top-color: var(--brand); border-radius: 50%; animation: agentSpin .8s linear infinite; }
@keyframes agentSpin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .agent-step__spinner { animation: none; } }

/* ---- 思考过程纪要（仅自由辅导模式） ---- */
.agent-thinking {
  display: grid;
  gap: 8px;
  margin: 0 0 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--brand);
  border-radius: 12px;
  background: var(--surface-2);
  color: var(--ink-2);
  font-size: 12px;
}
.agent-thinking summary {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: var(--ink-1);
  font-weight: 650;
  min-height: 24px;
}
.agent-thinking summary::marker { color: var(--brand); }
.agent-thinking__count { color: var(--ink-3); font-size: 11px; font-weight: 500; }
.agent-thinking__note { margin: 0; color: var(--ink-3); font-size: 11px; }
.thinking-round { display: grid; gap: 5px; padding: 7px 0 8px; border-top: 1px dashed var(--border); }
.thinking-round:first-of-type { border-top: none; padding-top: 0; }
.thinking-round__head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.thinking-round__label { color: var(--ink-1); font-size: 11.5px; font-weight: 600; }
.thinking-round__time { color: var(--ink-3); font-family: var(--font-mono); font-size: 11px; }
.thinking-round__text {
  margin: 0;
  padding-left: 9px;
  border-left: 2px solid var(--border-strong);
  color: var(--ink-2);
  font-size: 12.5px;
  line-height: 1.7;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.thinking-round__cut { margin: 0; color: var(--amber, #b6802b); font-size: 11px; }
/* 尚未定性的轮：文本还是临时增量，淡一点，和已归档的过程轮区分开。 */
.thinking-round--draft .thinking-round__label { color: var(--ink-3); font-weight: 550; }
.thinking-round--draft .thinking-round__text {
  border-left-color: var(--border);
  color: var(--ink-3);
}
.thinking-round__draft { margin: 0; color: var(--ink-3); font-size: 11.5px; }
.thinking-tool {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  overflow-x: auto;
}
.thinking-tool__name { flex: none; color: var(--ink-1); font-size: 11.5px; font-weight: 600; }
/* 终态文案：面板里的工具行也要能看出“调用失败”，不能只摆个工具名。 */
.thinking-tool__status { flex: none; color: var(--ink-3); font-size: 11px; }
.thinking-tool--failed .thinking-tool__status { color: var(--danger, #c2413a); }
.thinking-tool--running .thinking-tool__status { color: var(--ink-3); font-style: italic; }
.thinking-tool__io {
  flex: none;
  padding: 1px 6px;
  border-radius: 6px;
  background: var(--surface-2);
  color: var(--ink-3);
  font-family: var(--font-mono);
  font-size: 11px;
  white-space: nowrap;
}
.thinking-tool__io--out { background: var(--brand-soft); color: var(--brand-text); }
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

@media (max-width: 480px) {
  .agent-thinking {
    padding: 9px 10px;
    font-size: 11.5px;
  }
  .thinking-round__text {
    font-size: 12px;
    line-height: 1.65;
  }
  /* 窄屏不横滚终端条：摘要换行，宁可高一点也要可读 */
  .thinking-tool {
    flex-wrap: wrap;
    align-items: flex-start;
    overflow-x: visible;
  }
  .thinking-tool__io {
    flex: 1 1 auto;
    white-space: normal;
    overflow-wrap: anywhere;
  }
}

@media (prefers-reduced-motion: reduce) {
  .message-item,
  .msg-loading-dot,
  .message-item.streaming .msg-content::after {
    animation: none;
  }
}

/* Critic 可信度徽标(阶段五 5-C) */
.critic-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
}
.critic-badge--pass { background: var(--green-soft, rgba(60, 150, 105, .12)); color: var(--green); }
.critic-badge--warn { background: var(--amber-soft); color: var(--amber); }
.critic-badge--fail { background: var(--rose-soft); color: var(--rose); }
</style>
