<script setup lang="ts">
</script>

<template>
  <div class="dashboard-view">
    <div class="dashboard-header">
      <h1 class="page-title">学习看板</h1>
      <p class="dashboard-subtitle">按课程、章节和知识点查看学习数据</p>
    </div>
    <div class="dashboard-body">
      <!-- Phase 5 实现：学习看板聚合统计与错题分析 -->
      <p class="dashboard-placeholder">完成练习或把需要复盘的题加入错题本后，这里会按课程和章节形成学习分析。</p>
    </div>
  </div>
</template>

<style scoped>
.dashboard-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.dashboard-header {
  padding: var(--space-6) var(--space-6) var(--space-3);
  border-bottom: 1px solid var(--border-subtle);
}
.dashboard-subtitle {
  font-size: var(--font-size-sm);
  color: var(--text-secondary);
  margin-top: var(--space-1);
}
.dashboard-body {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
}
.dashboard-placeholder {
  color: var(--text-tertiary);
  font-size: var(--font-size-sm);
  text-align: center;
  padding: var(--space-12) 0;
}
</style>