<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AppShell from '@/components/shell/AppShell.vue'
import { getProactiveActions, retryProactiveAction, cancelProactiveAction, setProactivePreference } from '@/api/learning'
import { apiErrorMessage } from '@/utils/apiError'
import { Bell, Check, RefreshCw, X, Pause, Play } from 'lucide-vue-next'

const router = useRouter()
const actions = ref<any[]>([])
const enabled = ref(true)
const loading = ref(true)
const busy = ref('')
const error = ref('')

const statusLabel: Record<string, string> = {
  pending: '待处理', delivered: '已完成', failed: '失败，可重试', dead: '已进入死信', cancelled: '已取消', expired: '已过期',
}
const typeLabel: Record<string, string> = {
  review_reminder: '复习提醒', learning_nudge: '学习提醒', targeted_practice: '专项练习', goal_deadline_reminder: '目标提醒',
}
const active = computed(() => actions.value.filter((item) => ['pending', 'failed', 'dead'].includes(item.status)))
const history = computed(() => actions.value.filter((item) => !['pending', 'failed', 'dead'].includes(item.status)))

async function load() {
  loading.value = true; error.value = ''
  try {
    const { data } = await getProactiveActions(100)
    actions.value = data?.items ?? data?.data?.items ?? []
    enabled.value = data?.enabled ?? true
  } catch (e) { error.value = apiErrorMessage(e, '通知暂时无法加载') }
  finally { loading.value = false }
}

async function togglePreference() {
  busy.value = 'preference'
  try { await setProactivePreference(!enabled.value); enabled.value = !enabled.value }
  catch (e) { error.value = apiErrorMessage(e, '通知偏好更新失败') }
  finally { busy.value = '' }
}

async function mutate(item: any, operation: 'retry' | 'cancel') {
  busy.value = item.id
  try {
    if (operation === 'retry') await retryProactiveAction(item.id)
    else await cancelProactiveAction(item.id)
    await load()
  } catch (e) { error.value = apiErrorMessage(e, operation === 'retry' ? '重试失败' : '取消失败') }
  finally { busy.value = '' }
}

function openAction(item: any) {
  const code = item.evidence?.knowledge_point
  if (code) router.push({ path: '/knowledge', query: { point: code } })
  else if (item.evidence?.error_item_id) router.push(`/error-book/${item.evidence.error_item_id}`)
  else router.push('/dashboard')
}

function formatTime(value: string) {
  if (!value) return ''
  return new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

onMounted(load)
</script>

<template>
  <AppShell>
    <template #topbar-title><span>通知中心</span></template>
    <div class="notification-page">
      <header class="page-head">
        <div><h1 class="t-1">主动学习通知</h1><p class="sub">提醒、失败任务和恢复动作都在这里留痕。</p></div>
        <button class="btn" type="button" :disabled="busy === 'preference'" @click="togglePreference">
          <Pause v-if="enabled" class="ic-15" /><Play v-else class="ic-15" />
          {{ enabled ? '暂停主动提醒' : '恢复主动提醒' }}
        </button>
      </header>
      <div v-if="error" class="app-state" role="alert"><p>{{ error }}</p><button type="button" @click="load">重试</button></div>
      <div v-else-if="loading" class="notification-empty">正在加载通知…</div>
      <template v-else>
        <section class="card"><div class="card-head"><span class="t-3">待处理</span><span class="tag tag-soft-accent">{{ active.length }} 条</span></div>
          <div v-if="!active.length" class="notification-empty"><Check class="ic-18" />当前没有失败或待处理任务</div>
          <ul v-else class="notification-list">
            <li v-for="item in active" :key="item.id" class="notification-row">
              <button class="row-main" type="button" @click="openAction(item)"><Bell class="ic-16" /><span><strong>{{ typeLabel[item.action_type] || item.action_type }}</strong><small>{{ item.trigger }} · {{ formatTime(item.created_at) }}</small><small v-if="item.last_error" class="error-text">{{ item.last_error }}</small></span></button>
              <span class="row-actions"><span class="tag" :class="item.status === 'dead' ? 'tag-soft-rose' : 'tag-soft-amber'">{{ statusLabel[item.status] }}</span><button v-if="item.status === 'failed'" class="btn btn-small" :disabled="busy === item.id" @click="mutate(item, 'retry')"><RefreshCw class="ic-14" />重试</button><button v-if="item.status === 'pending' || item.status === 'failed'" class="icon-btn" aria-label="取消通知" :disabled="busy === item.id" @click="mutate(item, 'cancel')"><X class="ic-15" /></button></span>
            </li>
          </ul>
        </section>
        <section class="card"><div class="card-head"><span class="t-3">处理记录</span><span class="caption">最近 100 条</span></div>
          <div v-if="!history.length" class="notification-empty">暂无处理记录</div>
          <ul v-else class="notification-list history"><li v-for="item in history" :key="item.id" class="notification-row"><span class="row-main"><Check class="ic-16" /><span><strong>{{ typeLabel[item.action_type] || item.action_type }}</strong><small>{{ formatTime(item.created_at) }}</small></span></span><span class="tag tag-plain">{{ statusLabel[item.status] }}</span></li></ul>
        </section>
      </template>
    </div>
  </AppShell>
</template>

<style scoped>
.notification-page{width:100%;max-width:900px;margin:0 auto;padding:24px clamp(16px,3vw,32px) 44px;display:grid;gap:16px}.page-head{display:flex;justify-content:space-between;align-items:flex-end;gap:16px}.page-head h1{margin:0}.sub{margin:5px 0 0;color:var(--ink-3);font-size:13px}.notification-list{list-style:none;padding:0;margin:0}.notification-row{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 20px;border-top:1px solid var(--border)}.row-main{display:flex;align-items:flex-start;gap:10px;min-width:0;text-align:left;color:var(--ink-1);background:none;border:0;cursor:pointer}.row-main span{display:grid;gap:3px}.row-main small{color:var(--ink-3);font-size:12px}.row-actions{display:flex;align-items:center;gap:8px;flex:none}.btn-small{padding:5px 9px;font-size:12px}.notification-empty{display:flex;justify-content:center;align-items:center;gap:8px;padding:28px;color:var(--ink-3)}.error-text{color:var(--rose)!important}.history .row-main{cursor:default}@media(max-width:640px){.page-head{align-items:flex-start;flex-direction:column}.notification-row{align-items:flex-start;flex-direction:column}.row-actions{width:100%;justify-content:flex-end}}
</style>
