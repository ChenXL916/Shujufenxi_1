import { render, screen } from '@testing-library/react'
import type { EChartsCoreOption } from 'echarts/core'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { ECharts } from './ECharts'

vi.mock('echarts-for-react/lib/core', () => ({
  default: ({ option }: { option: EChartsCoreOption }) => (
    <pre data-testid="echarts-option">{JSON.stringify(option)}</pre>
  ),
}))

const originalMatchMedia = window.matchMedia

afterEach(() => {
  Object.defineProperty(window, 'matchMedia', { writable: true, value: originalMatchMedia })
})

function renderedOption(): EChartsCoreOption {
  return JSON.parse(screen.getByTestId('echarts-option').textContent ?? '{}') as EChartsCoreOption
}

describe('ECharts Motion与尺寸监听', () => {
  test('共享Motion覆盖页面硬编码时长', () => {
    render(<ECharts option={{ animationDuration: 999 }} />)
    expect(renderedOption().animationDuration).toBe(280)
    expect(renderedOption().animationDurationUpdate).toBe(240)
    expect(screen.getByTestId('echarts-option').parentElement).toHaveAttribute(
      'data-chart-resize-observer',
      'true',
    )
  })

  test('Reduce Motion强制禁用图表动画', () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
    render(<ECharts option={{ animationDuration: 999, animationDurationUpdate: 999 }} />)
    expect(renderedOption().animationDuration).toBe(0)
    expect(renderedOption().animationDurationUpdate).toBe(0)
  })
})
