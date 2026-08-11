<script setup lang="ts">
</script>

<template>
  <div class="profile-view">
    <div class="profile-header">
      <h1 class="page-title">你的数学学习画像</h1>
      <p class="profile-subtitle">由练习、错题和课程进度逐渐形成的知识掌握图</p>
    </div>
    <div class="profile-body">
      <!-- Phase 3 实现：画像摘要、知识图谱、知识树、变化记录、证据检查器 -->
      <p class="profile-placeholder">完成几道系统内练习后，这里会逐步形成你的知识掌握图。普通提问只会记录为"接触过"，不会被当作掌握证据。</p>
    </div>
  </div>
</template>

<style scoped>
.profile-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.profile-header {
  padding: var(--space-6) var(--space-6) var(--space-3);
  border-bottom: 1px solid var(--border-subtle);
}
.profile-subtitle {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: var(--space-1);
}
.profile-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
}
.profile-placeholder {
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
  text-align: center;
  padding: var(--space-12) 0;
}
</style>