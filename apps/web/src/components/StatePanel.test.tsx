import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'
import { EmptyPanel, ErrorPanel, LoadingPanel } from './StatePanel'

describe('StatePanel', () => {
  test('加载态使用稳定容器并暴露忙碌状态', () => {
    render(<LoadingPanel />)
    const panel = screen.getByRole('status')
    expect(panel).toHaveClass('state-panel', 'state-panel-loading')
    expect(panel).toHaveAttribute('aria-busy', 'true')
  })

  test('空态与错误态复用稳定容器且错误可重试', () => {
    const retry = vi.fn()
    const { rerender } = render(<EmptyPanel />)
    expect(screen.getByRole('status')).toHaveClass('state-panel-empty')

    rerender(<ErrorPanel onRetry={retry} />)
    fireEvent.click(screen.getByRole('button', { name: /重\s*试/ }))
    expect(retry).toHaveBeenCalledOnce()
    expect(screen.getByText('数据加载失败').closest('.state-panel')).toHaveClass(
      'state-panel-error',
    )
  })
})
