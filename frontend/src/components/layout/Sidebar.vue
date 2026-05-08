<template>
  <aside class="sidebar" :class="{ collapsed }">
    <div class="sidebar-inner">
      <div class="sidebar-top">
        <div class="brand">
          <div class="brand-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
              <line x1="8" y1="7" x2="16" y2="7"/>
              <line x1="8" y1="11" x2="14" y2="11"/>
            </svg>
          </div>
          <div class="brand-text">
            <h1>数学AI助手</h1>
            <span>你的智能数学学习伙伴</span>
          </div>
        </div>
      </div>

      <div class="sidebar-actions">
        <button class="btn-new-chat" @click="handleNewChat">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          新对话
        </button>
      </div>

      <div class="history-section">
        <h3 class="section-label">历史对话</h3>
        <div class="history-list" ref="historyListRef">
          <TransitionGroup name="list">
            <div
              v-for="chat in store.sortedChats"
              :key="chat.id"
              class="history-item"
              :class="{ active: chat.id === store.currentChatId }"
              @click="store.switchChat(chat.id)"
              @contextmenu.prevent="showContextMenu($event, chat)"
            >
              <div class="history-item-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>
                </svg>
              </div>
              <div class="history-item-text">
                <span class="history-title">{{ chat.title }}</span>
                <span class="history-time">{{ chat.lastMessageTime }}</span>
              </div>
            </div>
          </TransitionGroup>
          <div v-if="store.chats.length === 0" class="empty-hint">暂无对话记录</div>
        </div>
      </div>

      <div class="sidebar-footer">
        <router-link to="/error-book" class="btn-error-book">
          <span class="eb-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M4 19.5A2.5 2.5 0 016.5 17H20"/>
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/>
            </svg>
          </span>
          错题本
        </router-link>
      </div>
    </div>

    <Teleport to="body">
      <div
        v-if="contextMenu.visible"
        class="context-overlay"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
      >
        <div class="ctx-item" @click.stop="handleRename">
          <span>✏️</span> 重命名
        </div>
        <div class="ctx-item danger" @click.stop="handleDelete">
          <span>🗑️</span> 删除对话
        </div>
      </div>
    </Teleport>
  </aside>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chatStore'

const props = defineProps({ collapsed: Boolean })
const emit = defineEmits(['toggle'])

const store = useChatStore()

const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  chatId: null
})

function showContextMenu(event, chat) {
  const menuW = 140, menuH = 80
  let x = event.clientX
  let y = event.clientY
  if (x + menuW > window.innerWidth) x -= menuW
  if (y + menuH > window.innerHeight) y -= menuH
  contextMenu.x = x
  contextMenu.y = y
  contextMenu.chatId = chat.id
  contextMenu.visible = true
}

function hideContextMenu() {
  contextMenu.visible = false
}

function handleRename() {
  hideContextMenu()
  const title = prompt('请输入新的对话名称:')
  if (title?.trim()) {
    store.renameChat(contextMenu.chatId, title.trim())
  }
}

function handleDelete() {
  hideContextMenu()
  const chat = store.chats.find(c => c.id === contextMenu.chatId)
  if (chat && confirm(`确定要删除对话「${chat.title}」吗？此操作不可恢复。`)) {
    store.deleteChat(contextMenu.chatId)
  }
}

function handleNewChat() {
  store.createNewChat()
}

function onDocumentClick() {
  hideContextMenu()
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  width: $sidebar-width;
  height: 100vh;
  background: $bg-sidebar;
  border-right: 1px solid $border-color;
  z-index: 100;
  transform: translateX(0);
  transition: transform $transition-slow;
  display: flex;
  flex-direction: column;

  &.collapsed {
    transform: translateX(-100%);
  }
}

.sidebar-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.sidebar-top {
  padding: 24px 20px 16px;
  border-bottom: 1px solid $border-light;
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-icon {
  width: 42px;
  height: 42px;
  background: linear-gradient(135deg, $primary 0%, $primary-light 100%);
  border-radius: $radius-md;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
}

.brand-text h1 {
  font-size: 17px;
  font-weight: 700;
  color: $text-primary;
  line-height: 1.3;
}

.brand-text span {
  font-size: 12px;
  color: $text-tertiary;
  display: block;
  margin-top: 1px;
}

.sidebar-actions {
  padding: 14px 16px;
  flex-shrink: 0;
}

.btn-new-chat {
  width: 100%;
  padding: 11px 16px;
  border: 1px dashed $border-color;
  border-radius: $radius-md;
  background: $bg-tertiary;
  color: $text-secondary;
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: all $transition-fast;

  &:hover {
    background: $primary-bg;
    border-color: $primary;
    color: $primary;
    border-style: solid;
  }
}

.history-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0 12px;
}

.section-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: $text-tertiary;
  padding: 8px 12px 10px;
  font-weight: 600;
  flex-shrink: 0;
}

.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 4px;
  position: relative;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  border-radius: $radius-md;
  cursor: pointer;
  transition: all $transition-fast;
  margin-bottom: 2px;

  &:hover {
    background: $bg-tertiary;
  }

  &.active {
    background: $primary-bg;
    .history-item-icon { color: $primary; }
    .history-title { color: $primary-dark; font-weight: 600; }
  }
}

.history-item-icon {
  color: $text-tertiary;
  flex-shrink: 0;
  display: flex;
}

.history-item-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-title {
  font-size: 13.5px;
  color: $text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-time {
  font-size: 11px;
  color: $text-tertiary;
}

.empty-hint {
  text-align: center;
  color: $text-tertiary;
  font-size: 13px;
  padding: 30px 0;
}

.sidebar-footer {
  padding: 14px 16px;
  border-top: 1px solid $border-light;
  flex-shrink: 0;
}

.btn-error-book {
  width: 100%;
  padding: 12px 16px;
  background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%);
  border: 1px solid #fed7aa;
  border-radius: $radius-md;
  color: #c2410c;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: all $transition-fast;

  &:hover {
    background: linear-gradient(135deg, #ffedd5 0%, #fed7aa 100%);
    transform: translateY(-1px);
    box-shadow: 0 2px 8px rgba(234, 88, 12, 0.15);
  }
}

.context-overlay {
  position: fixed;
  z-index: 9999;
  background: white;
  border: 1px solid $border-color;
  border-radius: $radius-md;
  box-shadow: $shadow-xl;
  min-width: 140px;
  padding: 4px 0;
  animation: ctxIn 0.2s ease;
}

@keyframes ctxIn {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}

.ctx-item {
  padding: 9px 18px;
  font-size: 13.5px;
  color: $text-primary;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: background $transition-fast;

  &:hover { background: $bg-tertiary; }
  &.danger { color: $danger;
    &:hover { background: $danger-light; }
  }
}

.sidebar-footer a { text-decoration: none; }

@media (max-width: 768px) {
  .sidebar {
    width: 260px;
    box-shadow: $shadow-xl;
  }
}
</style>
