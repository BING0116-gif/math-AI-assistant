<template>
  <div class="filter-panel">
    <div class="filter-title">🔍 筛选</div>
    <div class="filter-grid">
      <div class="filter-field">
        <label>搜索</label>
        <input v-model="localFilter.search" @input="onChange" placeholder="搜索题目、答案、标签..." class="filter-input" />
      </div>
      <div class="filter-field">
        <label>分类</label>
        <select v-model="localFilter.category" @change="onChange" class="filter-input">
          <option value="">全部分类</option>
          <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
        </select>
      </div>
      <div class="filter-field">
        <label>掌握度</label>
        <select v-model="localFilter.mastery" @change="onChange" class="filter-input">
          <option value="">全部</option>
          <option v-for="n in 5" :key="n" :value="n">{{ '★'.repeat(n) }}{{ '☆'.repeat(5 - n) }}</option>
        </select>
      </div>
    </div>
    <button v-if="hasActiveFilter" class="reset-btn" @click="handleReset">重置筛选</button>
  </div>
</template>

<script setup>
import { reactive, computed, watch } from 'vue'

const props = defineProps({
  filter: Object,
  categories: Array
})

const emit = defineEmits(['update:filter', 'reset'])
const localFilter = reactive({ ...props.filter })

watch(() => props.filter, (val) => Object.assign(localFilter, val), { deep: true })

const hasActiveFilter = computed(() => localFilter.search || localFilter.category || localFilter.mastery)

function onChange() {
  emit('update:filter', { ...localFilter })
}

function handleReset() {
  localFilter.search = ''
  localFilter.category = ''
  localFilter.mastery = ''
  emit('reset')
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.filter-panel {
  background: var(--bg-card);
  border-radius: var(--radius-lg);
  padding: 22px 24px;
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--border-light);
  margin-bottom: 22px;
  position: relative;
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
}

.filter-title { font-size: 15px; font-weight: 700; color: var(--text-primary); margin-bottom: 16px; }

.filter-grid { display: flex; gap: 20px; }

.filter-field {
  flex: 1;
  label { display: block; font-size: 12.5px; font-weight: 600; color: var(--text-secondary); margin-bottom: 7px; }
}

.filter-input {
  width: 100%; padding: 10px 14px;
  border: 1.5px solid var(--border-default); border-radius: var(--radius-md);
  font-size: 14px; font-family: inherit; outline: none;
  transition: border-color var(--transition-fast);
  background: var(--bg-card);
  color: var(--text-primary);

  &:focus {
    border-color: var(--primary);
    background: var(--bg-card);
    box-shadow: 0 0 0 3px var(--primary-ghost);
  }
}

.reset-btn {
  position: absolute; top: 22px; right: 24px;
  padding: 6px 16px; border-radius: $radius-full;
  border: 1px solid var(--border-default); background: var(--bg-card);
  font-size: 13px; cursor: pointer; color: var(--text-secondary); font-family: inherit;
  transition: all var(--transition-fast);
  &:hover { border-color: var(--primary); color: var(--primary); }
}

@media (max-width: 768px) {
  .filter-grid { flex-direction: column; gap: 14px; }
  .reset-btn { position: static; margin-top: 14px; }
}
</style>