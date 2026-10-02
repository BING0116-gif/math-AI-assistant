<template>
  <AdminShell>
    <main class="metrics-page">
      <header class="metrics-head">
        <div>
          <p class="eyebrow">运行可观测性</p>
          <h2>Agent 指标</h2>
          <p>仅展示当前进程的累计聚合数据；趋势与 P95 请在 Prometheus/Grafana 中计算。</p>
        </div>
        <button class="refresh" type="button" :disabled="loading" @click="load">
          {{ loading ? '读取中…' : '刷新指标' }}
        </button>
      </header>

      <p v-if="error" class="alert" role="alert">{{ error }}</p>
      <p v-if="loading && !metrics" class="state" role="status">正在读取 Agent 指标…</p>

      <template v-if="metrics">
        <p class="meta">数据语义：{{ metrics.semantics === 'process_cumulative' ? '进程累计' : '未知' }} · {{ formatDate(metrics.as_of) }}</p>

        <section class="stat-grid" aria-label="Agent 运行指标">
          <article class="stat-card"><span>完成运行</span><strong>{{ count(metrics.runs, 'completed') }}</strong><small>失败 {{ count(metrics.runs, 'failed') }}</small></article>
          <article class="stat-card"><span>平均运行耗时</span><strong>{{ seconds(metrics.latency?.average_seconds) }}</strong><small>{{ metrics.latency?.observations ?? 0 }} 次观测</small></article>
          <article class="stat-card"><span>首 Token 延迟</span><strong>{{ seconds(metrics.time_to_first_token?.average_seconds) }}</strong><small>{{ metrics.time_to_first_token?.observations ?? 0 }} 次观测</small></article>
          <article class="stat-card"><span>工具失败</span><strong :class="{ danger: count(metrics.tool_calls, 'error') > 0 }">{{ count(metrics.tool_calls, 'error') }}</strong><small>成功 {{ count(metrics.tool_calls, 'success') }}</small></article>
        </section>

        <section class="panel-grid">
          <article class="panel">
            <h3>上下文健康度</h3>
            <div class="row"><span>平均历史字符数</span><strong>{{ number(metrics.context?.average_chars) }}</strong></div>
            <div class="row"><span>发生裁剪</span><strong>{{ total(metrics.context_trims) }} 次</strong></div>
            <div class="row"><span>工具平均耗时</span><strong>{{ seconds(metrics.tool_latency?.average_seconds) }}</strong></div>
          </article>
          <article class="panel">
            <h3>Token 消耗</h3>
            <div class="row"><span>输入 Token</span><strong>{{ number(metrics.tokens?.input) }}</strong></div>
            <div class="row"><span>输出 Token</span><strong>{{ number(metrics.tokens?.output) }}</strong></div>
            <div class="row"><span>合计 Token</span><strong>{{ number((metrics.tokens?.input || 0) + (metrics.tokens?.output || 0)) }}</strong></div>
          </article>
        </section>
      </template>
    </main>
  </AdminShell>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import AdminShell from '@/components/shell/AdminShell.vue'
import { adminAgentMetricsApi, unwrapAgentMetrics } from '@/api/adminAgentMetrics'

const loading = ref(false)
const error = ref('')
const metrics = ref(null)

const count = (value, key) => Number(value?.[key] || 0)
const total = (value) => Object.values(value || {}).reduce((sum, item) => sum + Number(item || 0), 0)
const number = (value) => Number(value || 0).toLocaleString()
const seconds = (value) => `${Number(value || 0).toFixed(2)} s`
const formatDate = (value) => value ? new Date(value).toLocaleString() : '暂无时间'

async function load() {
  loading.value = true
  error.value = ''
  try {
    metrics.value = unwrapAgentMetrics(await adminAgentMetricsApi.get())
  } catch (exc) {
    error.value = exc?.message || 'Agent 指标读取失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.metrics-page { max-width: 1180px; margin: 0 auto; padding: clamp(22px, 4vw, 48px); }
.metrics-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 22px; }
.eyebrow { margin: 0 0 8px; color: var(--accent-text); font-size: 12px; }
h2 { margin: 0; font-size: clamp(24px, 4vw, 36px); }
.metrics-head p:last-child { margin: 8px 0 0; color: var(--ink-2); }
.refresh { padding: 9px 14px; border: 1px solid var(--border); border-radius: 8px; color: var(--ink-1); background: var(--surface); cursor: pointer; }
.refresh:disabled { opacity: .6; cursor: wait; }
.alert { padding: 12px 14px; border: 1px solid var(--rose); border-radius: 8px; color: var(--rose); background: var(--rose-soft); }
.state, .meta { color: var(--ink-2); }
.meta { margin: 0 0 14px; font-size: 12px; }
.stat-grid, .panel-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.stat-card, .panel { padding: 20px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.stat-card span, .stat-card small { display: block; color: var(--ink-2); font-size: 13px; }
.stat-card strong { display: block; margin: 12px 0 6px; font-size: 30px; font-weight: 600; }
.stat-card small { color: var(--ink-3); }
.danger { color: var(--rose); }
.panel-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); margin-top: 14px; }
.panel h3 { margin: 0 0 10px; }
.row { display: flex; justify-content: space-between; gap: 16px; padding: 12px 0; border-top: 1px solid var(--border); color: var(--ink-2); }
.row strong { color: var(--ink-1); font-variant-numeric: tabular-nums; }
@media (max-width: 760px) { .metrics-head { display: block; } .refresh { margin-top: 16px; } .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 480px) { .metrics-page { padding: 20px 16px; } .panel-grid { grid-template-columns: 1fr; } }
</style>
