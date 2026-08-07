<template>
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳到主要内容</a>

    <aside class="desktop-nav" :class="{ 'desktop-nav--collapsed': collapsed }" aria-label="主导航">
      <div class="nav-brand">
        <div class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/><path d="M9 8h7M9 12h5"/></svg></div>
        <div v-if="!collapsed" class="brand-copy"><strong>知微</strong><span>数学学习工作台</span></div>
      </div>

      <button class="new-question" type="button" :title="collapsed ? '新提问' : undefined" @click="createQuestion">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
        <span v-if="!collapsed">新提问</span>
      </button>

      <nav class="primary-links" aria-label="一级导航">
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="nav-link" :class="{ 'nav-link--active': isActive(item.to) }" :aria-current="isActive(item.to) ? 'page' : undefined" :title="collapsed ? item.label : undefined">
          <span class="nav-icon" aria-hidden="true"><component :is="item.icon" /></span><span v-if="!collapsed">{{ item.label }}</span>
        </RouterLink>
      </nav>

      <section v-if="!collapsed" class="history-panel" aria-labelledby="history-title">
        <h2 id="history-title">最近提问</h2>
        <RouterLink v-for="chat in recentChats" :key="chat.id" :to="`/chat/${chat.id}`" class="history-link">{{ chat.title }}</RouterLink>
        <p v-if="recentChats.length === 0" class="history-empty">还没有对话记录</p>
      </section>

      <div class="nav-footer">
        <ThemeToggle v-if="!collapsed" />
        <button class="collapse-control" type="button" :aria-label="collapsed ? '展开导航' : '收起导航'" @click="collapsed = !collapsed">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path :d="collapsed ? 'm9 18 6-6-6-6' : 'm15 18-6-6 6-6'"/></svg>
          <span v-if="!collapsed">收起导航</span>
        </button>
      </div>
    </aside>

    <div class="shell-column">
      <header class="app-topbar">
        <div class="topbar-leading"><button class="mobile-menu" type="button" aria-label="打开导航" @click="mobileOpen = true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg></button><div class="breadcrumbs"><span class="breadcrumb-section">{{ activeLabel }}</span><span v-if="headerTitle" class="breadcrumb-title">{{ headerTitle }}</span></div></div>
        <div class="topbar-actions"><slot name="actions" /><ThemeToggle /></div>
      </header>

      <div v-if="$slots.header" class="page-header"><slot name="header" /></div>
      <main id="main-content" ref="mainRef" class="main-content" tabindex="-1"><slot /></main>
    </div>

    <nav class="mobile-nav" aria-label="移动端主导航">
      <RouterLink v-for="item in mobileItems" :key="item.to" :to="item.to" class="mobile-nav__item" :class="{ 'mobile-nav__item--active': isActive(item.to) }" :aria-current="isActive(item.to) ? 'page' : undefined"><span class="nav-icon" aria-hidden="true"><component :is="item.icon" /></span><span>{{ item.label }}</span></RouterLink>
    </nav>

    <div v-if="mobileOpen" class="mobile-sheet-backdrop" @click.self="mobileOpen = false">
      <aside class="mobile-sheet" aria-label="移动端导航" aria-modal="true" role="dialog">
        <div class="mobile-sheet__head"><strong>知微</strong><button class="close-sheet" type="button" aria-label="关闭导航" @click="mobileOpen = false">×</button></div>
        <RouterLink v-for="item in navItems" :key="item.to" :to="item.to" class="mobile-sheet__link" @click="mobileOpen = false"><span class="nav-icon" aria-hidden="true"><component :is="item.icon" /></span>{{ item.label }}</RouterLink>
        <button class="mobile-sheet__link" type="button" @click="createQuestion(); mobileOpen = false"><span class="nav-icon" aria-hidden="true">＋</span>新提问</button>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, h, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chatStore'
import ThemeToggle from '@/components/common/ThemeToggle.vue'

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const collapsed = ref(false)
const mobileOpen = ref(false)
const mainRef = ref(null)

const icon = (paths) => () => h('svg', { viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.8 }, paths.map(d => h('path', { d })))
const navItems = [
  { to: '/', label: '今日', icon: icon(['M4 5h16v14H4z', 'M8 9h8M8 13h5']) },
  { to: '/chat', label: '提问', icon: icon(['M4 5h16v12H8l-4 3V5Z', 'M8 9h8M8 13h5']) },
  { to: '/knowledge', label: '课程', icon: icon(['M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z', 'M8 8h8M8 12h6']) },
  { to: '/error-book', label: '错题复盘', icon: icon(['M5 4h14v16H5z', 'M8 8h8M8 12h6M8 16h4']) }
]
const mobileItems = navItems
const recentChats = computed(() => chatStore.sortedChats.slice(0, 4))
const activeItem = computed(() => navItems.find(item => item.to === '/' ? route.path === '/' : route.path.startsWith(item.to)))
const activeLabel = computed(() => activeItem.value?.label || '数学学习')
const headerTitle = computed(() => route.meta.title?.replace(' - 数学AI助手', '').replace('数学AI助手', '') || '')

function isActive(to) { return to === '/' ? route.path === '/' : route.path === to || route.path.startsWith(`${to}/`) }
function createQuestion() { const chat = chatStore.createNewChat(); router.push(`/chat/${chat.id}`) }
watch(() => route.fullPath, async () => { await nextTick(); mainRef.value?.focus() })
</script>

<style scoped lang="scss">
.app-shell { min-height: 100dvh; display: flex; background: var(--color-canvas); color: var(--color-text); }
.skip-link { position: fixed; top: 8px; left: 8px; z-index: 2000; padding: 10px 14px; border-radius: 10px; color: var(--color-text-inverse); background: var(--color-action); transform: translateY(-160%); transition: transform 160ms ease-out; &:focus { transform: translateY(0); } }
.desktop-nav { width: 248px; flex: 0 0 248px; min-height: 100dvh; display: flex; flex-direction: column; gap: 18px; padding: 22px 16px 16px; background: var(--color-surface); border-right: 1px solid var(--color-border-subtle); transition: width 220ms ease-out, flex-basis 220ms ease-out, padding 220ms ease-out; &--collapsed { width: 72px; flex-basis: 72px; padding-inline: 12px; .nav-brand { justify-content: center; } .new-question { padding-inline: 0; } .nav-link { justify-content: center; padding-inline: 0; } .nav-footer { align-items: center; } } }
.nav-brand { min-height: 46px; display: flex; align-items: center; gap: 11px; padding-inline: 8px; }.brand-mark { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 10px; color: var(--color-text-inverse); background: var(--color-agent); svg { width: 22px; } }.brand-copy { display: grid; line-height: 1.15; strong { font-size: 17px; letter-spacing: .02em; } span { margin-top: 4px; color: var(--color-text-muted); font-size: 11px; } }
.new-question { min-height: 46px; display: flex; align-items: center; justify-content: center; gap: 9px; padding: 0 14px; border: 1px solid var(--color-action); border-radius: 10px; color: var(--color-text-inverse); background: var(--color-action); font-weight: 700; cursor: pointer; transition: transform 160ms ease-out, background-color 160ms ease-out; svg { width: 18px; } &:hover { background: var(--color-action-hover); transform: translateY(-1px); } }
.primary-links { display: grid; gap: 5px; }.nav-link { min-height: 46px; display: flex; align-items: center; gap: 12px; padding: 0 12px; border-radius: 10px; color: var(--color-text-muted); font-weight: 650; text-decoration: none; transition: color 160ms ease-out, background-color 160ms ease-out; &:hover { color: var(--color-text); background: var(--color-surface-muted); } &--active { color: var(--color-agent); background: var(--color-agent-soft); } }.nav-icon { width: 22px; height: 22px; flex: 0 0 22px; display: inline-grid; place-items: center; svg { width: 20px; height: 20px; } }
.history-panel { flex: 1; min-height: 0; padding: 18px 8px 0; border-top: 1px solid var(--color-border-subtle); overflow: auto; h2 { margin: 0 0 10px; color: var(--color-text-subtle); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; } }.history-link { display: block; overflow: hidden; padding: 8px 4px; color: var(--color-text-muted); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; &:hover { color: var(--color-agent); } }.history-empty { margin: 0; color: var(--color-text-subtle); font-size: 13px; }
.nav-footer { display: flex; flex-direction: column; gap: 10px; }.collapse-control { min-height: 44px; display: flex; align-items: center; justify-content: center; gap: 9px; border: 0; color: var(--color-text-muted); background: transparent; cursor: pointer; font-size: 13px; svg { width: 20px; } &:hover { color: var(--color-agent); } }
.shell-column { min-width: 0; min-height: 100dvh; flex: 1; display: flex; flex-direction: column; }.app-topbar { min-height: 68px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 0 28px; background: var(--bg-topbar); border-bottom: 1px solid var(--color-border-subtle); }.topbar-leading, .topbar-actions, .breadcrumbs { display: flex; align-items: center; }.topbar-leading { min-width: 0; gap: 14px; }.breadcrumbs { min-width: 0; gap: 10px; }.breadcrumb-section { color: var(--color-text); font-size: 14px; font-weight: 750; }.breadcrumb-title { overflow: hidden; color: var(--color-text-muted); font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }.breadcrumb-title::before { content: '/'; margin-right: 10px; color: var(--color-text-subtle); }.topbar-actions { gap: 10px; }.mobile-menu { display: none; width: 44px; height: 44px; border: 1px solid var(--color-border); border-radius: 10px; color: var(--color-text); background: var(--color-surface); svg { width: 20px; } }.page-header { min-height: 68px; display: flex; align-items: center; padding: 0 28px; border-bottom: 1px solid var(--color-border-subtle); background: var(--color-surface); }.main-content { min-width: 0; flex: 1; overflow: hidden; outline: none; }.mobile-nav, .mobile-sheet-backdrop { display: none; }
@media (max-width: 1279px) and (min-width: 769px) { .desktop-nav { width: 72px; flex-basis: 72px; padding-inline: 12px; .nav-brand { justify-content: center; } .new-question { padding-inline: 0; } .nav-link { justify-content: center; padding-inline: 0; } .nav-footer { align-items: center; } .history-panel, .brand-copy, .new-question span, .collapse-control span { display: none; } } .app-topbar { padding-inline: 22px; } }
@media (max-width: 768px) { .desktop-nav { display: none; } .app-topbar { min-height: 60px; padding: 0 14px; }.mobile-menu { display: inline-grid; place-items: center; }.page-header { min-height: 60px; padding: 0 14px; }.main-content { padding-bottom: 72px; overflow: auto; }.mobile-nav { position: fixed; right: 0; bottom: 0; left: 0; z-index: 100; height: 72px; display: grid; grid-template-columns: repeat(4, 1fr); padding: 7px 8px max(7px, env(safe-area-inset-bottom)); background: color-mix(in srgb, var(--color-surface) 96%, transparent); border-top: 1px solid var(--color-border); backdrop-filter: blur(16px); }.mobile-nav__item { min-width: 44px; min-height: 52px; display: grid; place-items: center; align-content: center; gap: 2px; border-radius: 10px; color: var(--color-text-muted); font-size: 11px; font-weight: 650; text-decoration: none; }.mobile-nav__item--active { color: var(--color-agent); background: var(--color-agent-soft); }.mobile-nav__item .nav-icon { width: 20px; height: 20px; }.mobile-sheet-backdrop { position: fixed; inset: 0; z-index: 500; display: block; background: var(--bg-overlay); }.mobile-sheet { width: min(320px, 86vw); height: 100%; padding: 20px 16px; background: var(--color-surface); box-shadow: var(--shadow-lg); }.mobile-sheet__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 22px; font-size: 20px; }.close-sheet { width: 44px; height: 44px; border: 0; border-radius: 10px; color: var(--color-text); background: transparent; font-size: 28px; cursor: pointer; }.mobile-sheet__link { min-height: 48px; width: 100%; display: flex; align-items: center; gap: 12px; padding: 0 12px; border: 0; border-radius: 10px; color: var(--color-text); background: transparent; font-weight: 650; text-decoration: none; text-align: left; cursor: pointer; &:hover { background: var(--color-surface-muted); } } }
@media (prefers-reduced-motion: reduce) { .desktop-nav, .app-button, .skip-link, .new-question, .nav-link { transition: none; } }
</style>
