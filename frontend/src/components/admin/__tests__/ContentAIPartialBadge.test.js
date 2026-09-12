import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ContentAIPartialBadge from '../ContentAIPartialBadge.vue'

describe('ContentAIPartialBadge', () => {
  it('显示部分结果及原因提示', () => {
    const wrapper = mount(ContentAIPartialBadge, {
      props: { reasons: ['model_output_truncated', 'heuristic_json_recovery'] },
      global: {
        stubs: {
          ElTag: {
            props: ['title'],
            template: '<span class="el-tag-stub" :title="title"><slot /></span>',
          },
        },
      },
    })

    expect(wrapper.text()).toContain('部分结果')
    expect(wrapper.get('.el-tag-stub').attributes('title')).toBe(
      'model_output_truncated；heuristic_json_recovery',
    )
  })
})
