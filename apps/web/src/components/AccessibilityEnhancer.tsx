import { useEffect } from 'react'

function labelAntDesignControls(root: ParentNode) {
  root.querySelectorAll<HTMLElement>('.ant-pagination-item-link').forEach((control) => {
    const parent = control.closest('.ant-pagination-prev, .ant-pagination-next')
    const label = parent?.classList.contains('ant-pagination-prev')
      ? '上一页'
      : parent?.classList.contains('ant-pagination-next')
        ? '下一页'
        : '翻页'
    if (!control.getAttribute('aria-label')) control.setAttribute('aria-label', label)
    if (!control.getAttribute('title')) control.setAttribute('title', label)
  })

  root.querySelectorAll<HTMLElement>('.ant-tabs-nav-more').forEach((control) => {
    control.setAttribute('aria-label', '更多标签页')
    control.setAttribute('title', '更多标签页')
  })

  root.querySelectorAll<HTMLElement>('.ant-picker-clear').forEach((control) => {
    control.setAttribute('aria-label', '清除日期')
    control.setAttribute('title', '清除日期')
  })

  root.querySelectorAll<HTMLElement>('.ant-table-thead th').forEach((header) => {
    const label = header.textContent?.replace(/\s+/g, ' ').trim()
    if (label && !header.getAttribute('title')) header.setAttribute('title', label)
  })

  root.querySelectorAll<HTMLElement>('.ant-select-selection-item').forEach((item) => {
    const label = item.getAttribute('title') ?? item.textContent?.replace(/\s+/g, ' ').trim()
    if (label) item.setAttribute('title', label)
  })
}

export function AccessibilityEnhancer() {
  useEffect(() => {
    let frame = 0
    const apply = () => {
      window.cancelAnimationFrame(frame)
      frame = window.requestAnimationFrame(() => labelAntDesignControls(document))
    }
    apply()
    const observer = new MutationObserver(apply)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => {
      observer.disconnect()
      window.cancelAnimationFrame(frame)
    }
  }, [])

  return null
}
