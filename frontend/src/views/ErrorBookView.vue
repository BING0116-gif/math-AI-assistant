<template>
  <LayoutDefault>
    <template #header>
      <div class="eb-header-content">
        <h2 class="eb-title">📚 错题本</h2>
        <router-link to="/" class="back-link">← 返回对话</router-link>
      </div>
    </template>

    <div class="error-book-view">
      <ErrorStats
        :total="store.totalErrors"
        :unmastered="store.unmasteredCount"
        :mastered="store.masteredCount"
      />

      <ErrorFilter
        :filter="store.filter"
        :categories="store.availableCategories"
        @update:filter="store.setFilter($event)"
        @reset="store.resetFilter()"
      />

      <div class="error-list" ref="listRef" v-loading="store.loading">
        <TransitionGroup name="list-item">
          <ErrorCard
            v-for="(error, idx) in store.filteredErrors"
            :key="error.id"
            :error="error"
            :index="idx"
            @view-detail="openDetail"
            @toggle-mastery="store.toggleMastery(error.id)"
            @delete="handleDelete(error)"
          />
        </TransitionGroup>
        <div v-if="store.filteredErrors.length === 0 && !store.loading" class="empty-state">
          <div class="empty-icon">📭</div>
          <div class="empty-text">{{ store.totalErrors === 0 ? '暂无错题记录' : '没有匹配的错题' }}</div>
          <div class="empty-hint">{{ store.totalErrors === 0 ? '在对话中点击"加入错题本"来添加第一道错题吧！' : '尝试调整筛选条件' }}</div>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <ErrorDetailModal
        v-if="detailVisible"
        :error="detailError"
        :current-index="detailIndex"
        :total="store.filteredErrors.length"
        @close="closeDetail"
        @prev="navigateDetail(-1)"
        @next="navigateDetail(1)"
        @toggle-mastery="store.toggleMastery(detailError.id)"
        @delete="handleDeleteFromDetail"
      />
    </Teleport>
  </LayoutDefault>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import LayoutDefault from '@/components/layout/LayoutDefault.vue'
import ErrorStats from '@/components/errorBook/ErrorStats.vue'
import ErrorFilter from '@/components/errorBook/ErrorFilter.vue'
import ErrorCard from '@/components/errorBook/ErrorCard.vue'
import ErrorDetailModal from '@/components/errorBook/ErrorDetailModal.vue'
import { useErrorBookStore } from '@/stores/errorBookStore'
import { escapeHtml } from '@/utils/helpers'

const route = useRoute()
const router = useRouter()
const store = useErrorBookStore()

const detailVisible = ref(false)
const detailIndex = ref(-1)

const detailError = computed(() =>
  detailIndex.value >= 0 ? store.filteredErrors[detailIndex.value] : null
)

onMounted(() => {
  store.loadErrors()
  const errorId = route.params.errorId
  if (errorId) {
    const idx = store.filteredErrors.findIndex(e => e.id === errorId)
    if (idx >= 0) {
      detailIndex.value = idx
      detailVisible.value = true
    }
  }
})

function openDetail(idx) {
  detailIndex.value = idx
  detailVisible.value = true
}

function closeDetail() {
  detailVisible.value = false
  detailIndex.value = -1
}

function navigateDetail(dir) {
  const newIdx = detailIndex.value + dir
  if (newIdx >= 0 && newIdx < store.filteredErrors.length) {
    detailIndex.value = newIdx
  }
}

function handleDelete(error) {
  const name = (error.display_question || error.question || '').substring(0, 50)
  ElMessageBox.confirm(`确定要删除这道错题吗？\n\n${name}...`, '确认删除', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning'
  }).then(() => {
    store.deleteError(error.id)
  }).catch(() => {})
}

function handleDeleteFromDetail() {
  const error = detailError.value
  if (!error) return
  handleDelete(error)
  closeDetail()
}

function handleKeydown(e) {
  if (!detailVisible.value) return
  if (e.key === 'Escape') closeDetail()
  else if (e.key === 'ArrowLeft') navigateDetail(-1)
  else if (e.key === 'ArrowRight') navigateDetail(1)
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))
</script>

<style lang="scss" scoped>
@use '@/styles/variables' as *;

.eb-header-content {
  display: flex; align-items: center; justify-content: space-between; flex: 1;
}

.eb-title { font-size: 17px; font-weight: 700; color: $text-primary; }

.back-link {
  font-size: 13px; color: $primary; text-decoration: none; font-weight: 500;
  padding: 6px 14px; border-radius: $radius-full; transition: all $transition-fast;
  &:hover { background: $primary-bg; }
}

.error-book-view {
  flex: 1; overflow-y: auto; padding: 24px;
  max-width: 1000px; margin: 0 auto; width: 100%;
}

.error-list {
  display: flex; flex-direction: column; gap: 14px;
  min-height: 200px; position: relative;
}

.empty-state {
  text-align: center; padding: 60px 20px;
  .empty-icon { font-size: 52px; margin-bottom: 14px; }
  .empty-text { font-size: 17px; color: $text-secondary; font-weight: 600; margin-bottom: 8px; }
  .empty-hint { font-size: 14px; color: $text-tertiary; }
}

.list-item-enter-active {
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.list-item-leave-active {
  transition: all 0.25s ease;
  position: absolute; width: 100%;
}
.list-item-enter-from { opacity: 0; transform: translateY(24px) scale(0.96); }
.list-item-leave-to { opacity: 0; transform: translateX(-30px); }

@media (max-width: 768px) {
  .error-book-view { padding: 16px; }
}
</style>
