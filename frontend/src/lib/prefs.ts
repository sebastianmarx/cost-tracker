/** Per-browser UI preferences. Storage can be unavailable (private mode). */
export function loadPref<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = window.localStorage.getItem(`cost-tracker.${key}`)
    return allowed.includes(value as T) ? (value as T) : fallback
  } catch {
    return fallback
  }
}

export function savePref(key: string, value: string): void {
  try {
    window.localStorage.setItem(`cost-tracker.${key}`, value)
  } catch {
    // ignore
  }
}
