/** Minimal History-API router: the app has three screens. */
export const route = $state({ path: window.location.pathname, search: window.location.search })

function sync(): void {
  route.path = window.location.pathname
  route.search = window.location.search
}

export function navigate(to: string, replace = false): void {
  if (replace) window.history.replaceState({}, '', to)
  else window.history.pushState({}, '', to)
  sync()
  if (!replace) window.scrollTo(0, 0)
}

/** Updates the query string of the current page without a history entry. */
export function setQuery(params: Record<string, string | null>): void {
  const query = new URLSearchParams(window.location.search)
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value)
    else query.delete(key)
  }
  const search = query.toString()
  navigate(`${window.location.pathname}${search ? `?${search}` : ''}`, true)
}

window.addEventListener('popstate', sync)

/** onclick handler for internal <a href> links. */
export function link(event: MouseEvent): void {
  if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return
  const anchor = event.currentTarget as HTMLAnchorElement
  event.preventDefault()
  navigate(anchor.getAttribute('href') ?? '/')
}
