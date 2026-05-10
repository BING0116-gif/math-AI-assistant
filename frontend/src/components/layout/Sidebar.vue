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
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-right: 1px solid rgba(226, 232, 240, 0.4);
  z-index: 100;
  transform: translateX(0);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  box-shadow: 4px 0 24px rgba(0, 0, 0, 0.04);

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
  border-bottom: 1px solid rgba(226, 232, 240, 0.3);
  flex-shrink: 0;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.03) 0%, rgba(129, 140, 248, 0.05) 100%);
}

.brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-icon {
  width: 46px;
  height: 46px;
  background: linear-gradient(135deg, $primary 0%, $primary-light 100%);
  border-radius: $radius-lg;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  flex-shrink: 0;
  box-shadow: 0 4px 15px rgba(99, 102, 241, 0.25);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    transform: scale(1.08) rotate(-3deg);
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);
  }
}

.brand-text h1 {
  font-size: 18px;
  font-weight: 700;
  color: $text-primary;
  line-height: 1.3;
  background: linear-gradient(135deg, $text-primary 0%, $primary 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.brand-text span {
  font-size: 12px;
  color: $text-tertiary;
  display: block;
  margin-top: 2px;
  letter-spacing: 0.02em;
}

.sidebar-actions {
  padding: 16px 18px;
  flex-shrink: 0;
}

.btn-new-chat {
  width: 100%;
  padding: 13px 18px;
  border: 2px dashed rgba(99, 102, 241, 0.25);
  border-radius: $radius-lg;
  background: linear-gradient(135deg, rgba(238, 242, 255, 0.8) 0%, rgba(255, 255, 255, 0.9) 100%);
  color: $primary;
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
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.08) 0%, rgba(129, 140, 248, 0.12) 100%);
    border-color: $primary;
    border-style: solid;
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(99, 102, 241, 0.2);
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
  color: $text-tertiary;
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
  border-radius: $radius-md;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  margin-bottom: 3px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.06) 0%, rgba(129, 140, 248, 0.03) 100%);
    opacity: 0;
    transition: opacity 0.25s ease;
  }

  &:hover {
    background: rgba(241, 245, 249, 0.7);
    
    &::before {
      opacity: 1;
    }
  }

  &.active {
    background: linear-gradient(135deg, rgba(99, 102, 241, 0.1) 0%, rgba(129, 140, 248, 0.08) 100%);
    box-shadow: 0 2px 12px rgba(99, 102, 241, 0.12);
    
    .history-item-icon { 
      color: $primary; 
      transform: scale(1.1);
    }
    .history-title { 
      color: $primary-dark; 
      font-weight: 700; 
    }
  }

  * {
    position: relative;
    z-index: 1;
  }
}

.history-item-icon {
  color: $text-tertiary;
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
  color: $text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-weight: 500;
  transition: all 0.25s ease;
}

.history-time {
  font-size: 11px;
  color: $text-tertiary;
}

.empty-hint {
  text-align: center;
  color: $text-tertiary;
  font-size: 13px;
  padding: 40px 0;
  opacity: 0.7;
}

.sidebar-footer {
  padding: 16px 18px;
  border-top: 1px solid rgba(226, 232, 240, 0.3);
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.5);
}

.btn-error-book {
  width: 100%;
  padding: 13px 18px;
  background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 50%, #fed7aa 100%);
  border: 1px solid rgba(251, 146, 60, 0.3);
  border-radius: $radius-lg;
  color: #c2410c;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px rgba(234, 88, 12, 0.08);

  &:hover {
    background: linear-gradient(135deg, #ffedd5 0%, #fed7aa 50%, #fdba74 100%);
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(234, 88, 12, 0.2);
    border-color: rgba(251, 146, 60, 0.5);
  }

  &:active {
    transform: translateY(0);
  }
}

.context-overlay {
  position: fixed;
  z-index: 9999;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(226, 232, 240, 0.5);
  border-radius: $radius-lg;
  box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15), 0 0 0 1px rgba(255, 255, 255, 0.8);
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
  color: $text-primary;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 10px;
  transition: all 0.2s ease;
  font-weight: 500;

  &:hover { 
    background: linear-gradient(90deg, rgba(99, 102, 241, 0.06) 0%, transparent 100%); 
    padding-left: 24px;
  }
  
  &.danger { 
    color: $danger;
    &:hover { 
      background: linear-gradient(90deg, rgba(239, 68, 68, 0.08) 0%, transparent 100%);
    }
  }
}

.sidebar-footer a { text-decoration: none; }

@media (max-width: 768px) {
  .sidebar {
    width: 280px;
    box-shadow: 8px 0 32px rgba(0, 0, 0, 0.12);
  }
}
</style>