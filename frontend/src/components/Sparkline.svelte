<script lang="ts">
  import type { PricePoint } from '../lib/types'

  let { points, width = 120, height = 36 }: { points: PricePoint[]; width?: number; height?: number } = $props()

  const path = $derived.by(() => {
    if (points.length < 2) return ''
    const xs = points.map((p) => new Date(p.ts).getTime())
    const ys = points.map((p) => p.price)
    const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
    const [y0, y1] = [Math.min(...ys), Math.max(...ys)]
    const pad = 3
    const sx = (x: number) => pad + ((x - x0) / (x1 - x0 || 1)) * (width - 2 * pad)
    const sy = (y: number) => (y1 === y0 ? height / 2 : pad + (1 - (y - y0) / (y1 - y0)) * (height - 2 * pad))
    return points.map((p, i) => `${i ? 'L' : 'M'}${sx(xs[i]).toFixed(1)},${sy(p.price).toFixed(1)}`).join(' ')
  })
</script>

{#if path}
  <svg {width} {height} viewBox="0 0 {width} {height}" role="img" aria-label="Price trend over the last 30 days">
    <path d={path} fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
  </svg>
{:else}
  <span class="muted small">Not enough data yet</span>
{/if}

<style>
  svg {
    display: block;
    overflow: visible;
  }
  .small {
    font-size: 12px;
  }
</style>
