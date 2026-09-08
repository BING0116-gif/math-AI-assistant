<template>
  <div class="rd">
    <header class="rd-head">
      <div class="rd-head-main">
        <h1 class="rd-title">能力就绪度</h1>
        <p class="rd-sub">
          只读诊断，不写库、不改配置。用于定位「配置漂移导致能力静默失效」。
        </p>
      </div>
      <button class="rd-btn" type="button" :disabled="loading" @click="load">
        {{ loading ? '检查中…' : '重新检查' }}
      </button>
    </header>

    <div v-if="error" class="rd-alert" role="alert">
      <span>{{ error }}</span>
      <button class="rd-btn rd-btn-sm" type="button" @click="load">重试</button>
    </div>

    <section v-if="summary" class="rd-summary" aria-label="就绪度汇总">
      <div class="rd-stat">
        <span class="rd-stat-label">就绪</span>
        <strong class="rd-stat-value">{{ summary.ok }} / {{ summary.total }}</strong>
      </div>
      <div class="rd-stat is-blocker">
        <span class="rd-stat-label">阻断</span>
        <strong class="rd-stat-value">{{ summary.blocker }}</strong>
      </div>
      <div class="rd-stat is-warning">
        <span class="rd-stat-label">降级</span>
        <strong class="rd-stat-value">{{ summary.warning }}</strong>
      </div>
      <div class="rd-stat">
        <span class="rd-stat-label">耗时</span>
        <strong class="rd-stat-value">{{ elapsedMs ?? '—' }} ms</strong>
      </div>
    </section>

    <p v-if="generatedAt" class="rd-meta">生成于 {{ generatedAt }}</p>

    <div v-if="loading && !capabilities.length" class="rd-loading">正在检查八项能力…</div>

    <section v-if="capabilities.length" class="rd-list">
      <article
        v-for="item in capabilities"
        :key="item.id"
        class="rd-item"
        :class="`rd-item--${item.status}`"
      >
        <span class="rd-badge" :class="`rd-badge--${item.status}`">{{ statusLabel(item.status) }}</span>
        <div class="rd-item-body">
          <h2 class="rd-item-name">{{ item.name }}</h2>
          <p class="rd-item-reason">{{ item.reason || '—' }}</p>
          <p v-if="item.remediation" class="rd-item-fix">{{ item.remediation }}</p>

          <details v-if="hasDetails(item)" class="rd-details">
            <summary>诊断细节</summary>
            <pre class="rd-pre">{{ formatDetails(item.details) }}</pre>
          </details>
        </div>
      </article>
    </section>

    <p v-if="!loading && !capabilities.length && !error" class="rd-empty">暂无数据</p>

    <footer class="rd-foot">
      轻量探测无法验证密钥是否真实有效——「key 存在但无效」只能由实际调用发现。
    </footer>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { readinessApi, unwrap } from '@/api/readiness'

const loading = ref(false)
const error = ref('')
const summary = ref(null)
const capabilities = ref([])
const generatedAt = ref('')
const elapsedMs = ref(null)

function statusLabel(status) {
  if (status === 'blocker') return '阻断'
  if (status === 'warning') return '降级'
  return '正常'
}

function hasDetails(item) {
  return item.details && Object.keys(item.details).length > 0
}

function formatDetails(details) {
  // 后端已做脱敏（密钥仅返回尾号），此处仅做长度保护，避免超长值撑破布局。
  const safe = {}
  for (const [key, value] of Object.entries(details)) {
    if (typeof value === 'string' && value.length > 120) {
      safe[key] = `${value.slice(0, 120)}…`
    } else {
      safe[key] = value
    }
  }
  return JSON.stringify(safe, null, 2)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = unwrap(await readinessApi.capabilities())
    summary.value = data.summary || null
    capabilities.value = data.capabilities || []
    generatedAt.value = data.generated_at ? new Date(data.generated_at).toLocaleString() : ''
    elapsedMs.value = data.elapsed_ms ?? null
  } catch (exc) {
    error.value = exc?.message || '就绪度检查失败'
    summary.value = null
    capabilities.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.rd {
  max-width: 960px;
  margin: 0 auto;
  padding: 24px 20px 48px;
  color: var(--text-primary);
}

.rd-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.rd-title {
  margin: 0;
  font-size: 22px;
  font-weight: 500;
}

.rd-sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.rd-btn {
  padding: 8px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-strong);
  background: var(--surface);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.rd-btn:hover:not(:disabled) {
  background: var(--surface-hover);
}

.rd-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.rd-btn-sm {
  padding: 4px 12px;
  font-size: 12px;
}

.rd-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 20px;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--danger);
  background: var(--surface-muted);
  color: var(--text-primary);
  font-size: 13px;
}

.rd-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px;
  margin-top: 20px;
}

.rd-stat {
  padding: 12px 16px;
  border-radius: var(--radius-md);
  background: var(--surface-muted);
  border: 1px solid var(--border-subtle);
}

.rd-stat-label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
}

.rd-stat-value {
  display: block;
  margin-top: 4px;
  font-size: 22px;
  font-weight: 500;
}

.rd-stat.is-blocker .rd-stat-value {
  color: var(--danger);
}

.rd-stat.is-warning .rd-stat-value {
  color: var(--warning);
}

.rd-meta {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
}

.rd-loading,
.rd-empty {
  margin-top: 24px;
  padding: 32px;
  text-align: center;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--surface-muted);
  border-radius: var(--radius-md);
}

.rd-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 16px;
}

.rd-item {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border-subtle);
  background: var(--surface);
}

.rd-item--blocker {
  border-color: var(--danger);
}

.rd-item--warning {
  border-color: var(--warning);
}

.rd-badge {
  flex-shrink: 0;
  align-self: flex-start;
  padding: 2px 10px;
  border-radius: var(--radius-pill);
  font-size: 12px;
  line-height: 1.6;
  background: var(--surface-muted);
  color: var(--text-secondary);
}

/* 状态以文字传达，颜色仅作辅助，不单独承载语义。 */
.rd-badge--ok {
  background: var(--success);
  color: #fff;
}

.rd-badge--warning {
  background: var(--warning);
  color: #1a1200;
}

.rd-badge--blocker {
  background: var(--danger);
  color: #fff;
}

.rd-item-body {
  min-width: 0;
}

.rd-item-name {
  margin: 0;
  font-size: 14px;
  font-weight: 500;
}

.rd-item-reason {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.rd-item-fix {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.6;
}

.rd-details {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.rd-details summary {
  cursor: pointer;
}

.rd-pre {
  margin: 8px 0 0;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  background: var(--surface-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.6;
  overflow-x: auto;
}

.rd-foot {
  margin-top: 28px;
  padding-top: 16px;
  border-top: 1px solid var(--border-subtle);
  font-size: 12px;
  color: var(--text-tertiary);
  line-height: 1.6;
}

@media (max-width: 640px) {
  .rd {
    padding: 16px 14px 32px;
  }

  .rd-head {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
