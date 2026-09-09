import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MathVisualCard from '../MathVisualCard.vue'

const spec = {
  type: 'tangent_line',
  title: 'y=x² 在 x=1 处的切线',
  viewport: { x_min: -3, x_max: 3, y_min: -7, y_max: 9 },
  series: [
    { kind: 'curve', label: 'y=x²', points: [[-2, 4], [-1, 1], [0, 0], [1, 1], [2, 4]] },
    { kind: 'line', label: 'y=2x-1', points: [[-3, -7], [3, 5]] },
  ],
  annotations: [{ kind: 'point', x: 1, y: 1, label: '切点' }],
  teaching_note: '观察切线在切点附近与曲线贴合。',
}

describe('MathVisualCard', () => {
  it('renders axes, series, legend and verified state with native SVG', () => {
    const wrapper = mount(MathVisualCard, {
      props: { spec, verification: { status: 'verified' } },
    })
    expect(wrapper.find('svg[role="img"]').exists()).toBe(true)
    expect(wrapper.findAll('polyline')).toHaveLength(2)
    expect(wrapper.text()).toContain('已验证')
    expect(wrapper.text()).toContain('y=2x-1')
    expect(wrapper.find('canvas').exists()).toBe(false)
  })

  it('draws markers only for point annotations', () => {
    const withLabel = structuredClone(spec)
    withLabel.annotations.push({ kind: 'label', x: 0, y: 2, label: '对称轴 x=0' })
    const wrapper = mount(MathVisualCard, { props: { spec: withLabel } })
    expect(wrapper.findAll('.annotations circle')).toHaveLength(1)
    expect(wrapper.text()).toContain('对称轴 x=0')
  })

  it('never creates executable nodes from labels', () => {
    const hostile = structuredClone(spec)
    hostile.series[0].label = '<script>window.pwned=true</script>'
    const wrapper = mount(MathVisualCard, { props: { spec: hostile } })
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.text()).toContain('<script>window.pwned=true</script>')
    expect(window.pwned).toBeUndefined()
  })

  it.each([
    ['vector_plot', 'vector', 'line'],
    ['geometry_plot', 'polygon', 'polygon'],
  ])('selects the native renderer for %s', (type, kind, selector) => {
    const rendererSpec = {
      ...structuredClone(spec),
      type,
      series: [{ kind, label: kind, points: [[0, 0], [1, 1], ...(kind === 'polygon' ? [[0, 1]] : [])] }],
      annotations: [],
    }
    const wrapper = mount(MathVisualCard, { props: { spec: rendererSpec } })
    expect(wrapper.find(selector).exists()).toBe(true)
  })
})
