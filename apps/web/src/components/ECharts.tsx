import { useEffect, useMemo, useRef } from 'react'
import ReactEChartsCore from 'echarts-for-react/lib/core'
import type { EChartsReactProps } from 'echarts-for-react/lib/types'
import * as echarts from 'echarts/core'
import type { EChartsCoreOption, EChartsType } from 'echarts/core'
import { LineChart, BarChart, CandlestickChart } from 'echarts/charts'
import {
  AriaComponent,
  DataZoomComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  TransformComponent,
} from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import { CHART_THEME_NAME, dashboardChartTheme } from '@/theme/chartTheme'
import { useMediaQuery } from '@/hooks/useMediaQuery'

echarts.use([
  AriaComponent,
  LineChart,
  BarChart,
  CandlestickChart,
  DataZoomComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  MarkPointComponent,
  TitleComponent,
  ToolboxComponent,
  TooltipComponent,
  TransformComponent,
  CanvasRenderer,
])

echarts.registerTheme(CHART_THEME_NAME, dashboardChartTheme)

type Props = Omit<EChartsReactProps, 'echarts' | 'option' | 'onChartReady'> & {
  option: EChartsCoreOption
  onChartReady?: (instance: EChartsType) => void
  motion?: 'default' | 'focus'
}

export function ECharts({ option, onChartReady, motion = 'default', ...props }: Props) {
  const reducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)')
  const frameRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<EChartsType | null>(null)
  const resizeFrameRef = useRef<number | null>(null)
  const enterDuration = motion === 'focus' ? 460 : 280
  const updateDuration = motion === 'focus' ? 320 : 240
  const mergedOption = useMemo<EChartsCoreOption>(
    () => ({
      ...option,
      animationDuration: reducedMotion ? 0 : enterDuration,
      animationDurationUpdate: reducedMotion ? 0 : updateDuration,
      animationEasing: motion === 'focus' ? 'quarticOut' : 'cubicOut',
      animationEasingUpdate: 'cubicOut',
    }),
    [enterDuration, motion, option, reducedMotion, updateDuration],
  )

  const scheduleResize = () => {
    if (resizeFrameRef.current !== null) cancelAnimationFrame(resizeFrameRef.current)
    resizeFrameRef.current = requestAnimationFrame(() => {
      resizeFrameRef.current = null
      chartRef.current?.resize()
    })
  }

  const handleChartReady = (instance: EChartsType) => {
    chartRef.current = instance
    scheduleResize()
    onChartReady?.(instance)
  }

  useEffect(() => {
    const frame = frameRef.current
    if (!frame) return
    const observer = new ResizeObserver(scheduleResize)
    observer.observe(frame)
    const shell = document.querySelector('.app-shell')
    shell?.addEventListener('transitionend', scheduleResize)
    return () => {
      observer.disconnect()
      shell?.removeEventListener('transitionend', scheduleResize)
      if (resizeFrameRef.current !== null) cancelAnimationFrame(resizeFrameRef.current)
      resizeFrameRef.current = null
      chartRef.current = null
    }
  }, [])

  return (
    <div
      ref={frameRef}
      className="echarts-resize-frame echarts-accessible-frame"
      data-chart-resize-observer="true"
      data-reduced-motion={String(reducedMotion)}
      data-motion={motion}
    >
      <ReactEChartsCore
        echarts={echarts}
        option={mergedOption}
        theme={CHART_THEME_NAME}
        notMerge
        lazyUpdate
        onChartReady={handleChartReady}
        {...props}
      />
    </div>
  )
}
