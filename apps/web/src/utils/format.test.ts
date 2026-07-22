import type { TimelineSeries } from '@/types/dashboard'
import { formatMetric, formatRoiChange, groupSeriesByUnit } from './format'

test('formats compatible business units', () => {
  expect(formatMetric('0.0968', 'percent')).toBe('9.68%')
  expect(formatMetric('3', 'ratio')).toBe('3.00')
  expect(formatMetric(null, 'currency')).toBe('—')
})

test('splits chart series by unit', () => {
  const series = [
    { metric_key: 'roi', name: 'ROI', unit: 'ratio', axis_group: 'ratio', data: [3] },
    { metric_key: 'amount', name: '金额', unit: 'currency', axis_group: 'currency', data: [100] },
  ] satisfies TimelineSeries[]
  expect(Object.keys(groupSeriesByUnit(series))).toEqual(['ratio', 'currency'])
})

test('formats ROI changes without treating delayed data as zero', () => {
  expect(formatRoiChange(null, null, null)).toBe('待当前实绩')
  expect(formatRoiChange('1.3', '-0.7', '-35')).toBe('下降 0.70（35.00%）')
  expect(formatRoiChange('2.7', '0.7', '35')).toBe('提升 0.70（35.00%）')
  expect(formatRoiChange('2', '0', '0')).toBe('持平 0.00（0.00%）')
})
