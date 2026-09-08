import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AskStudentCard from '../AskStudentCard.vue'

const baseCard = {
  clarification_id: 'c-123',
  pending_turn_id: 't-456',
  session_id: 's-1',
  question: '已知三角形两边长，求第三边，缺什么条件？',
  kind: 'missing_condition',
  options: [
    { label: 'A', text: '是直角三角形' },
    { label: 'B', text: '给出两边的夹角' },
  ],
}

describe('AskStudentCard', () => {
  it('renders question, kind label and options', () => {
    const wrapper = mount(AskStudentCard, { props: { card: baseCard } })
    expect(wrapper.text()).toContain('缺条件')
    expect(wrapper.text()).toContain('已知三角形两边长，求第三边，缺什么条件？')
    const options = wrapper.findAll('.ask-card__option')
    expect(options).toHaveLength(2)
    expect(options[0].text()).toContain('A. 是直角三角形')
  })

  it('emits submit with option text when an option is clicked', async () => {
    const wrapper = mount(AskStudentCard, { props: { card: baseCard } })
    await wrapper.findAll('.ask-card__option')[1].trigger('click')
    expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.emitted('submit')[0][0]).toEqual({ answer: '给出两边的夹角', optionLabel: 'B' })
  })

  it('renders a free input and emits submit with typed answer', async () => {
    const wrapper = mount(AskStudentCard, { props: { card: baseCard } })
    const textarea = wrapper.find('textarea.ask-card__input')
    expect(textarea.exists()).toBe(true)
    textarea.setValue('夹角是 60 度')
    await textarea.trigger('input')
    await wrapper.find('.ask-card__submit').trigger('click')
    expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.emitted('submit')[0][0]).toEqual({ answer: '夹角是 60 度' })
  })

  it('does not emit empty free text', async () => {
    const wrapper = mount(AskStudentCard, { props: { card: baseCard } })
    await wrapper.find('.ask-card__submit').trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()
  })

  it('disables interactions when disabled prop is true', async () => {
    const wrapper = mount(AskStudentCard, { props: { card: baseCard, disabled: true } })
    expect(wrapper.findAll('.ask-card__option')[0].attributes('disabled')).toBeDefined()
    expect(wrapper.find('.ask-card__submit').attributes('disabled')).toBeDefined()
    await wrapper.findAll('.ask-card__option')[0].trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()
  })
})
