<template>
  <aside class="sidebar" :class="{ collapsed }" role="navigation" aria-label="主导航">
    <div class="sidebar-inner">
      <div class="sidebar-top">
        <div class="brand">
          <div class="brand-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
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
        <div class="theme-toggle-wrapper">
          <ThemeToggle />
        </div>
      </div>

      <div class="sidebar-actions">
        <button class="btn-new-chat" @click="handleNewChat">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
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
              role="button"
              :tabindex="0"
              @keydown.enter="store.switchChat(chat.id)"
            >
              <div class="history-item-icon">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
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
        <router-link to="/knowledge" class="btn-error-book">
          <span class="eb-icon" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/><path d="M9 8h7M9 12h7M9 16h5"/></svg>
          </span>
          课程目录
        </router-link>
        <router-link to="/error-book" class="btn-error-book">
          <span class="eb-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
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
        role="menu"
      >
        <div class="ctx-item" @click.stop="handleRename" role="menuitem">
          <span class="ctx-glyph" aria-hidden="true">Aa</span> 重命名
        </div>
        <div class="ctx-item danger" @click.stop="handleDelete" role="menuitem">
          <span class="ctx-glyph" aria-hidden="true">×</span> 删除对话
        </div>
      </div>
    </Teleport>
  </aside>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chatStore'
import ThemeToggle from '@/components/common/ThemeToggle.vue'
import { ElMessageBox } from 'element-plus'

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
  ElMessageBox.prompt('请输入新的对话名称。', '重命名对话', { confirmButtonText: '保存', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '名称不能为空。' })
    .then(({ value }) => store.renameChat(contextMenu.chatId, value.trim()))
    .catch(() => {})
}

function handleDelete() {
  hideContextMenu()
  const chat = store.chats.find(c => c.id === contextMenu.chatId)
  if (!chat) return
  ElMessageBox.confirm(`确定要删除对话「${chat.title}」吗？此操作不可恢复。`, '删除对话', { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' })
    .then(() => store.deleteChat(contextMenu.chatId))
    .catch(() => {})
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
  background: var(--bg-sidebar);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-right: 1px solid var(--border-light);
  z-index: 100;
  transform: translateX(0);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-sm);

  &.collapsed {
    transform: translateX(-100%);
    opacity: 0;
  }
}

.sidebar-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.sidebar-top {
  padding: 28px 22px 18px;
  border-bottom: 1px solid var(--border-light);
  flex-shrink: 0;
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-icon {
  width: 46px;
  height: 46px;
  background: linear-gradient(135deg, var(--primary) 0%, var(--primary-hover) 100%);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
  box-shadow: var(--shadow-glow);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    transform: scale(1.08) rotate(-3deg);
    box-shadow: var(--shadow-glow);
  }
}

.brand-text h1 {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.3;
}

.brand-text span {
  font-size: 12px;
  color: var(--text-tertiary);
  display: block;
  margin-top: 2px;
  letter-spacing: 0.02em;
}

.theme-toggle-wrapper {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.sidebar-actions {
  padding: 16px 18px;
  flex-shrink: 0;
}

.btn-new-chat {
  width: 100%;
  padding: 13px 18px;
  border: 2px dashed var(--primary);
  border-radius: var(--radius-lg);
  background: var(--primary-ghost);
  color: var(--primary);
  font-size: 14px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    background: var(--primary-ghost);
    border-style: solid;
    border-color: var(--primary);
    transform: translateY(-2px);
    box-shadow: var(--shadow-glow);
  }

  &:active {
    transform: translateY(0);
  }

  svg {
    transition: transform 0.3s ease;
  }

  &:hover svg {
    transform: rotate(90deg);
  }
}

.history-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0 10px;
}

.section-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-tertiary);
  padding: 12px 16px 10px;
  font-weight: 700;
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
  padding: 12px 16px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  margin-bottom: 3px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: var(--primary-ghost);
    opacity: 0;
    transition: opacity 0.25s ease;
  }

  &:hover {
    background: var(--bg-card);
    border: 1px solid var(--border-light);

    &::before {
      opacity: 1;
    }
  }

  &.active {
    background: var(--primary-ghost);
    border: 1px solid rgba(245, 158, 11, 0.12);

    .history-item-icon {
      color: var(--primary);
      transform: scale(1.1);
    }
    .history-title {
      color: var(--primary);
      font-weight: 700;
    }
  }

  * {
    position: relative;
    z-index: 1;
  }
}

.history-item-icon {
  color: var(--text-tertiary);
  flex-shrink: 0;
  display: flex;
  transition: all 0.25s ease;
}

.history-item-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.history-title {
  font-size: 13.5px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  transition: all 0.25s ease;
}

.history-time {
  font-size: 11px;
  color: var(--text-tertiary);
}

.empty-hint {
  text-align: center;
  color: var(--text-tertiary);
  font-size: 13px;
  padding: 40px 0;
  opacity: 0.7;
}

.sidebar-footer {
  padding: 16px 18px;
  border-top: 1px solid var(--border-light);
  flex-shrink: 0;
}

.btn-error-book {
  width: 100%;
  padding: 13px 18px;
  background: linear-gradient(135deg, var(--primary-ghost) 0%, var(--accent-ghost) 100%);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  color: var(--primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    background: var(--primary-ghost);
    transform: translateY(-2px);
    box-shadow: var(--shadow-glow);
  }

  &:active {
    transform: translateY(0);
  }
}

.context-overlay {
  position: fixed;
  z-index: 9999;
  background: var(--bg-card);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  min-width: 150px;
  padding: 6px 0;
  animation: ctxIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes ctxIn {
  from {
    opacity: 0;
    transform: scale(0.9) translateY(-8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.ctx-item {
  padding: 10px 20px;
  font-size: 13.5px;
  color: var(--text-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: all 0.2s ease;
  font-weight: 500;

  &:hover {
    background: var(--primary-ghost);
    padding-left: 24px;
  }

  &.danger {
    color: var(--danger);
    &:hover {
      background: rgba(239, 68, 68, 0.08);
    }
  }
}

.sidebar-footer a { text-decoration: none; }

@media (max-width: 768px) {
  .sidebar {
    width: 280px;
    box-shadow: var(--shadow-lg);
  }
}
</style>
