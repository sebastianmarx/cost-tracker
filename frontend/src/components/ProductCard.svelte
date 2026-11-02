<script lang="ts">
  import { money, pct } from '../lib/format'
  import { link } from '../lib/router.svelte'
  import type { ProductSummary } from '../lib/types'
  import Sparkline from './Sparkline.svelte'
  import StatusBadge from './StatusBadge.svelte'
  import TagList from './TagList.svelte'

  let { product }: { product: ProductSummary } = $props()

  const belowTarget = $derived(
    product.best && product.target_price !== undefined && product.best.price <= product.target_price,
  )
</script>

<a class="card product" href="/products/{product.id}" onclick={link}>
  <div class="top">
    <div class="thumb">
      {#if product.image_url}
        <img src={product.image_url} alt="" loading="lazy" referrerpolicy="no-referrer" />
      {:else}
        <span aria-hidden="true">🛒</span>
      {/if}
    </div>
    <div class="title">
      <h3>{product.name}</h3>
      <div class="muted small">
        {product.link_count}
        {product.link_count === 1 ? 'shop' : 'shops'}
        {#if product.status && product.status !== 'ok'}
          · <StatusBadge status={product.status} />
        {/if}
      </div>
      {#if product.tags?.length}<div class="tags"><TagList tags={product.tags} /></div>{/if}
    </div>
  </div>

  <div class="bottom">
    <div>
      {#if product.best}
        <div class="price num">{money(product.best.price, product.best.currency)}</div>
        <div class="small secondary">
          at {product.best.shop}
          {#if product.change_30d_pct !== null && product.change_30d_pct !== 0}
            <span class={product.change_30d_pct < 0 ? 'good' : 'bad'}>
              {product.change_30d_pct < 0 ? '▼' : '▲'}
              {pct(product.change_30d_pct)}
            </span>
            <span class="muted">30d</span>
          {/if}
        </div>
      {:else}
        <div class="price muted">–</div>
        <div class="small muted">No price yet</div>
      {/if}
      {#if product.target_price !== undefined}
        <div class="small target" class:hit={belowTarget}>
          {belowTarget ? '🎯 Target reached' : 'Target'}
          {money(product.target_price, product.best?.currency)}
        </div>
      {/if}
    </div>
    <Sparkline points={product.sparkline} />
  </div>
</a>

<style>
  .product {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 16px;
    text-decoration: none;
    transition: border-color 0.15s;
  }
  .product:hover {
    border-color: var(--accent);
  }
  .top {
    display: flex;
    gap: 12px;
    align-items: center;
  }
  .thumb {
    width: 56px;
    height: 56px;
    border-radius: 10px;
    background: #fff;
    border: 1px solid var(--border);
    display: grid;
    place-items: center;
    flex-shrink: 0;
    overflow: hidden;
    font-size: 24px;
  }
  .thumb img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
  h3 {
    margin: 0 0 2px;
    font-size: 16px;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .tags {
    margin-top: 6px;
  }
  .bottom {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 12px;
  }
  .price {
    font-size: 24px;
    font-weight: 750;
  }
  .small {
    font-size: 13px;
  }
  .target {
    margin-top: 4px;
    color: var(--muted);
  }
  .target.hit {
    color: var(--good-ink);
    font-weight: 600;
  }
</style>
