import { formatDistanceToNowStrict } from 'date-fns'
import type { LinkStatus } from './types'

const moneyFormats = new Map<string, Intl.NumberFormat>()

export function money(value: number | null | undefined, currency = 'EUR'): string {
  if (value === null || value === undefined) return '–'
  let format = moneyFormats.get(currency)
  if (!format) {
    try {
      format = new Intl.NumberFormat('de-DE', { style: 'currency', currency })
    } catch {
      format = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    }
    moneyFormats.set(currency, format)
  }
  return format.format(value)
}

export function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return ''
  const sign = value > 0 ? '+' : value < 0 ? '−' : '±'
  return `${sign}${Math.abs(value).toLocaleString('de-DE', { maximumFractionDigits: 1 })} %`
}

export function ago(ts: string | null | undefined): string {
  if (!ts) return 'never'
  return `${formatDistanceToNowStrict(new Date(ts))} ago`
}

export function dateTime(ts: string | null | undefined): string {
  if (!ts) return '–'
  return new Date(ts).toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' })
}

export const statusLabel: Record<LinkStatus, string> = {
  ok: 'OK',
  pending: 'Pending',
  blocked: 'Blocked',
  parse_error: 'No price found',
  http_error: 'Unreachable',
}

/** Series colors in fixed slot order (validated palette); never cycled. */
export const SERIES_LIGHT = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948']
export const SERIES_DARK = ['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767']
export const OVERFLOW_SERIES = '#898781'
