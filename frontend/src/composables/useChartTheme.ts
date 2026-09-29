/* ECharts 主题跟随引擎(REFACTOR_PLAN.md §7.2)
   - chartVar(name):实时读取当前主题下的 CSS 变量值(替代旧的 getCSSVar 快照)
   - bindChart(chart, buildOptions):登记实例;ui.theme 变化时以 notMerge 重绘,
     不 dispose 重建,避免闪烁
   - disposeAll:onBeforeUnmount 统一释放,防内存泄漏 */
import { onBeforeUnmount, watch, type Ref } from 'vue'
import type { ECharts, EChartsOption } from 'echarts'
import { useUiStore } from '@/stores/uiStore'

/** 读取指定 CSS 变量的当前值(空白剔除,保证 ECharts 拿到干净色值) */
export function chartVar(name: string, fallback = 'transparent'): string {
  if (typeof window === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

type ChartEntry = {
  chart: ECharts
  build: () => EChartsOption
}

export interface ChartThemeBinding {
  bindChart: (chart: ECharts, build: () => EChartsOption) => void
  /** 手动触发一次全部重绘(数据刷新后也可用) */
  refreshAll: () => void
  disposeAll: () => void
}

export function useChartTheme(themeSource?: Ref<string>): ChartThemeBinding {
  const ui = useUiStore()
  const entries: ChartEntry[] = []

  function redraw(entry: ChartEntry) {
    if (entry.chart.isDisposed?.()) return
    entry.chart.setOption(entry.build(), true)
  }

  function bindChart(chart: ECharts, build: () => EChartsOption) {
    const entry: ChartEntry = { chart, build }
    entries.push(entry)
  }

  function refreshAll() {
    entries.forEach(redraw)
  }

  function disposeAll() {
    entries.forEach((entry) => {
      if (!entry.chart.isDisposed?.()) entry.chart.dispose()
    })
    entries.length = 0
  }

  watch(
    () => themeSource?.value ?? ui.theme,
    () => {
      // 等待 data-theme 挂载后的下一帧再取色,避免读到旧值
      requestAnimationFrame(refreshAll)
    },
  )

  onBeforeUnmount(disposeAll)

  return { bindChart, refreshAll, disposeAll }
}

/* 统一动画参数(§7.2:每图 900ms cubicOut,折线从左向右生长) */
export const chartAnimation = {
  animationDuration: 900,
  animationEasing: 'cubicOut',
  animationDurationUpdate: 400,
} as const
