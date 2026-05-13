<template>
  <div class="quick-tools" aria-label="快捷工具">
    <div class="tools-row">
      <button
        v-for="tool in tools"
        :key="tool.id"
        class="tool-btn"
        @click="handleToolClick(tool)"
        :title="tool.label"
      >
        <span class="tool-icon" v-html="tool.icon"></span>
        <span class="tool-label">{{ tool.label }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
const emit = defineEmits(['toolClick'])

const tools = [
  {
    id: 'quick',
    label: '快速问答',
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>'
  },
  {
    id: 'image',
    label: '图像识别',
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>'
  },
  {
    id: 'formula',
    label: '公式推导',
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 016.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"/></svg>'
  },
  {
    id: 'code',
    label: '代码执行',
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'
  },
  {
    id: 'writing',
    label: '写作辅助',
    icon: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a2.83 2.83 0 114 4L7.5 20.5 2 22l1.5-5.5z"/></svg>'
  }
]

function handleToolClick(tool) {
  emit('toolClick', tool)
}
</script>

<style lang="scss" scoped>
.quick-tools {
  padding: 0 24px;
  max-width: 720px;
  margin: 0 auto 28px;
}

.tools-row {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}

.tool-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  border: 1.5px solid var(--border-light);
  border-radius: var(--radius-xl);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 13.5px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  white-space: nowrap;

  &:hover {
    color: var(--primary);
    border-color: var(--primary);
    background: var(--primary-ghost);
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
  }

  &:active {
    transform: translateY(0);
  }
}

.tool-icon {
  display: flex;
  align-items: center;
}

.tool-label {
  font-size: 13.5px;
}

@media (max-width: 600px) {
  .quick-tools {
    padding: 0 16px;
  }

  .tools-row {
    gap: 8px;
  }

  .tool-btn {
    padding: 8px 14px;
  }
}
</style>