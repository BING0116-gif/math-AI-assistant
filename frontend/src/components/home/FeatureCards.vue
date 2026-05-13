<template>
  <section class="feature-cards" aria-label="核心功能">
    <h2 class="section-heading">核心功能</h2>
    <div class="cards-grid">
      <div
        v-for="feature in displayFeatures"
        :key="feature.id"
        class="feature-card hover-lift"
        @click="navigateTo(feature.route)"
        role="link"
        :tabindex="0"
        @keydown.enter="navigateTo(feature.route)"
      >
        <div class="card-icon">
          <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" v-html="feature.icon"></svg>
        </div>
        <div class="card-text">
          <h3 class="card-title">{{ feature.title }}</h3>
          <p class="card-description">{{ feature.description }}</p>
        </div>
        <span v-if="feature.badge" class="card-badge">{{ feature.badge }}</span>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  features: {
    type: Array,
    default: () => [
      {
        id: 'chat',
        icon: '<path d="M24 4C12.95 4 4 12.95 4 24s8.95 20 20 20c1.5 0 2.95-.2 4.35-.55L24 30h4c6.07 0 11-4.93 11-11s-4.93-11-11-11h-4v4h4c3.87 0 7 3.13 7 7s-3.13 7-7 7h-4v4H8.3c-1.4-2.45-2.3-5.25-2.3-8.3 0-9.94 8.06-18 18-18 4.95 0 9.5 1.75 13.2 4.6l2.8-2.8C38.7 6.65 31.65 4 24 4z" fill="currentColor" opacity="0.9"/>',
        title: '智能对话',
        description: '与AI进行自然语言对话，解答数学问题、推导公式、解释概念',
        route: '/chat'
      },
      {
        id: 'error-book',
        icon: '<rect x="6" y="2" width="16" height="20" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><line x1="10" y1="8" x2="18" y2="8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="10" y1="12" x2="16" y2="12" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M26 14h8M26 18h8M26 22h5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><rect x="24" y="6" width="14" height="22" rx="2" stroke="currentColor" stroke-width="2" fill="none"/>',
        title: '错题本管理',
        description: '自动收录错题，分类整理、进度追踪、定期复习提醒',
        route: '/error-book'
      },
      {
        id: 'knowledge',
        icon: '<circle cx="24" cy="24" r="18" stroke="currentColor" stroke-width="2" fill="none"/><line x1="24" y1="16" x2="24" y2="32" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/><line x1="16" y1="24" x2="32" y2="24" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/><circle cx="10" cy="10" r="3" fill="currentColor" opacity="0.3"/><circle cx="38" cy="38" r="4" fill="currentColor" opacity="0.2"/><circle cx="38" cy="10" r="2" fill="currentColor" opacity="0.15"/>',
        title: '知识库搜索',
        description: '海量数学知识库，快速查找定理、公式、解法与经典例题',
        route: '/chat'
      },
      {
        id: 'vision',
        icon: '<rect x="4" y="8" width="36" height="26" rx="3" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="26" cy="22" r="5" stroke="currentColor" stroke-width="2" fill="none"/><path d="M4 30l8-6 6 4 14-10 8 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><circle cx="38" cy="12" r="2" fill="currentColor" opacity="0.4"/>',
        title: '视觉识别',
        description: '上传题目图片，自动识别手写或印刷体数学内容并解答',
        route: '/chat'
      },
      {
        id: 'code',
        icon: '<rect x="3" y="3" width="18" height="18" rx="2" stroke="currentColor" stroke-width="2" fill="none"/><line x1="8" y1="7" x2="8" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="12" y1="9" x2="12" y2="15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><line x1="16" y1="7" x2="16" y2="17" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M28 8l6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M38 8l-6 6 6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
        title: '代码执行',
        description: 'Python 代码实时运行，支持数值计算、图表绘制与仿真模拟',
        route: '/chat'
      },
      {
        id: 'analysis',
        icon: '<rect x="4" y="28" width="8" height="12" rx="1" fill="currentColor" opacity="0.15"/><rect x="14" y="20" width="8" height="20" rx="1" fill="currentColor" opacity="0.25"/><rect x="24" y="16" width="8" height="24" rx="1" fill="currentColor" opacity="0.35"/><rect x="34" y="8" width="8" height="32" rx="1" fill="currentColor" opacity="0.5"/><path d="M7 8l4 4-4 4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M41 16l-4-4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
        title: '数据分析',
        description: '数学统计分析与可视化，帮你理解数据背后的数学规律',
        route: '/chat'
      }
    ]
  }
})

const router = useRouter()

const displayFeatures = computed(() => props.features)

function navigateTo(route) {
  if (route) {
    router.push(route)
  }
}
</script>

<style lang="scss" scoped>
.feature-cards {
  padding: 0 24px;
  max-width: 960px;
  margin: 0 auto 40px;
}

.section-heading {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 20px;
  text-align: center;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  font-size: 11.5px;
}

.cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

.feature-card {
  position: relative;
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  padding: 24px 20px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  gap: 14px;

  &:hover {
    transform: translateY(-4px);
    box-shadow: var(--shadow-md);
    border-color: var(--primary);
    background: var(--bg-card);
  }

  &:active {
    transform: translateY(-1px);
  }
}

.card-icon {
  width: 44px;
  height: 44px;
  color: var(--primary);
  background: var(--primary-ghost);
  border-radius: var(--radius-md);
  padding: 8px;
  display: flex;
  align-items: center;
  justify-content: center;

  svg {
    width: 100%;
    height: 100%;
  }
}

.card-text {
  flex: 1;
}

.card-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.card-description {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.card-badge {
  position: absolute;
  top: 12px;
  right: 12px;
  background: var(--danger);
  color: white;
  font-size: 11px;
  font-weight: 700;
  min-width: 20px;
  height: 20px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 6px;
}

@media (max-width: 900px) {
  .cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 600px) {
  .cards-grid {
    grid-template-columns: 1fr;
  }

  .feature-cards {
    padding: 0 16px;
  }
}
</style>