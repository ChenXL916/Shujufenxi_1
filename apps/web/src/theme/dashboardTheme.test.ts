import { describe, expect, test } from 'vitest'
import { dashboardTheme } from './dashboardTheme'
import { CHART_THEME_NAME, chartPalette } from './chartTheme'

function luminance(hex: string): number {
  const channels = [
    Number.parseInt(hex.slice(1, 3), 16) / 255,
    Number.parseInt(hex.slice(3, 5), 16) / 255,
    Number.parseInt(hex.slice(5, 7), 16) / 255,
  ] as const
  const [red, green, blue] = channels.map((channel) =>
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
  ) as [number, number, number]
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue
}

function contrastRatio(foreground: string, background: string): number {
  const foregroundLuminance = luminance(foreground)
  const backgroundLuminance = luminance(background)
  const lighter = Math.max(foregroundLuminance, backgroundLuminance)
  const darker = Math.min(foregroundLuminance, backgroundLuminance)
  return (lighter + 0.05) / (darker + 0.05)
}

describe('Index-inspired warm BI design system', () => {
  test('maps the canonical light tokens into Ant Design', () => {
    expect(dashboardTheme.token).toMatchObject({
      colorBgBase: '#F7F6F2',
      colorBgContainer: '#FFFFFF',
      colorBgElevated: '#FFFFFF',
      colorPrimary: '#171716',
      colorInfo: '#4565D4',
      colorSuccess: '#1E7A54',
      colorError: '#B83C3C',
      colorWarning: '#9B5F0E',
      colorText: '#171716',
      colorTextSecondary: '#5F5C56',
      colorTextTertiary: '#706D67',
      colorBorder: '#8D8981',
    })
  })

  test('maps one fast, normal and slow motion scale into Ant Design', () => {
    expect(dashboardTheme.token).toMatchObject({
      motionDurationFast: '0.12s',
      motionDurationMid: '0.18s',
      motionDurationSlow: '0.26s',
    })
  })

  test('uses one named ECharts theme and accessible data palette', () => {
    expect(CHART_THEME_NAME).toBe('index-warm-bi')
    expect(chartPalette).toEqual(
      expect.arrayContaining(['#C44720', '#4565D4', '#6656CE', '#9B5F0E', '#1E7A54']),
    )
  })

  test('keeps text and data palette colors at WCAG AA contrast on warm and white surfaces', () => {
    const semanticText = ['#171716', '#5F5C56', '#706D67']
    const surfaces = ['#F7F6F2', '#FFFFFF', '#FBFAF7']
    for (const foreground of [...semanticText, ...chartPalette]) {
      for (const background of surfaces) {
        expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(4.5)
      }
    }
    expect(contrastRatio('#8D8981', '#FFFFFF')).toBeGreaterThanOrEqual(3)
  })
})
