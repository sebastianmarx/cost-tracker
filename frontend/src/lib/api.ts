import { accessToken, forceRefresh, signIn } from './auth'
import type { History, Link, Product, ProductSummary, RangeDays } from './types'

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message)
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = await accessToken()
  if (!token) {
    await signIn()
    throw new ApiError(401, 'unauthorized', 'Signing in…')
  }
  const send = (t: string) =>
    fetch(`/api${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${t}`,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  let response = await send(token)
  if (response.status === 401) {
    // Try a silent refresh first; only fall back to the login page if that fails.
    const refreshed = await forceRefresh()
    if (refreshed) response = await send(refreshed.access_token)
  }
  if (response.status === 401) {
    await signIn()
    throw new ApiError(401, 'unauthorized', 'Session expired, signing in again…')
  }
  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(response.status, data.error ?? 'error', data.message ?? `HTTP ${response.status}`)
  }
  return data as T
}

export const api = {
  listProducts: () => request<ProductSummary[]>('GET', '/products'),
  getProduct: (id: string) => request<Product>('GET', `/products/${id}`),
  createProduct: (body: { name: string; target_price?: number | null; tags?: string[]; links: string[] }) =>
    request<Product>('POST', '/products', body),
  updateProduct: (id: string, body: { name?: string; target_price?: number | null; tags?: string[] }) =>
    request<Product>('PUT', `/products/${id}`, body),
  deleteProduct: (id: string) => request<void>('DELETE', `/products/${id}`),
  addLink: (productId: string, url: string) => request<Link>('POST', `/products/${productId}/links`, { url }),
  deleteLink: (productId: string, linkId: string) =>
    request<void>('DELETE', `/products/${productId}/links/${linkId}`),
  history: (linkId: string, days: RangeDays) => request<History>('GET', `/links/${linkId}/history?days=${days}`),
  refreshLink: (linkId: string) => request<Link>('POST', `/links/${linkId}/refresh`),
  refreshAll: () => request<{ queued: number }>('POST', '/refresh'),
}
