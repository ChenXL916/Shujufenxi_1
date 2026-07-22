export function restoreFocusAfterOverlayClose(target: HTMLElement | null): number {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  return window.setTimeout(
    () => {
      if (target?.isConnected) target.focus({ preventScroll: true })
    },
    reducedMotion ? 0 : 300,
  )
}
