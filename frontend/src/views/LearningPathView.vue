<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, BookOpenCheck, CircleCheck, CircleDashed, CirclePlay, RefreshCw } from 'lucide-vue-next'
import AppShell from '@/components/shell/AppShell.vue'
import { getMyLearningPath, trackPathStep } from '@/api/learningPath'

interface PathStep {
  type: string
  title: string
  description: string
  route: string
  status: string
}
interface PathPoint {
  code: string
  name: string
  mastery: number
  attempts_count: number
  mistake_count: number
  prerequisites: string[]
  steps: PathStep[]
}
interface PathWeek {
  week: number
  focus: string
  points: PathPoint[]
}

const router = useRouter()
const weeks = ref<PathWeek[]>([])
const weakCount = ref(0)
const threshold = ref(0.6)
const loading = ref(true)
const loadError = ref('')

const STEP_ICONS: Record<string, any> = {
  explain: BookOpenCheck,
  practice: CirclePlay,
  variant: RefreshCw,
  review: CircleCheck,
}

const firstPendingRoute = computed(() => {
  for (const week of weeks.value) {
    for (const point of week.points) {
      for (const step of point.steps) {
        if (step.status !== 'done') return step.route
      }
    }
  }
  return ''
})

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const data = await getMyLearningPath()
    weeks.value = data.weeks || []
    weakCount.value = data.weak_count || 0
    threshold.value = data.weak_threshold || 0.6
  } catch (error: any) {
    loadError.value = error?.message || '学习路径加载失败'
  } finally {
    loading.value = false
  }
}

function goStep(step: PathStep, code: string) {
  trackPathStep(step.type, code)
  router.push(step.route)
}

onMounted(load)
</script>

<template>
  <AppShell>
    <template #topbar-title>
      <span>我的学习路径</span>
    </template>

    <div class="path-view">
      <header class="path-view__head">
        <button class="path-view__back" type="button" @click="router.push('/profile')">
          <ArrowLeft :size="15" /> 返回画像
        </button>
        <div class="path-view__summary">
          <template v-if="!loading && !loadError">
            <strong>{{ weakCount }}</strong> 个薄弱知识点
            <span class="path-view__caption">掌握度低于 {{ Math.round(threshold * 100) }}% 且有作答记录 · 已按依赖关系排序</span>
          </template>
        </div>
        <button v-if="firstPendingRoute" class="path-view__resume" type="button" @click="router.push(firstPendingRoute)">
          继续学习
        </button>
      </header>

      <div v-if="loading" class="path-view__state">正在生成路径…</div>
      <div v-else-if="loadError" class="path-view__state path-view__state--error">
        {{ loadError }}
        <button type="button" @click="load">重试</button>
      </div>
      <div v-else-if="weeks.length === 0" class="path-view__state">
        当前没有薄弱知识点——保持节奏，完成练习后这里会规划下一阶段。
      </div>

      <section v-for="week in weeks" v-else :key="week.week" class="path-week" :aria-label="`第 ${week.week} 周计划`">
        <header class="path-week__head">
          <span class="path-week__badge">第 {{ week.week }} 周</span>
          <span class="path-week__focus">{{ week.focus }}</span>
        </header>

        <article v-for="point in week.points" :key="point.code" class="path-point">
          <header class="path-point__head">
            <h3 class="path-point__name">{{ point.name }}</h3>
            <span class="path-point__mastery" :title="`当前掌握度 ${Math.round(point.mastery * 100)}%`">
              掌握 {{ Math.round(point.mastery * 100) }}%
            </span>
          </header>
          <p v-if="point.prerequisites.length" class="path-point__prereq">
            先修：{{ point.prerequisites.join('、') }}
          </p>

          <ol class="path-point__steps">
            <li v-for="step in point.steps" :key="step.type" class="path-step" :class="`path-step--${step.status}`">
              <component :is="STEP_ICONS[step.type] || CircleDashed" class="path-step__icon" :size="15" />
              <div class="path-step__body">
                <span class="path-step__title">{{ step.title }}</span>
                <span class="path-step__desc">{{ step.description }}</span>
              </div>
              <button class="path-step__go" type="button" @click="goStep(step, point.code)">
                {{ step.status === 'done' ? '再练' : '开始' }}
              </button>
            </li>
          </ol>
        </article>
      </section>
    </div>
  </AppShell>
</template>

<style scoped>
.path-view { flex: 1; overflow-y: auto; padding: 22px clamp(16px, 4vw, 44px) 40px; display: grid; gap: 18px; align-content: start; }
.path-view__head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.path-view__back { display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 10px; border: 1px solid var(--border); border-radius: var(--r-s); background: transparent; color: var(--ink-2); font: inherit; font-size: 13px; cursor: pointer; }
.path-view__back:hover { color: var(--brand-text); border-color: var(--brand); }
.path-view__summary { display: flex; align-items: baseline; gap: 8px; color: var(--ink-1); font-size: 15px; }
.path-view__summary strong { font-size: 22px; color: var(--brand-text); }
.path-view__caption { font-size: 12px; color: var(--ink-3); }
.path-view__resume { margin-left: auto; height: 32px; padding: 0 16px; border: 0; border-radius: var(--r-s); background: var(--accent); color: #fff; font: inherit; font-size: 13px; font-weight: 600; cursor: pointer; }
.path-view__resume:hover { filter: brightness(1.05); }
.path-view__state { padding: 28px; border: 1px dashed var(--border); border-radius: var(--r-m); color: var(--ink-3); font-size: 13.5px; text-align: center; display: grid; gap: 10px; justify-items: center; }
.path-view__state--error { color: var(--rose); border-color: var(--rose); }
.path-view__state button { height: 28px; padding: 0 12px; border: 1px solid var(--border); border-radius: var(--r-s); background: transparent; color: var(--ink-2); font: inherit; cursor: pointer; }

.path-week { display: grid; gap: 12px; }
.path-week__head { display: flex; align-items: center; gap: 10px; }
.path-week__badge { padding: 3px 10px; border-radius: 999px; background: var(--brand-soft); color: var(--brand-text); font-size: 12.5px; font-weight: 700; }
.path-week__focus { font-size: 13px; color: var(--ink-2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.path-point { border: 1px solid var(--border); border-radius: var(--r-m); background: var(--surface); padding: var(--space-4); display: grid; gap: 10px; }
.path-point__head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.path-point__name { margin: 0; font-size: 15px; font-weight: 700; color: var(--ink-1); }
.path-point__mastery { font-size: 12px; color: var(--amber); font-weight: 600; }
.path-point__prereq { margin: 0; font-size: 12px; color: var(--ink-3); }

.path-point__steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.path-step { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid var(--border); border-radius: var(--r-s); background: var(--bg); }
.path-step--done { opacity: 0.66; }
.path-step--done .path-step__icon { color: var(--green); }
.path-step--in_progress .path-step__icon { color: var(--brand); }
.path-step--pending .path-step__icon { color: var(--ink-4); }
.path-step__body { display: grid; min-width: 0; }
.path-step__title { font-size: 13.5px; font-weight: 600; color: var(--ink-1); }
.path-step__desc { font-size: 12px; color: var(--ink-3); }
.path-step__go { margin-left: auto; height: 28px; padding: 0 12px; border: 1px solid var(--border); border-radius: var(--r-s); background: transparent; color: var(--ink-2); font: inherit; font-size: 12.5px; cursor: pointer; }
.path-step__go:hover { color: var(--brand-text); border-color: var(--brand); }

@media (max-width: 640px) {
  .path-view__resume { margin-left: 0; }
}
</style>
