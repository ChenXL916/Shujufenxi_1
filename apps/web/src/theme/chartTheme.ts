export const CHART_THEME_NAME = 'index-warm-bi'

export const chartPalette = ['#C44720', '#4565D4', '#6656CE', '#9B5F0E', '#1E7A54', '#B83C3C']

export const chartComparisonPalette = [
  '#4565D4',
  '#6656CE',
  '#9B5F0E',
  '#2F779F',
  '#317961',
  '#A55363',
]

export const chartSemanticColors = {
  canvas: '#FFFFFF',
  current: '#C44720',
  comparison: '#4565D4',
  target: '#706D67',
  axis: '#DCD8D0',
  axisLabel: '#706D67',
  grid: '#EEEAE3',
  positive: '#1E7A54',
  negative: '#B83C3C',
  warning: '#9B5F0E',
  muted: '#706D67',
  onStatus: '#FFFFFF',
} as const

export const chartStatusColors = {
  critical: chartSemanticColors.negative,
  warning: chartSemanticColors.warning,
  positive: chartSemanticColors.positive,
  info: chartSemanticColors.comparison,
  improving: chartSemanticColors.current,
  normal: chartSemanticColors.muted,
  neutral: chartSemanticColors.muted,
} as const

export const dashboardChartTheme = {
  color: chartPalette,
  backgroundColor: 'transparent',
  textStyle: {
    color: '#5F5C56',
    fontFamily: 'Inter, "SF Pro Display", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
  },
  title: {
    textStyle: { color: '#171716', fontWeight: 650 },
    subtextStyle: { color: '#706D67' },
  },
  line: {
    itemStyle: { borderWidth: 1 },
    lineStyle: { width: 2 },
    symbolSize: 6,
    symbol: 'circle',
    smooth: false,
  },
  bar: {
    itemStyle: { borderRadius: [4, 4, 0, 0] },
  },
  candlestick: {
    itemStyle: {
      color: chartSemanticColors.positive,
      color0: chartSemanticColors.negative,
      borderColor: chartSemanticColors.positive,
      borderColor0: chartSemanticColors.negative,
    },
  },
  categoryAxis: {
    axisLine: { show: true, lineStyle: { color: chartSemanticColors.axis } },
    axisTick: { show: false },
    axisLabel: { color: chartSemanticColors.axisLabel },
    splitLine: { show: false },
    splitArea: { show: false },
  },
  valueAxis: {
    axisLine: { show: false, lineStyle: { color: chartSemanticColors.axis } },
    axisTick: { show: false },
    axisLabel: { color: chartSemanticColors.axisLabel },
    splitLine: { show: true, lineStyle: { color: chartSemanticColors.grid, type: 'dashed' } },
    splitArea: { show: false },
  },
  legend: {
    textStyle: { color: '#5F5C56' },
    pageTextStyle: { color: '#706D67' },
    pageIconColor: '#C44720',
    pageIconInactiveColor: '#706D67',
  },
  tooltip: {
    backgroundColor: 'rgba(255,255,255,.98)',
    borderColor: '#E2DED6',
    borderWidth: 1,
    textStyle: { color: '#171716' },
    extraCssText:
      'max-width:min(360px,calc(100vw - 24px));white-space:normal;overflow-wrap:anywhere;border-radius:12px;box-shadow:0 20px 60px rgba(35,31,24,.14);',
  },
  dataZoom: {
    backgroundColor: '#FAF9F6',
    dataBackgroundColor: '#E2DED6',
    fillerColor: 'rgba(196,71,32,.12)',
    handleColor: '#C44720',
    handleSize: '90%',
    textStyle: { color: '#706D67' },
    borderColor: '#E2DED6',
  },
  toolbox: {
    iconStyle: { borderColor: '#706D67' },
    emphasis: { iconStyle: { borderColor: '#C44720' } },
  },
}
