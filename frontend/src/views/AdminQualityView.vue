<script setup>
import { onMounted, ref } from 'vue'
import AdminShell from '@/components/shell/AdminShell.vue'
import { adminQualityApi, unwrapQuality } from '@/api/adminQuality'

const loading = ref(false)
const submitting = ref('')
const error = ref('')
const status = ref('pending')
const queue = ref({ items: [], total: 0 })

const verdictLabel = (value) => ({ pass: '通过', fail: '不通过', warn: '需关注' }[value] || '未判定')
const verdictClass = (value) => `quality-tag quality-tag--${value || 'pending'}`
const formatDate = (value) => value ? new Date(value).toLocaleString() : '暂无时间'

async function load() {
  loading.value = true
  error.value = ''
  try {
    queue.value = unwrapQuality(await adminQualityApi.queue({ status: status.value, limit: 50 }))
  } catch (exc) {
    error.value = exc?.message || '抽检队列读取失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function submit(row, verdict) {
  submitting.value = row.run_id
  error.value = ''
  try {
    await adminQualityApi.verdict(row.run_id, { verdict, issue_codes: (row.critic_issues || []).map((item) => item.code).filter(Boolean) })
    await load()
  } catch (exc) {
    error.value = exc?.message || '抽检判定提交失败，请稍后重试'
  } finally {
    submitting.value = ''
  }
}

function changeStatus(value) {
  status.value = value
  load()
}

onMounted(load)
</script>

<template>
  <AdminShell>
    <main class="quality-page">
      <header class="quality-head">
        <div>
          <p class="eyebrow">阶段一 · 人工抽检</p>
          <h2>回答质量队列</h2>
          <p>仅显示脱敏的运行元数据和问题代码，不展示学生身份、原始问题或答案正文。</p>
        </div>
        <button class="refresh" type="button" :disabled="loading" @click="load">{{ loading ? '读取中…' : '刷新队列' }}</button>
      </header>

      <nav class="quality-tabs" aria-label="抽检状态">
        <button v-for="item in [['pending', '待处理'], ['graded', '已处理'], ['all', '全部']]" :key="item[0]" type="button" :class="{ active: status === item[0] }" @click="changeStatus(item[0])">{{ item[1] }}</button>
      </nav>

      <p v-if="error" class="alert" role="alert">{{ error }}</p>
      <p v-if="loading && !queue.items.length" class="state" role="status">正在读取抽检队列…</p>
      <section v-if="!loading && !queue.items.length" class="empty" aria-live="polite">当前没有符合条件的抽检项。</section>

      <section v-if="queue.items.length" class="queue-list" aria-label="回答质量抽检列表">
        <article v-for="row in queue.items" :key="row.run_id" class="queue-card">
          <div class="queue-card__head">
            <div><span class="run-id">{{ row.run_id }}</span><span class="request-kind">{{ row.request_kind }} · {{ row.tutor_mode || '默认模式' }}</span></div>
            <span :class="verdictClass(row.critic_verdict)">{{ verdictLabel(row.critic_verdict) }}</span>
          </div>
          <div class="queue-meta"><span>创建于 {{ formatDate(row.created_at) }}</span><span>人工判定：{{ verdictLabel(row.review_verdict) }}</span></div>
          <div class="issue-list"><span v-for="issue in row.critic_issues" :key="`${issue.code}-${issue.location || ''}`" class="issue">{{ issue.code }}<small v-if="issue.location"> · {{ issue.location }}</small></span><span v-if="!row.critic_issues?.length" class="muted">暂无问题代码</span></div>
          <div v-if="!row.review_verdict" class="queue-actions"><button type="button" class="button button--quiet" :disabled="submitting === row.run_id" @click="submit(row, 'pass')">通过</button><button type="button" class="button button--danger" :disabled="submitting === row.run_id" @click="submit(row, 'fail')">不通过</button></div>
        </article>
      </section>
    </main>
  </AdminShell>
</template>

<style scoped>
.quality-page { max-width: 980px; margin: 0 auto; padding: clamp(22px, 4vw, 48px); }
.quality-head { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; margin-bottom: 20px; }
.eyebrow { margin: 0 0 8px; color: var(--accent-text); font-size: 12px; } h2 { margin: 0; font-size: clamp(24px, 4vw, 36px); } .quality-head p:last-child { margin: 8px 0 0; color: var(--ink-2); }
.refresh, .quality-tabs button, .button { border: 1px solid var(--border); border-radius: 8px; background: var(--surface); color: var(--ink-1); cursor: pointer; }
.refresh { padding: 9px 14px; } .refresh:disabled, .button:disabled { opacity: .55; cursor: wait; }
.quality-tabs { display: flex; gap: 8px; margin-bottom: 18px; } .quality-tabs button { padding: 8px 14px; } .quality-tabs button.active { border-color: var(--accent); color: var(--accent-text); background: var(--accent-soft); }
.alert { padding: 12px 14px; border: 1px solid var(--rose); border-radius: 8px; color: var(--rose); background: var(--rose-soft); } .state, .empty, .muted { color: var(--ink-2); } .empty { padding: 34px 20px; border: 1px dashed var(--border); border-radius: 12px; text-align: center; }
.queue-list { display: grid; gap: 12px; } .queue-card { padding: 18px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); } .queue-card__head, .queue-meta, .queue-actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; } .queue-meta { margin-top: 8px; color: var(--ink-2); font-size: 12px; } .run-id { font-family: var(--font-mono, monospace); font-size: 13px; } .request-kind { margin-left: 10px; color: var(--ink-2); font-size: 13px; }
.quality-tag { padding: 4px 9px; border-radius: 999px; font-size: 12px; background: var(--surface-2); } .quality-tag--fail { color: var(--rose); background: var(--rose-soft); } .quality-tag--warn { color: var(--accent-text); background: var(--accent-soft); } .quality-tag--pass { color: var(--green, #287a57); }
.issue-list { display: flex; flex-wrap: wrap; gap: 7px; margin: 16px 0; } .issue { padding: 5px 8px; border-radius: 6px; color: var(--ink-2); background: var(--surface-2); font-size: 12px; } .issue small { color: var(--ink-3); } .button { padding: 8px 13px; } .button--quiet { margin-left: auto; } .button--danger { color: var(--rose); border-color: var(--rose); }
@media (max-width: 560px) { .quality-head { display: block; } .refresh { margin-top: 16px; } .queue-card__head, .queue-meta { align-items: flex-start; flex-direction: column; } .button--quiet { margin-left: 0; } }
</style>
