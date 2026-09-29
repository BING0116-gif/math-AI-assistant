<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUiStore } from '@/stores/uiStore'
import { useChatStore } from '@/stores/chatStore'
import { useAuthStore } from '@/stores/authStore'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { useLearningActivity } from '@/composables/useLearningActivity'
import {
  Plus, Search, LayoutDashboard, UserRound, Network, FileText, Target, BookX,
  PanelLeftClose, PanelLeftOpen, Sun, Moon, Menu, X, Trash2,
} from 'lucide-vue-next'
import { formatRelativeTime } from '@/utils/dateTime'

const router = useRouter()
const route = useRoute()
const ui = useUiStore()
const chatStore = useChatStore()
const authStore = useAuthStore()
const errorBookStore = useErrorBookStore()
useLearningActivity()

const searchQuery = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)

// navItems 数据结构不变(6 项);icon 值对应 lucide 组件(§6.4)
const navItems = [
  { to: '/dashboard', label: '学习看板', icon: LayoutDashboard },
  { to: '/profile', label: '记忆画像', icon: UserRound },
  { to: '/knowledge', label: '知识星球', icon: Network },
  { to: '/notes', label: '智能笔记', icon: FileText },
  { to: '/apply', label: '学以致用', icon: Target },
  { to: '/error-book', label: '错题复盘', icon: BookX },
]

const filteredChats = computed(() => {
  if (!searchQuery.value) return chatStore.sortedChats
  const q = searchQuery.value.toLowerCase()
  return chatStore.sortedChats.filter(c =>
    c.title?.toLowerCase().includes(q)
  )
})

// 错题待复盘计数:仅当本地已有数据时展示(不在此触发拉取)
const pendingReviewCount = computed(() => {
  const n = errorBookStore.unmasteredCount
  return n > 0 ? n : null
})

const userInitial = computed(() => {
  const name = authStore.username || '同'
  return name.slice(0, 1).toUpperCase()
})

const userRoleLabel = computed(() =>
  authStore.role === 'admin' ? '管理员' : '学生'
)

const isDark = computed(() => {
  const t = ui.theme
  if (t === 'system') {
    return typeof window !== 'undefined'
      && window.matchMedia('(prefers-color-scheme: dark)').matches
  }
  return t === 'dark'
})

const themeLabel = computed(() => {
  if (ui.theme === 'system') return '跟随系统'
  return isDark.value ? '深色模式' : '浅色模式'
})

function isActive(to: string) {
  if (to === '/') return route.path === '/'
  return route.path === to || route.path.startsWith(to + '/')
}

function startNewChat() {
  chatStore.createNewChat()
  router.push('/')
}

function openChat(chatId: string) {
  chatStore.switchChat(chatId)
  router.push(`/chat/${chatId}`)
}

function deleteChat(e: MouseEvent, chatId: string) {
  e.stopPropagation()
  chatStore.deleteChat(chatId)
}

function recentTime(chat: { lastMessageTime?: string }): string {
  if (!chat.lastMessageTime) return ''
  try {
    return formatRelativeTime(chat.lastMessageTime)
  } catch {
    return ''
  }
}

function focusSearch() {
  if (window.innerWidth <= 768) {
    ui.mobileDrawerOpen = true
    return
  }
  if (ui.sidebarCollapsed) ui.sidebarCollapsed = false
  requestAnimationFrame(() => searchInputRef.value?.focus())
}

function onKeydown(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    focusSearch()
  }
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="app-shell">
    <!-- 跳过链接 -->
    <a class="skip-link" href="#main-content">跳到主要内容</a>

    <!-- 桌面侧栏 -->
    <aside
      class="sidebar"
      :class="{ 'sidebar--collapsed': ui.sidebarCollapsed }"
      aria-label="主导航"
    >
      <!-- 品牌 + 收起 -->
      <div class="side-top">
        <RouterLink to="/" class="brand" aria-label="知微 首页">
          <span class="brand-mark" aria-hidden="true">∑</span>
          <span v-if="!ui.sidebarCollapsed" class="brand-name">
            知微<small>MATH&nbsp;AI&nbsp;ASSISTANT</small>
          </span>
        </RouterLink>
        <button
          class="icon-btn"
          :aria-label="ui.sidebarCollapsed ? '展开侧栏' : '收起侧栏'"
          :title="ui.sidebarCollapsed ? '展开侧栏' : '收起侧栏'"
          @click="ui.toggleSidebar()"
        >
          <PanelLeftOpen v-if="ui.sidebarCollapsed" :size="15" :stroke-width="1.75" />
          <PanelLeftClose v-else :size="15" :stroke-width="1.75" />
        </button>
      </div>

      <!-- 新对话主按钮 -->
      <button class="btn btn-primary btn-block sidebar-new-chat" @click="startNewChat">
        <Plus :size="15" :stroke-width="2" />
        <span v-if="!ui.sidebarCollapsed">新对话</span>
      </button>

      <!-- 搜索 -->
      <div v-if="!ui.sidebarCollapsed" class="side-search">
        <Search :size="14" :stroke-width="1.75" aria-hidden="true" />
        <input
          ref="searchInputRef"
          v-model="searchQuery"
          type="search"
          placeholder="搜索对话"
          aria-label="搜索对话历史"
        >
        <kbd>Ctrl K</kbd>
      </div>

      <!-- 主导航 -->
      <div v-if="!ui.sidebarCollapsed" class="nav-label">学习空间</div>
      <nav class="nav" aria-label="页面导航">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ 'nav-item--active': isActive(item.to) }"
          :aria-current="isActive(item.to) ? 'page' : undefined"
          :title="ui.sidebarCollapsed ? item.label : undefined"
        >
          <component :is="item.icon" :size="17" :stroke-width="1.75" aria-hidden="true" />
          <span v-if="!ui.sidebarCollapsed" class="nav-item__label">{{ item.label }}</span>
          <span
            v-if="!ui.sidebarCollapsed && item.to === '/error-book' && pendingReviewCount"
            class="count"
          >{{ pendingReviewCount }}</span>
        </RouterLink>
      </nav>

      <!-- 最近对话 -->
      <div v-if="!ui.sidebarCollapsed" class="recent">
        <div class="nav-label">最近对话</div>
        <div class="recent-list">
          <div
            v-for="chat in filteredChats"
            :key="chat.id"
            class="recent-item"
            :class="{ 'recent-item--active': chat.id === chatStore.currentChatId }"
            role="button"
            tabindex="0"
            @click="openChat(chat.id)"
            @keydown.enter="openChat(chat.id)"
          >
            <span class="rt">{{ chat.title || '新对话' }}</span>
            <span class="rs">{{ recentTime(chat) }}</span>
            <button
              class="recent-del"
              :aria-label="`删除 ${chat.title || '对话'}`"
              @click="(e) => deleteChat(e, chat.id)"
            >
              <Trash2 :size="12" :stroke-width="1.75" />
            </button>
          </div>
          <p v-if="filteredChats.length === 0" class="recent-empty">
            {{ searchQuery ? '未找到匹配的对话' : '还没有对话记录' }}
          </p>
        </div>
      </div>

      <!-- 底部:主题行 + 用户卡 -->
      <div class="side-foot">
        <div class="theme-row">
          <span class="caption">{{ themeLabel }}</span>
          <button class="icon-btn" aria-label="切换主题" @click="ui.toggleTheme()">
            <Moon v-if="!isDark" :size="15" :stroke-width="1.75" />
            <Sun v-else :size="15" :stroke-width="1.75" />
          </button>
        </div>
        <RouterLink to="/profile" class="user-chip" aria-label="个人主页">
          <span class="avatar" aria-hidden="true">{{ userInitial }}</span>
          <span class="user-chip__meta">
            <b>{{ authStore.username || '同学' }}</b>
            <small>{{ userRoleLabel }}</small>
          </span>
        </RouterLink>
      </div>
    </aside>

    <!-- 主工作区 -->
    <div class="shell-main">
      <!-- 顶部栏 -->
      <header class="topbar">
        <button class="shell-menu-btn" aria-label="打开导航" @click="ui.mobileDrawerOpen = true">
          <Menu :size="18" :stroke-width="1.75" />
        </button>
        <div class="topbar__title">
          <slot name="topbar-title" />
        </div>
        <div class="topbar__actions">
          <slot name="topbar-actions" />
        </div>
      </header>

      <!-- 页面头部(可选插槽) -->
      <div v-if="$slots['page-header']" class="page-header">
        <slot name="page-header" />
      </div>

      <!-- 主内容 -->
      <main id="main-content" class="shell-content" tabindex="-1">
        <slot />
      </main>
    </div>

    <!-- 右侧检查器(可选) -->
    <aside
      v-if="ui.inspectorOpen && $slots.inspector"
      class="shell-inspector"
      aria-label="上下文检查器"
    >
      <div class="shell-inspector__head">
        <span class="shell-inspector__title">检查器</span>
        <button class="shell-inspector__close" aria-label="关闭检查器" @click="ui.toggleInspector()">
          <X :size="16" :stroke-width="1.75" />
        </button>
      </div>
      <slot name="inspector" />
    </aside>

    <!-- 移动端抽屉 -->
    <Teleport to="body">
      <div
        v-if="ui.mobileDrawerOpen"
        class="mobile-drawer-backdrop"
        @click="ui.mobileDrawerOpen = false"
      >
        <aside class="mobile-drawer" aria-label="移动端导航" role="dialog" aria-modal="true" @click.stop>
          <div class="mobile-drawer__head">
            <span class="brand">
              <span class="brand-mark" aria-hidden="true">∑</span>
              <span class="brand-name">知微<small>MATH&nbsp;AI&nbsp;ASSISTANT</small></span>
            </span>
            <button aria-label="关闭导航" @click="ui.mobileDrawerOpen = false">
              <X :size="20" :stroke-width="1.75" />
            </button>
          </div>
          <button class="btn btn-primary btn-block" @click="startNewChat(); ui.mobileDrawerOpen = false">
            <Plus :size="15" :stroke-width="2" /> 新对话
          </button>
          <RouterLink
            v-for="item in navItems"
            :key="item.to"
            :to="item.to"
            class="mobile-drawer__link"
            :class="{ 'mobile-drawer__link--active': isActive(item.to) }"
            @click="ui.mobileDrawerOpen = false"
          >
            <component :is="item.icon" :size="17" :stroke-width="1.75" />
            {{ item.label }}
          </RouterLink>
          <div class="mobile-drawer__foot">
            <button class="mobile-drawer__theme" aria-label="切换主题" @click="ui.toggleTheme()">
              <Moon v-if="!isDark" :size="15" :stroke-width="1.75" />
              <Sun v-else :size="15" :stroke-width="1.75" />
              {{ themeLabel }}
            </button>
          </div>
        </aside>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-width) 1fr;
  height: 100dvh;
  overflow: hidden;
  background: var(--bg);
  color: var(--ink-1);
}

.app-shell:has(.sidebar--collapsed) {
  grid-template-columns: var(--sidebar-collapsed) 1fr;
}

.skip-link {
  position: fixed;
  top: var(--space-2);
  left: var(--space-2);
  z-index: var(--z-toast);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--r-s);
  background: var(--brand);
  color: #fff;
  min-height: 44px;
  display: inline-flex;
  align-items: center;
  transform: translateY(-160%);
  transition: transform var(--dur-fast) var(--ease-standard);
}
.skip-link:focus {
  transform: translateY(0);
}

/* ============ 侧栏 ============ */
.sidebar {
  background: var(--side);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 18px 14px 14px;
  gap: 4px;
  min-height: 0;
  overflow: hidden;
  transition: width var(--dur-fast) var(--ease-standard);
}
.sidebar--collapsed {
  padding-inline: 10px;
}

/* ---- 品牌行 ---- */
.side-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 6px 14px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-weight: 700;
  font-size: 15.5px;
  letter-spacing: 0.01em;
  color: var(--ink-1);
  text-decoration: none;
}
.brand-mark {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  flex: none;
  background: linear-gradient(135deg, #17A98A 0%, #0B7A5E 55%, #08604A 100%);
  color: #fff;
  font-family: var(--font-disp);
  font-size: 17px;
  font-weight: 600;
  box-shadow: 0 2px 6px rgba(11, 122, 94, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.25);
}
.brand-name {
  display: block;
  line-height: 1.15;
}
.brand-name small {
  display: block;
  font-size: 10.5px;
  font-weight: 500;
  color: var(--ink-3);
  letter-spacing: 0.08em;
  line-height: 1.2;
}

/* ---- 新对话 ---- */
.sidebar-new-chat {
  margin-bottom: 2px;
}

/* ---- 搜索 ---- */
.side-search {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  padding: 0 10px;
  margin: 2px 0 10px;
  border: 1px solid var(--border);
  border-radius: 9px;
  color: var(--ink-3);
  font-size: 13px;
  background: var(--surface);
  box-shadow: var(--shadow-1);
}
.side-search input {
  flex: 1;
  min-width: 0;
  border: none;
  outline: none;
  background: transparent;
  color: var(--ink-1);
  font-size: 13px;
}
.side-search input::placeholder {
  color: var(--ink-3);
}
.side-search input::-webkit-search-cancel-button {
  display: none;
}
.side-search kbd {
  margin-left: auto;
  font-family: var(--font-ui);
  font-size: 11px;
  color: var(--ink-3);
  border: 1px solid var(--border);
  border-radius: 5px;
  padding: 1px 5px;
  background: var(--surface-2);
}

/* ---- 导航 ---- */
.nav-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--ink-3);
  letter-spacing: 0.06em;
  padding: 12px 10px 6px;
}
.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 36px;
  padding: 0 10px;
  border-radius: 9px;
  font-size: 13.5px;
  font-weight: 500;
  color: var(--ink-2);
  transition: all 0.15s;
  position: relative;
  text-decoration: none;
  min-height: 36px;
}
.nav-item:hover {
  background: var(--brand-soft);
  color: var(--ink-1);
}
.nav-item--active {
  background: var(--brand-soft-2);
  color: var(--brand-text);
  font-weight: 600;
}
.nav-item .count {
  margin-left: auto;
  font-size: 11px;
  font-weight: 600;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  display: grid;
  place-items: center;
  border-radius: var(--r-pill);
  background: var(--rose-soft);
  color: var(--rose);
}

/* ---- 最近对话 ---- */
.recent {
  display: flex;
  flex-direction: column;
  min-height: 0;
  flex: 1;
}
.recent-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.recent-item {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 7px 26px 7px 10px;
  border-radius: 9px;
  cursor: pointer;
  transition: background 0.15s;
}
.recent-item:hover {
  background: var(--brand-soft);
}
.recent-item--active {
  background: var(--brand-soft-2);
}
.recent-item .rt {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--ink-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.recent-item--active .rt {
  color: var(--brand-text);
}
.recent-item .rs {
  font-size: 11.5px;
  color: var(--ink-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}
.recent-del {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 20px;
  height: 20px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: var(--ink-3);
  opacity: 0;
  transition: opacity 0.15s, background 0.15s, color 0.15s;
}
.recent-item:hover .recent-del,
.recent-del:focus-visible {
  opacity: 1;
}
.recent-del:hover {
  background: var(--rose-soft);
  color: var(--rose);
}
.recent-empty {
  color: var(--ink-3);
  font-size: 12px;
  padding: 8px 10px;
}

/* ---- 底部 ---- */
.side-foot {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-top: 10px;
}
.theme-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 6px;
}
.user-chip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--r-m);
  border: 1px solid var(--border);
  background: var(--surface);
  box-shadow: var(--shadow-1);
  text-decoration: none;
  color: var(--ink-1);
  transition: border-color 0.15s;
}
.user-chip:hover {
  border-color: var(--brand);
}
.user-chip__meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.3;
}
.user-chip__meta b {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.user-chip__meta small {
  font-size: 11px;
  color: var(--ink-3);
}
.avatar {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  flex: none;
  background: linear-gradient(135deg, #17A98A, #08604A);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

/* ============ 主工作区 ============ */
.shell-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100dvh;
  overflow: hidden;
  background: var(--bg);
}

.topbar {
  height: var(--topbar-height);
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 28px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  backdrop-filter: blur(8px);
  z-index: var(--z-topbar);
}
.topbar__title {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-1);
  display: flex;
  align-items: center;
  gap: 7px;
}
.topbar__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.shell-menu-btn {
  display: none;
  width: 44px;
  height: 44px;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: var(--r-s);
  background: none;
  cursor: pointer;
  color: var(--ink-1);
}

.page-header {
  flex: none;
  padding: var(--space-4) 28px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-soft);
}

.shell-content {
  flex: 1;
  /* min-height:0 允许 flex 子项收缩到内容高度以下(聊天页内滚的前提);
     长内容页面在此容器内滚动。 */
  min-height: 0;
  overflow-y: auto;
  outline: none;
  display: flex;
  flex-direction: column;
  position: relative;
}

/* ============ 检查器 ============ */
.shell-inspector {
  width: var(--inspector-width);
  flex: 0 0 var(--inspector-width);
  border-left: 1px solid var(--border);
  background: var(--surface);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.shell-inspector__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--border);
}
.shell-inspector__title {
  font-size: 13px;
  font-weight: 600;
}
.shell-inspector__close {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--r-s);
  color: var(--ink-2);
  background: none;
  border: none;
  cursor: pointer;
}
.shell-inspector__close:hover {
  background: var(--surface-2);
}

/* ============ 移动端抽屉 ============ */
.mobile-drawer-backdrop {
  display: none;
  position: fixed;
  inset: 0;
  z-index: var(--z-drawer-mask);
  background: rgba(9, 11, 15, 0.5);
}
.mobile-drawer {
  position: absolute;
  left: 0;
  top: 0;
  width: min(320px, 86vw);
  height: 100%;
  padding: var(--space-5) var(--space-4);
  background: var(--side);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  box-shadow: var(--shadow-3);
  overflow-y: auto;
}
.mobile-drawer__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}
.mobile-drawer__head button {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: var(--r-s);
  background: none;
  border: none;
  cursor: pointer;
  color: var(--ink-2);
}
.mobile-drawer__link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px var(--space-2);
  border-radius: var(--r-s);
  color: var(--ink-2);
  font-size: 14px;
  font-weight: 500;
  text-decoration: none;
  transition: background var(--dur-fast);
  min-height: 44px;
}
.mobile-drawer__link:hover {
  background: var(--brand-soft);
}
.mobile-drawer__link--active {
  background: var(--brand-soft-2);
  color: var(--brand-text);
}
.mobile-drawer__foot {
  margin-top: auto;
  border-top: 1px solid var(--border);
  padding-top: var(--space-3);
}
.mobile-drawer__theme {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px var(--space-2);
  border-radius: var(--r-s);
  color: var(--ink-2);
  font-size: 14px;
  min-height: 44px;
  width: 100%;
}

/* ============ 响应式 ============ */
/* ≤1279px:侧栏收窄为 rail(68px) */
@media (max-width: 1279px) and (min-width: 769px) {
  .app-shell:not(:has(.sidebar--collapsed)) {
    grid-template-columns: var(--sidebar-collapsed) 1fr;
  }
  .sidebar:not(.sidebar--collapsed) {
    padding-inline: 10px;
  }
  .sidebar .side-top,
  .sidebar .btn span,
  .sidebar .side-search,
  .sidebar .nav-label,
  .sidebar .nav-item__label,
  .sidebar .nav-item .count,
  .sidebar .recent,
  .sidebar .theme-row .caption,
  .sidebar .user-chip__meta {
    display: none;
  }
  .sidebar .side-top {
    flex-direction: column;
    gap: 8px;
    padding-bottom: 10px;
  }
  .sidebar .nav-item {
    justify-content: center;
    padding: 0;
  }
  .sidebar .side-foot {
    align-items: center;
  }
}

/* ≤768px:侧栏隐藏,汉堡 + 抽屉,topbar 52px */
@media (max-width: 768px) {
  .app-shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    display: none;
  }
  .shell-menu-btn {
    display: grid;
  }
  .topbar {
    height: var(--topbar-height-mobile);
    padding: 0 var(--space-4);
  }
  .page-header {
    padding: var(--space-3) var(--space-4);
  }
  .mobile-drawer-backdrop {
    display: block;
  }
  .shell-inspector {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .sidebar,
  .nav-item,
  .recent-item,
  .recent-del,
  .skip-link {
    transition: none;
  }
}
</style>
