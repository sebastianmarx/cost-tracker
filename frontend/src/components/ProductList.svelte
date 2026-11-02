<script lang="ts">
  import { money, pct } from '../lib/format'
  import { link, navigate } from '../lib/router.svelte'
  import type { ProductSummary } from '../lib/types'
  import Sparkline from './Sparkline.svelte'
  import StatusBadge from './StatusBadge.svelte'
  import TagList from './TagList.svelte'

  type SortKey = 'name' | 'price' | 'change' | 'target'

  let {
    products,
    sort = $bindable('name'),
    dir = $bindable('asc'),
  }: { products: ProductSummary[]; sort?: SortKey; dir?: 'asc' | 'desc' } = $props()

  /** Distance to the target in percent; negative means the target is reached. */
  function targetGap(p: ProductSummary): number | null {
    if (!p.best || p.target_price === undefined) return null
    return ((p.best.price - p.target_price) / p.target_price) * 100
  }

  const value: Record<SortKey, (p: ProductSummary) => string | number | null> = {
    name: (p) => p.name.toLocaleLowerCase('de-DE'),
    price: (p) => p.best?.price ?? null,
    change: (p) => p.change_30d_pct,
    target: targetGap,
  }

  const sorted = $derived(
    [...products].sort((a, b) => {
      const va = value[sort](a)
      const vb = value[sort](b)
      // Missing values always sink to the bottom, whatever the direction.
      if (va === null && vb === null) return 0
      if (va === null) return 1
      if (vb === null) return -1
      const cmp = typeof va === 'string' ? va.localeCompare(vb as string, 'de-DE') : va - (vb as number)
      return dir === 'asc' ? cmp : -cmp
    }),
  )

  function sortBy(key: SortKey) {
    if (sort === key) dir = dir === 'asc' ? 'desc' : 'asc'
    else {
      sort = key
      dir = 'asc'
    }
  }

  function ariaSort(key: SortKey): 'ascending' | 'descending' | 'none' {
    return sort === key ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'
  }
</script>

{#snippet header(key: SortKey, label: string, align = '')}
  <th aria-sort={ariaSort(key)} class={align}>
    <button type="button" onclick={() => sortBy(key)}>
      {label}
      <span class="arrow" aria-hidden="true">{sort === key ? (dir === 'asc' ? '▲' : '▼') : ''}</span>
    </button>
  </th>
{/snippet}

<div class="card wrap">
  <table>
    <thead>
      <tr>
        {@render header('name', 'Product')}
        {@render header('price', 'Best price', 'r')}
        {@render header('change', '30 days', 'r')}
        {@render header('target', 'Target', 'r hide-sm')}
        <th class="hide-sm">Trend</th>
      </tr>
    </thead>
    <tbody>
      {#each sorted as product (product.id)}
        {@const gap = targetGap(product)}
        <tr onclick={() => navigate(`/products/${product.id}`)}>
          <td>
            <div class="product">
              <div class="thumb">
                {#if product.image_url}
                  <img src={product.image_url} alt="" loading="lazy" referrerpolicy="no-referrer" />
                {:else}
                  <span aria-hidden="true">🛒</span>
                {/if}
              </div>
              <div class="name">
                <a href="/products/{product.id}" onclick={link}>{product.name}</a>
                <div class="meta">
                  <span class="muted">{product.link_count} {product.link_count === 1 ? 'shop' : 'shops'}</span>
                  {#if product.status && product.status !== 'ok'}<StatusBadge status={product.status} />{/if}
                  <TagList tags={product.tags} />
                </div>
              </div>
            </div>
          </td>
          <td class="r num">
            {#if product.best}
              <div class="price">{money(product.best.price, product.best.currency)}</div>
              <div class="muted small">{product.best.shop}</div>
            {:else}
              <span class="muted">–</span>
            {/if}
          </td>
          <td class="r num">
            {#if product.change_30d_pct !== null && product.change_30d_pct !== 0}
              <span class={product.change_30d_pct < 0 ? 'good' : 'bad'}>
                {product.change_30d_pct < 0 ? '▼' : '▲'}
                {pct(product.change_30d_pct)}
              </span>
            {:else}
              <span class="muted">–</span>
            {/if}
          </td>
          <td class="r num hide-sm">
            {#if product.target_price !== undefined}
              <div>{money(product.target_price, product.best?.currency)}</div>
              {#if gap !== null}
                <div class="small {gap <= 0 ? 'good' : 'muted'}">
                  {gap <= 0 ? '🎯 reached' : `${pct(gap)} above`}
                </div>
              {/if}
            {:else}
              <span class="muted">–</span>
            {/if}
          </td>
          <td class="hide-sm"><Sparkline points={product.sparkline} width={100} height={30} /></td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .wrap {
    overflow-x: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }
  th {
    text-align: left;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 10px 14px;
    border-bottom: 1px solid var(--grid);
    white-space: nowrap;
  }
  th button {
    all: unset;
    cursor: pointer;
    display: inline-flex;
    gap: 4px;
    align-items: center;
  }
  th button:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  th button:hover {
    color: var(--ink);
  }
  .arrow {
    font-size: 9px;
    min-width: 9px;
  }
  td {
    padding: 10px 14px;
    border-bottom: 1px solid var(--grid);
    vertical-align: middle;
  }
  tbody tr {
    cursor: pointer;
  }
  tbody tr:hover {
    background: var(--surface-2);
  }
  tbody tr:last-child td {
    border-bottom: 0;
  }
  .r {
    text-align: right;
    white-space: nowrap;
  }
  th.r button {
    flex-direction: row-reverse;
  }
  .product {
    display: flex;
    gap: 12px;
    align-items: center;
    min-width: 220px;
  }
  .thumb {
    width: 40px;
    height: 40px;
    border-radius: 8px;
    background: #fff;
    border: 1px solid var(--border);
    display: grid;
    place-items: center;
    flex-shrink: 0;
    overflow: hidden;
    font-size: 18px;
  }
  .thumb img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
  .name a {
    font-weight: 600;
    text-decoration: none;
  }
  .name a:hover {
    text-decoration: underline;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    margin-top: 2px;
    font-size: 12px;
  }
  .price {
    font-weight: 700;
  }
  .small {
    font-size: 12px;
  }
  @media (max-width: 640px) {
    .hide-sm {
      display: none;
    }
  }
</style>
