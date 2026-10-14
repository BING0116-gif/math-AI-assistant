import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LearningResourceCard from '../LearningResourceCard.vue'

const stubs = { MathAnimationCard: true, MathVisualCard: true }

describe('LearningResourceCard', () => {
  it('reveals worked examples one keyboard-operable step at a time', async () => {
    const wrapper = mount(LearningResourceCard, {
      props: { resource: { id: 'ex-1', type: 'worked_example', title: '基础例题', body: '先写定义。再完成化简。最后检查条件。', metadata: {} } },
      global: { stubs },
    })
    const buttons = wrapper.findAll('.example-steps button')
    expect(buttons).toHaveLength(3)
    expect(wrapper.text()).not.toContain('先写定义。')
    await buttons[0].trigger('click')
    expect(wrapper.text()).toContain('先写定义。')
    expect(buttons[0].attributes('aria-expanded')).toBe('true')
    await buttons[2].trigger('click')
    expect(wrapper.text()).not.toContain('最后检查条件。')
  })

  it('provides checkpoint feedback without emitting mastery evidence', async () => {
    const wrapper = mount(LearningResourceCard, {
      props: {
        resource: { id: 'cp-1', type: 'checkpoint', title: '理解检查', body: '1. 为什么可导必连续？\n2. 举出一个反例。', metadata: {} },
        commonError: '把连续误认为可导。',
      },
      global: { stubs },
    })
    expect(wrapper.text()).toContain('不会写入掌握度')
    await wrapper.find('.checkpoint-list button').trigger('click')
    expect(wrapper.text()).toContain('把连续误认为可导')
    expect(wrapper.text()).toContain('下一步')
    expect(wrapper.emitted()).not.toHaveProperty('mastery')
  })

  it('routes exercise actions through the formal practice event', async () => {
    const wrapper = mount(LearningResourceCard, {
      props: { resource: { id: 'set-1', type: 'exercise_set', title: '正式练习', body: '进入题库。', metadata: { question_ids: ['Q1'] } } },
      global: { stubs },
    })
    await wrapper.find('.practice-button').trigger('click')
    expect(wrapper.emitted('practice')).toHaveLength(1)
  })
})

describe('讲义分节子卡', () => {
  it('把 ## 小节拆成编号子卡并渲染自查勾选框', () => {
    const wrapper = mount(LearningResourceCard, {
      props: {
        resource: {
          id: 'le-1', type: 'lecture', title: '精讲',
          body: '## 为什么学\n先讲前提。\n\n## 核心定义\n$f(x)$ 的含义。\n\n## 自查清单\n- [ ] 定义域写了？',
        },
      },
      global: { stubs },
    })
    const subcards = wrapper.findAll('.lecture-subcard')
    expect(subcards).toHaveLength(3)
    expect(subcards[0].text()).toContain('为什么学')
    expect(subcards[1].text()).toContain('核心定义')
    expect(subcards[2].find('.check-todo').exists()).toBe(true)
    expect(wrapper.find('.lecture-subcard--lead').exists()).toBe(true)
  })

  it('易错警示子卡带警示色修饰', () => {
    const wrapper = mount(LearningResourceCard, {
      props: {
        resource: { id: 'pf-1', type: 'pitfalls', title: '易错警示', body: '## 高频错误\n别乱替换。' },
      },
      global: { stubs },
    })
    expect(wrapper.find('.lecture-subcard--warn').exists()).toBe(true)
  })
})
