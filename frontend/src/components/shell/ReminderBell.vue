<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useReminderStore, DEFAULT_DEFER_HOURS } from '@/stores/reminderStore'
import { Bell, ChevronRight } from 'lucide-vue-next'

const router = useRouter()
const store = useReminderStore()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

function toggle() {
  open.value = !open.value
  // 面板打开时才补一次拉取：store.fetch 自带 60s 去抖，不会形成请求风暴
  if (open.value) store.fetch()
}

function close() {
  open.value = false
}

function onDocClick(event: MouseEvent) {
  if (!open.value) return
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) close()
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') close()
}

function go(item: any) {
  const target = item?.action
  if (!target?.route) return
  close()
  router.push({ path: target.route, query: target.query || {} })
}

function goPrimary() {
  const target = store.primary?.start
  if (!target?.route) return
  close()
  router.push({ path: target.route, query: target.query || {} })
}

function defer(item: any) {
  store.defer(item, DEFAULT_DEFER_HOURS)
}

onMounted(() => document.addEventListener('click', onDocClick, true))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick, true))
</script>

<template>
  <div ref="rootRef" class="reminder-bell">
    <button
      type="button"
      class="bell-btn"
      :class="{ 'bell-btn--active': open }"
      :aria-expanded="open ? 'true' : 'false'"
      aria-haspopup="true"
      aria-label="复习提醒"
      :title="store.badge ? `${store.badge} 条复习提醒` : '复习提醒'"
      @click="toggle"
      @keydown="onKeydown"
    >
      <Bell :size="16" :stroke-width="1.75" aria-hidden="true" />
      <span v-if="store.badge" class="bell-count">{{ store.badge > 99 ? '99+' : store.badge }}</span>
    </button>

    <div v-if="open" class="bell-panel" role="region" aria-label="复习到期提醒">
      <header class="panel-head">
        <span class="panel-title">复习提醒</span>
        <span v-if="store.loading" class="panel-state">加载中…</span>
        <span v-else-if="store.lastError" class="panel-state panel-state--warn">{{ store.lastError }}</span>
      </header>

      <button
        v-if="store.primary && store.primary.start"
        type="button"
        class="panel-primary"
        @click="goPrimary"
      >
        <span class="panel-primary__label">今日主任务</span>
        <span class="panel-primary__title">{{ store.primary.title }}</span>
        <ChevronRight :size="15" :stroke-width="1.75" aria-hidden="true" />
      </button>

      <p v-if="store.hasData && store.urgent.length === 0 && store.upcoming.length === 0" class="panel-empty">
        暂时没有到期的复习，去安心做新的题吧。
      </p>

      <ul v-if="store.urgent.length" class="panel-list">
        <li v-for="item in store.urgent" :key="item.key" class="panel-row">
          <button type="button" class="row-main" @click="go(item)">
            <span class="row-title">{{ item.title }}</span>
            <span class="row-hint" :class="`row-hint--${item.bucket}`">{{ item.hint }}</span>
          </button>
          <button
            type="button"
            class="row-defer"
            :disabled="!item.can_defer || !!store.deferring"
            :title="item.can_defer ? `延后 ${DEFAULT_DEFER_HOURS} 小时提醒` : item.defer_disabled_reason"
            @click="defer(item)"
          >
            {{ store.deferring === item.key ? '处理中…' : '稍后提醒' }}
          </button>
        </li>
      </ul>

      <div v-if="store.upcoming.length" class="panel-group">
        <span class="panel-group__label">即将到期</span>
        <ul class="panel-list">
          <li v-for="item in store.upcoming" :key="item.key" class="panel-row panel-row--soft">
            <button type="button" class="row-main" @click="go(item)">
              <span class="row-title">{{ item.title }}</span>
              <span class="row-hint row-hint--upcoming">{{ item.hint }}</span>
            </button>
          </li>
        </ul>
      </div>

      <footer v-if="store.counts.total" class="panel-foot">
        <span>逾期 {{ store.counts.overdue }} · 今日 {{ store.counts.today }} · 即将 {{ store.counts.upcoming }}</span>
        <RouterLink to="/error-book" @click="close">错题本</RouterLink>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.reminder-bell { position: relative; }

.bell-btn {
  position: relative;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-s);
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--ink-2);
  transition: color .16s, border-color .16s;
}
.bell-btn:hover,
.bell-btn--active {
  color: var(--ink-1);
  border-color: var(--border-strong);
}
.bell-count {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  display: grid;
  place-items: center;
  border-radius: var(--r-pill);
  background: var(--rose);
  color: #fff;
  font-size: 10.5px;
  font-weight: 700;
  line-height: 1;
}

.bell-panel {
  position: absolute;
  top: calc(100% + 10px);
  right: 0;
  width: 320px;
  max-height: min(70vh, 520px);
  overflow-y: auto;
  padding: var(--space-3);
  display: grid;
  gap: var(--space-2);
  border: 1px solid var(--border-strong);
  border-radius: var(--r-m);
  background: var(--surface);
  box-shadow: var(--shadow-3);
  /* 顶栏自身是 z-topbar 的堆叠上下文，面板只需在其内部抬高一档 */
  z-index: 1;
}

.panel-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
.panel-title { font-size: var(--type-md); font-weight: 600; color: var(--ink-1); }
.panel-state { font-size: var(--type-xs); color: var(--ink-3); }
.panel-state--warn { color: var(--amber); }

.panel-primary {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--r-s);
  background: var(--brand-soft);
  color: var(--brand-text);
  text-align: left;
}
.panel-primary__label { font-size: 11px; font-weight: 700; letter-spacing: .02em; flex: none; }
.panel-primary__title { flex: 1; min-width: 0; font-size: var(--type-sm); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.panel-empty { font-size: var(--type-sm); color: var(--ink-3); padding: var(--space-2) 0; }

.panel-list { list-style: none; display: grid; gap: 2px; }
.panel-row { display: flex; align-items: center; gap: var(--space-1); }
.panel-row--soft .row-title { color: var(--ink-2); }

.row-main {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 1px;
  padding: 6px var(--space-2);
  border-radius: var(--r-s);
  text-align: left;
}
.row-main:hover { background: var(--surface-2); }
.row-title {
  font-size: var(--type-sm);
  color: var(--ink-1);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.row-hint { font-size: 11.5px; color: var(--ink-3); }
.row-hint--overdue { color: var(--rose); }
.row-hint--today { color: var(--amber); }

.row-defer {
  flex: none;
  padding: 5px 9px;
  border-radius: var(--r-pill);
  border: 1px solid var(--border);
  font-size: 11.5px;
  color: var(--ink-2);
  background: var(--surface);
}
.row-defer:hover:not(:disabled) { border-color: var(--border-strong); color: var(--ink-1); }
/* 错题级排期没有 deferred_until 字段：按钮禁用并在 title 里说明原因，而不是假装能点 */
.row-defer:disabled { opacity: .45; cursor: not-allowed; }

.panel-group { display: grid; gap: 2px; }
.panel-group__label { font-size: 11px; color: var(--ink-3); padding: 0 var(--space-2); }

.panel-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding-top: var(--space-2);
  border-top: 1px solid var(--border);
  font-size: 11.5px;
  color: var(--ink-3);
}
.panel-foot a { color: var(--brand-text); }
</style>
