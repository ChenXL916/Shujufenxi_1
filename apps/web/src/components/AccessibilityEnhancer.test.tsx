import { render, waitFor } from '@testing-library/react'
import { AccessibilityEnhancer } from './AccessibilityEnhancer'

test('为Ant分页与Tabs更多按钮补齐可访问名称和提示', async () => {
  const { container } = render(
    <>
      <AccessibilityEnhancer />
      <button className="ant-pagination-item-link">
        <span className="anticon" />
      </button>
      <button className="ant-tabs-nav-more">
        <span className="anticon" />
      </button>
    </>,
  )

  await waitFor(() => {
    expect(container.querySelector('.ant-pagination-item-link')).toHaveAttribute(
      'aria-label',
      '翻页',
    )
    expect(container.querySelector('.ant-tabs-nav-more')).toHaveAttribute(
      'aria-label',
      '更多标签页',
    )
  })
  expect(container.querySelector('.ant-tabs-nav-more')).toHaveAttribute('title', '更多标签页')
})
