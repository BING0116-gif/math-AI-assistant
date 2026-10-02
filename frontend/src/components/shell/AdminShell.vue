<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const items = [
  { to: '/admin', label: '后台概览' },
  { to: '/admin/review', label: '题库导入与审核' },
  { to: '/admin/papers', label: '组卷工作台' },
  { to: '/admin/readiness', label: '能力就绪度' },
  { to: '/admin/agent-metrics', label: 'Agent 指标' },
]

const activeLabel = computed(() => items.find((item) => route.path === item.to)?.label || '管理后台')

function isActive(to) {
  return to === '/admin' ? route.path === to : route.path === to || route.path.startsWith(`${to}/`)
}
</script>

<template>
  <div class="admin-shell">
    <aside class="admin-shell__side" aria-label="管理员导航">
      <RouterLink class="admin-shell__brand" to="/admin">
        <span class="admin-shell__mark">∑</span>
        <span><strong>知微</strong><small>管理后台</small></span>
      </RouterLink>
      <div class="admin-shell__caption">内容与系统</div>
      <nav class="admin-shell__nav">
        <RouterLink
          v-for="item in items"
          :key="item.to"
          :to="item.to"
          class="admin-shell__link"
          :class="{ 'is-active': isActive(item.to) }"
          :aria-current="isActive(item.to) ? 'page' : undefined"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
      <div class="admin-shell__foot">
        <span class="admin-shell__identity">{{ authStore.username || '管理员' }}</span>
        <button type="button" class="admin-shell__student-link" @click="router.push('/')">返回学生端</button>
      </div>
    </aside>
    <main class="admin-shell__main">
      <header class="admin-shell__topbar">
        <span class="admin-shell__eyebrow">ADMIN CONSOLE</span>
        <h1>{{ activeLabel }}</h1>
      </header>
      <section class="admin-shell__content">
        <slot />
      </section>
    </main>
  </div>
</template>

<style scoped>
.admin-shell { min-height: 100vh; display: flex; background: var(--bg); color: var(--ink-1); }
.admin-shell__side { width: 230px; flex: 0 0 230px; display: flex; flex-direction: column; padding: 22px 14px; background: var(--side); border-right: 1px solid var(--border); }
.admin-shell__brand { display: flex; align-items: center; gap: 10px; padding: 4px 10px 26px; color: inherit; text-decoration: none; }
.admin-shell__brand strong, .admin-shell__brand small { display: block; }
.admin-shell__brand small { margin-top: 2px; color: var(--ink-3); font-size: 11px; }
.admin-shell__mark { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 9px; color: #fff; background: var(--accent); }
.admin-shell__caption { padding: 0 10px 8px; color: var(--ink-3); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.admin-shell__nav { display: grid; gap: 4px; }
.admin-shell__link { padding: 11px 10px; border-radius: 8px; color: var(--ink-2); text-decoration: none; font-size: 14px; }
.admin-shell__link:hover, .admin-shell__link.is-active { color: var(--ink-1); background: var(--surface-2); }
.admin-shell__link.is-active { font-weight: 600; box-shadow: inset 3px 0 var(--accent); }
.admin-shell__foot { margin-top: auto; display: grid; gap: 8px; padding: 16px 10px 0; border-top: 1px solid var(--border); }
.admin-shell__identity { color: var(--ink-2); font-size: 13px; }
.admin-shell__student-link { width: fit-content; padding: 0; border: 0; color: var(--accent-text); background: none; cursor: pointer; font: inherit; font-size: 13px; }
.admin-shell__main { flex: 1; min-width: 0; }
.admin-shell__topbar { padding: 22px clamp(20px, 4vw, 48px) 18px; border-bottom: 1px solid var(--border); background: var(--surface); }
.admin-shell__topbar h1 { margin: 4px 0 0; font-size: clamp(22px, 3vw, 30px); font-weight: 600; }
.admin-shell__eyebrow { color: var(--accent-text); font-size: 11px; letter-spacing: .12em; }
.admin-shell__content { min-width: 0; }
@media (max-width: 720px) {
  .admin-shell { display: block; }
  .admin-shell__side { width: auto; padding: 12px; border-right: 0; border-bottom: 1px solid var(--border); }
  .admin-shell__brand { padding-bottom: 12px; }
  .admin-shell__caption, .admin-shell__foot { display: none; }
  .admin-shell__nav { display: flex; overflow-x: auto; }
  .admin-shell__link { flex: 0 0 auto; white-space: nowrap; }
  .admin-shell__topbar { padding: 16px 18px; }
}
</style>
