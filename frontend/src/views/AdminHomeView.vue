<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import AdminShell from '@/components/shell/AdminShell.vue'
import { adminOverviewApi, unwrapOverview } from '@/api/adminOverview'

const router = useRouter()
const loading = ref(true)
const error = ref('')
const overview = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    overview.value = unwrapOverview(await adminOverviewApi.get())
  } catch (err) {
    error.value = err?.message || '概览加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <AdminShell>
    <main class="admin-home">
      <div class="admin-home__intro">
        <div>
          <p class="eyebrow">内容治理与运行状态</p>
          <h2>欢迎进入管理后台</h2>
          <p>从这里导入题库、审核题目并查看系统整体状态。</p>
        </div>
        <button class="refresh" type="button" :disabled="loading" @click="load">{{ loading ? '读取中…' : '刷新概览' }}</button>
      </div>

      <p v-if="error" class="alert" role="alert">{{ error }}</p>
      <p v-if="loading && !overview" class="state" role="status">正在读取系统概览…</p>

      <template v-if="overview">
        <section class="stat-grid" aria-label="系统概览">
          <article class="stat-card"><span>用户总数</span><strong>{{ overview.users?.total ?? 0 }}</strong><small>活跃 {{ overview.users?.active ?? 0 }}</small></article>
          <article class="stat-card"><span>学生账号</span><strong>{{ overview.users?.students ?? 0 }}</strong><small>管理员 {{ overview.users?.admins ?? 0 }}</small></article>
          <article class="stat-card"><span>已发布题目</span><strong>{{ overview.question_bank?.published ?? 0 }}</strong><small>待审核 {{ overview.question_bank?.draft ?? 0 }}</small></article>
          <article class="stat-card"><span>学习事件</span><strong>{{ overview.learning?.learning_events ?? 0 }}</strong><small>活跃学习者 {{ overview.learning?.active_learners ?? 0 }}</small></article>
        </section>

        <section class="action-grid" aria-label="管理员操作">
          <button class="action-card action-card--primary" type="button" @click="router.push('/admin/review')">
            <strong>导入题库</strong><span>上传 PDF，解析候选题并进入审核流程</span>
          </button>
          <button class="action-card" type="button" @click="router.push('/admin/review')">
            <strong>审核与发布题目</strong><span>编辑、分析、审核并发布正式题目</span>
          </button>
          <button class="action-card" type="button" @click="router.push('/admin/papers')">
            <strong>组卷工作台</strong><span>管理模板并生成正式试卷</span>
          </button>
          <button class="action-card" type="button" @click="router.push('/admin/readiness')">
            <strong>能力就绪度</strong><span>检查系统能力与配置状态</span>
          </button>
          <button class="action-card" type="button" @click="router.push('/admin/quality')">
            <strong>回答质量抽检</strong><span>处理脱敏的 Critic 抽检队列并记录判定</span>
          </button>
        </section>

        <section class="status-panel">
          <h3>题库与导入状态</h3>
          <div class="status-row"><span>草稿 / 已审核 / 已发布 / 已下架</span><strong>{{ overview.question_bank?.draft ?? 0 }} / {{ overview.question_bank?.reviewed ?? 0 }} / {{ overview.question_bank?.published ?? 0 }} / {{ overview.question_bank?.retired ?? 0 }}</strong></div>
          <div class="status-row"><span>导入批次</span><strong>{{ Object.values(overview.imports || {}).reduce((sum, value) => sum + Number(value || 0), 0) }}</strong></div>
        </section>
      </template>
    </main>
  </AdminShell>
</template>

<style scoped>
.admin-home { max-width: 1180px; margin: 0 auto; padding: clamp(22px, 4vw, 48px); }
.admin-home__intro { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 28px; }
.eyebrow { margin: 0 0 8px; color: var(--accent-text); font-size: 12px; }
h2 { margin: 0; font-size: clamp(24px, 4vw, 36px); }
.admin-home__intro p:last-child { margin: 8px 0 0; color: var(--ink-2); }
.refresh { padding: 9px 14px; border: 1px solid var(--border); border-radius: 8px; color: var(--ink-1); background: var(--surface); cursor: pointer; }
.refresh:disabled { opacity: .6; cursor: wait; }
.alert { padding: 12px 14px; border: 1px solid var(--rose); border-radius: 8px; color: var(--rose); background: var(--rose-soft); }
.state { color: var(--ink-2); }
.stat-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }
.stat-card, .status-panel { padding: 20px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
.stat-card span, .stat-card small { display: block; color: var(--ink-2); font-size: 13px; }
.stat-card strong { display: block; margin: 12px 0 6px; font-size: 30px; font-weight: 600; }
.stat-card small { color: var(--ink-3); }
.action-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin: 24px 0; }
.action-card { display: grid; gap: 8px; min-height: 122px; padding: 20px; border: 1px solid var(--border); border-radius: 12px; text-align: left; color: var(--ink-1); background: var(--surface); cursor: pointer; }
.action-card:hover { border-color: var(--accent); transform: translateY(-1px); }
.action-card strong { font-size: 17px; }
.action-card span { color: var(--ink-2); line-height: 1.5; }
.action-card--primary { border-color: var(--accent); background: var(--accent-soft, var(--surface)); }
.status-panel h3 { margin: 0 0 12px; }
.status-row { display: flex; justify-content: space-between; gap: 16px; padding: 12px 0; border-top: 1px solid var(--border); color: var(--ink-2); }
.status-row strong { color: var(--ink-1); }
@media (max-width: 760px) { .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .admin-home__intro { display: block; } .refresh { margin-top: 16px; } }
@media (max-width: 480px) { .admin-home { padding: 20px 16px; } .action-grid { grid-template-columns: 1fr; } }
</style>
