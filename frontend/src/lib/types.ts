export type LinkStatus = 'ok' | 'pending' | 'blocked' | 'parse_error' | 'http_error'

export interface WindowStats {
  min: number
  max: number
  avg: number
  count: number
}

export interface LinkStats {
  d30: WindowStats | null
  d90: WindowStats | null
  d180: WindowStats | null
  d365: WindowStats | null
  all: WindowStats | null
  all_time_low: { price: number; ts: string } | null
  change_30d_pct: number | null
}

export interface Link {
  id: string
  product_id: string
  url: string
  shop: string
  title?: string
  currency: string
  last_price?: number
  last_in_stock?: boolean
  last_checked?: string
  last_attempt?: string
  last_status: LinkStatus
  last_error?: string
  lowest_price?: number
  created_at: string
  stats?: LinkStats
}

export interface Product {
  id: string
  name: string
  image_url?: string
  target_price?: number
  tags?: string[]
  created_at: string
  updated_at: string
  links: Link[]
}

export interface PricePoint {
  ts: string
  price: number
  in_stock?: boolean | null
}

export interface ProductSummary {
  id: string
  name: string
  image_url?: string
  target_price?: number
  tags?: string[]
  created_at: string
  link_count: number
  best: { link_id: string; shop: string; price: number; currency: string; in_stock?: boolean } | null
  change_30d_pct: number | null
  sparkline: PricePoint[]
  status: LinkStatus | null
}

export interface History {
  link_id: string
  currency: string
  points: PricePoint[]
}

export type RangeDays = 30 | 90 | 180 | 365 | 0

export interface ChartSeries {
  id: string
  label: string
  /** Fixed color slot: follows the link, never its rank. */
  slot: number
  currency: string
  points: PricePoint[]
}
