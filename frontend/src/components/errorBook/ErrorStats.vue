<template>
  <div class="stats-row">
    <div class="stat-card">
      <div class="stat-value">{{ total }}</div>
      <div class="stat-label">总计</div>
    </div>
    <div class="stat-card unmastered">
      <div class="stat-value">{{ unmastered }}</div>
      <div class="stat-label">待复习</div>
    </div>
    <div class="stat-card mastered">
      <div class="stat-value">{{ mastered }}</div>
      <div class="stat-label">已掌握</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  total: Number,
  unmastered: Number,
  mastered: Number
})
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.stats-row {
  display: flex; gap: 16px; margin-bottom: 22px;
}

.stat-card {
  flex: 1;
  background: white;
  border-radius: $radius-lg;
  padding: 18px 20px;
  text-align: center;
  box-shadow: $shadow-sm;
  border: 1px solid $border-light;
  transition: all $transition-base;

  &:hover { transform: translateY(-2px); box-shadow: $shadow-md; }

  &.unmastered { border-left: 4px solid $warning; }
  &.mastered { border-left: 4px solid $success; }
}

.stat-value {
  font-size: 28px; font-weight: 800; color: $primary;
  .unmastered & { color: $warning; }
  .mastered & { color: $success; }
}

.stat-label {
  font-size: 13px; color: $text-tertiary; margin-top: 4px; font-weight: 500;
}

@media (max-width: 768px) {
  .stats-row { gap: 10px; }
  .stat-card { padding: 14px; }
  .stat-value { font-size: 24px; }
}
</style>
