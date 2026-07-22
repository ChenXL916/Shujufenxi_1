import { render, screen } from '@testing-library/react'
import { Button } from 'antd'
import { PageHeader } from './PageHeader'

test('长页面标题保持完整且操作区使用独立的响应式容器', () => {
  const { container } = render(
    <PageHeader
      title="主播场控时间汇总透视表"
      description="用于验证标题不会被右侧操作区挤压或错误省略。"
      actions={
        <>
          <Button>刷新</Button>
          <Button>导出数据</Button>
        </>
      }
    />,
  )

  expect(screen.getByRole('heading', { name: '主播场控时间汇总透视表' })).toHaveTextContent(
    '主播场控时间汇总透视表',
  )
  expect(container.querySelector('.page-heading-copy')).toBeInTheDocument()
  expect(container.querySelector('.responsive-actions')).toHaveAttribute('aria-label', '页面操作')
})
