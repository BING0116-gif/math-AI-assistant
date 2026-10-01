import { graphic, init, registerTheme, use } from 'echarts/core'
import { BarChart, HeatmapChart, LineChart, PieChart } from 'echarts/charts'
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'

use([
  BarChart,
  HeatmapChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
])

/* ============================================================
   知微双主题(REFACTOR_PLAN.md §7.1)
   - 系列顺序语义固定:系列 1(主数据)= brand 青,系列 2(对比/正确率)= accent 橙
   - heatmap visualMap 五档青色阶梯(废除旧紫阶)
   ============================================================ */

interface ZhiweiThemePalette {
  brand: string
  brandSoft2: string
  brandMid35: string
  brandMid62: string
  surface2: string
  accent: string
  sky: string
  amber: string
  rose: string
  teal: string
  ink1: string
  ink2: string
  ink3: string
  border: string
  borderStrong: string
  surface: string
}

const LIGHT: ZhiweiThemePalette = {
  brand: '#0B7A5E',
  brandSoft2: 'rgba(11,122,94,.16)',
  brandMid35: 'rgba(11,122,94,.35)',
  brandMid62: 'rgba(11,122,94,.62)',
  surface2: '#F7F8FA',
  accent: '#F4570A',
  sky: '#3E8DDD',
  amber: '#D08700',
  rose: '#DE5A63',
  teal: '#2FA79B',
  ink1: '#171923',
  ink2: '#565D6D',
  ink3: '#8A91A0',
  border: 'rgba(23,25,35,.08)',
  borderStrong: 'rgba(23,25,35,.15)',
  surface: '#FFFFFF',
}

const DARK: ZhiweiThemePalette = {
  brand: '#45C8A0',
  brandSoft2: 'rgba(69,200,160,.22)',
  brandMid35: 'rgba(69,200,160,.32)',
  brandMid62: 'rgba(69,200,160,.58)',
  surface2: '#1A1E29',
  accent: '#F4570A',
  sky: '#6BB2F2',
  amber: '#E5B567',
  rose: '#F08088',
  teal: '#4FC3B4',
  ink1: '#E8EAF2',
  ink2: '#9CA3B2',
  ink3: '#6B7280',
  border: 'rgba(255,255,255,.08)',
  borderStrong: 'rgba(255,255,255,.17)',
  surface: '#14171F',
}

function buildZhiweiTheme(p: ZhiweiThemePalette) {
  return {
    color: [p.brand, p.accent, p.sky, p.amber, p.rose, p.teal],
    backgroundColor: 'transparent',
    textStyle: {
      fontFamily: 'Inter, "Noto Sans SC", "PingFang SC", "Microsoft YaHei UI", sans-serif',
    },
    categoryAxis: {
      axisLine: { lineStyle: { color: p.borderStrong } },
      axisTick: { lineStyle: { color: p.borderStrong } },
      axisLabel: { color: p.ink3 },
      splitLine: { show: false },
    },
    valueAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: p.ink3 },
      splitLine: { lineStyle: { color: p.border, type: 'dashed' as const } },
    },
    axisPointer: {
      lineStyle: { color: p.borderStrong },
      crossStyle: { color: p.borderStrong },
    },
    tooltip: {
      backgroundColor: p.surface,
      borderColor: p.borderStrong,
      borderWidth: 1,
      textStyle: { color: p.ink1, fontSize: 12.5 },
      extraCssText: 'border-radius:10px; box-shadow:0 16px 40px -14px rgba(18,22,33,.2); padding:8px 12px;',
    },
    legend: {
      textStyle: { color: p.ink2, fontSize: 12 },
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
    },
    heatmapHeatColorStops: [p.surface2, p.brandSoft2, p.brandMid35, p.brandMid62, p.brand],
  }
}

/** heatmap 五档青色阶梯(按当前主题名取值) */
export function heatVisualMapColors(theme: 'light' | 'dark' = 'light'): string[] {
  const p = theme === 'dark' ? DARK : LIGHT
  return [p.surface2, p.brandSoft2, p.brandMid35, p.brandMid62, p.brand]
}

registerTheme('zhiwei-light', buildZhiweiTheme(LIGHT))
registerTheme('zhiwei-dark', buildZhiweiTheme(DARK))

/** 按当前 data-theme 取 ECharts 主题名 */
export function currentChartTheme(): 'zhiwei-light' | 'zhiwei-dark' {
  if (typeof document === 'undefined') return 'zhiwei-light'
  return document.documentElement.getAttribute('data-theme') === 'dark'
    ? 'zhiwei-dark'
    : 'zhiwei-light'
}

export { graphic, init }
export type { ECharts } from 'echarts/core'
