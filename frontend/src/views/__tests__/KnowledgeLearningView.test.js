import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { pointId: 'kp-1' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/components/shell/AppShell.vue', () => ({
  default: { template: '<div><slot name="page-header" /><slot /></div>' },
}))
vi.mock('@/components/knowledge/LearningResourceCard.vue', () => ({
  default: { props: ['resource'], template: '<div class="lesson-card">{{ resource.title }}</div>' },
}))
vi.mock('@/components/practice/PracticeRunner.vue', () => ({
  default: { template: '<div class="runner-stub" />' },
}))
vi.mock('@/composables/useEntranceAnimation', () => ({
  useEntranceAnimation: () => () => {},
}))

const learningContent = {
  id: 'kp-1', code: 'function-definition', name: '函数的定义', description: '理解函数与定义域',
  difficulty: 2, course: { id: 'c1', name: '高等数学' }, version: { id: 'v1' },
  learning_objectives: ['目标一'], prerequisite_points: [],
  resources: [{ id: 'r1', type: 'concept', title: '核心概念', body: '概念正文' }],
}

vi.mock('@/api/knowledge', () => ({
  getKnowledgePointLearning: vi.fn(async () => ({ data: learningContent })),
  getCourseLearningMap: vi.fn(async () => ({
    data: { points: [{ code: 'function-definition', mastery: 0.56, status: 'learning', open_error_count: 1, due_error_count: 0 }] },
  })),
  getKnowledgePointExamples: vi.fn(async () => ({
    data: { examples: [{ question_id: 'q1', question_type: 'choice', content: '例题题干', options: [{ id: 'A', text: 'x' }], difficulty: 2, answer: 'A', analysis: '例题解析' }] },
  })),
}))
vi.mock('@/api/errorBook', () => ({
  getErrorBook: vi.fn(async () => ({
    data: [{ id: 'e1', question: '错题题干', knowledge_point_codes: ['function-definition'], is_mastered: false, wrong_attempt_count: 2, review_state: 'new', error_reason: '符号抄错', correct_answer: 'A', original_answer: 'B', question_id: 'q9', variant_supported: true }],
  })),
  createVariantSession: vi.fn(),
}))
vi.mock('@/api/practice', () => ({
  unwrapPractice: vi.fn((response) => response?.data?.data ?? response?.data),
}))

import KnowledgeLearningView from '../KnowledgeLearningView.vue'

describe('KnowledgeLearningView 一站式学习枢纽', () => {
  it('挂载并渲染掌握度/例题/练习/错题四个区块', async () => {
    const wrapper = mount(KnowledgeLearningView, { global: { plugins: [createPinia()] } })
    await flushPromises()
    expect(wrapper.text()).toContain('函数的定义')
    expect(wrapper.find('.mastery-ring span').text()).toBe('56%')
    expect(wrapper.findAll('.lesson-card')).toHaveLength(1)
    expect(wrapper.findAll('.example-item')).toHaveLength(1)
    expect(wrapper.text()).toContain('开始 5 题小练习')
    expect(wrapper.text()).toContain('本知识点有 1 道未掌握错题')
  })
})
