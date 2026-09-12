<script setup>
defineProps({
  reasons: { type: Array, default: () => [] },
})
</script>

<template>
  <el-tag
    class="content-ai-partial-badge"
    type="warning"
    effect="plain"
    size="small"
    :title="reasons.join('；')"
  >部分结果</el-tag>
</template>

<style scoped>
.content-ai-partial-badge {
  --el-tag-text-color: var(--warning);
  --el-tag-border-color: var(--warning);
}
</style>
