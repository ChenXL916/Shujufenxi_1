import { useEffect, useState } from 'react'

export function useMediaQuery(query: string): boolean {
  const getMatches = () =>
    typeof window === 'undefined' ? false : window.matchMedia(query).matches
  const [matches, setMatches] = useState(getMatches)

  useEffect(() => {
    const mediaQuery = window.matchMedia(query)
    const update = () => setMatches(mediaQuery.matches)
    update()
    mediaQuery.addEventListener('change', update)
    return () => mediaQuery.removeEventListener('change', update)
  }, [query])

  return matches
}
