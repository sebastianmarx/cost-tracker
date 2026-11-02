<script lang="ts">
  import { onMount } from 'svelte'
  import { api, ApiError } from '../lib/api'
  import { money } from '../lib/format'
  import { link as navLink, navigate } from '../lib/router.svelte'
  import type { ChartSeries, Link, Product, RangeDays } from '../lib/types'
  import LinkTable from '../components/LinkTable.svelte'
  import PriceChart from '../components/PriceChart.svelte'
  import ProductForm from '../components/ProductForm.svelte'
  import TagList from '../components/TagList.svelte'

  let { id }: { id: string } = $props()

  const RANGES: { days: RangeDays; label: string }[] = [
    { days: 30, label: '1M' },
    { days: 90, label: '3M' },
    { days: 180, label: '6M' },
    { days: 365, label: '1Y' },
    { days: 0, label: 'All' },
  ]

  let product = $state<Product | null>(null)
  let series = $state<ChartSeries[]>([])
  let range = $state<RangeDays>(90)
  let error = $state('')
  let message = $state('')
  let editing = $state(false)
  let busy = $state<Record<string, boolean>>({})
  let newUrl = $state('')
  let adding = $state(false)
  let knownTags = $state<string[]>([])

  async function loadProduct() {
    try {
      product = await api.getProduct(id)
      error = ''
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) error = 'This product does not exist (any more).'
      else if (!(e instanceof ApiError && e.status === 401)) error = e instanceof Error ? e.message : String(e)
    }
  }

  async function loadHistory() {
    if (!product) return
    const links = product.links
    const histories = await Promise.all(links.map((l) => api.history(l.id, range)))
    series = links.map((l, index) => ({
      id: l.id,
      label: l.shop,
      slot: index,
      currency: l.currency,
      points: histories[index].points,
    }))
  }

  async function reload() {
    await loadProduct()
    await loadHistory().catch(() => {})
  }

  onMount(reload)

  async function setRange(days: RangeDays) {
    range = days
    await loadHistory()
  }

  function flash(text: string) {
    message = text
    setTimeout(() => (message === text ? (message = '') : null), 6000)
  }

  async function refreshLink(link: Link) {
    busy[link.id] = true
    try {
      const updated = await api.refreshLink(link.id)
      if (updated.last_status === 'ok') flash(`${link.shop}: ${money(updated.last_price, updated.currency)}`)
      else flash(`${link.shop}: ${updated.last_error ?? 'check failed'} — kept the last known price.`)
      await reload()
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e))
    } finally {
      busy[link.id] = false
    }
  }

  async function deleteLink(link: Link) {
    if (!product || !confirm(`Remove ${link.shop} and its price history?`)) return
    await api.deleteLink(product.id, link.id)
    await reload()
  }

  async function addLink(event: SubmitEvent) {
    event.preventDefault()
    if (!product || !newUrl.trim()) return
    adding = true
    try {
      await api.addLink(product.id, newUrl.trim())
      newUrl = ''
      flash('Link added — the first price check is running and shows up in a few seconds.')
      await reload()
      setTimeout(reload, 12_000)
    } catch (e) {
      flash(e instanceof Error ? e.message : String(e))
    } finally {
      adding = false
    }
  }

  async function openEdit() {
    editing = true
    // Suggest tags used on other products.
    const all = await api.listProducts().catch(() => [])
    const seen = new Map<string, string>()
    for (const tag of all.flatMap((p) => p.tags ?? [])) seen.set(tag.toLowerCase(), seen.get(tag.toLowerCase()) ?? tag)
    knownTags = [...seen.values()].sort((a, b) => a.localeCompare(b, 'de-DE'))
  }

  async function deleteProduct() {
    if (!product || !confirm(`Delete "${product.name}" with all links and price history?`)) return
    await api.deleteProduct(product.id)
    navigate('/')
  }
</script>

<a href="/" onclick={navLink} class="back">← All products</a>

{#if error}
  <div class="error-box">{error}</div>
{:else if !product}
  <p class="muted"><span class="spinner"></span> Loading…</p>
{:else}
  <section class="head">
    <div class="thumb">
      {#if product.image_url}
        <img src={product.image_url} alt="" referrerpolicy="no-referrer" />
      {:else}
        <span aria-hidden="true">🛒</span>
      {/if}
    </div>
    <div class="info">
      <h1>{product.name}</h1>
      {#if product.tags?.length}
        <div class="tags">
          <TagList tags={product.tags} onselect={(tag) => navigate(`/?tags=${encodeURIComponent(tag)}`)} />
        </div>
      {/if}
      <p class="secondary">
        {#if product.target_price !== undefined}
          Target price <strong>{money(product.target_price, product.links[0]?.currency)}</strong> — you get an email
          when a shop reaches it.
        {:else}
          No target price set.
        {/if}
      </p>
    </div>
    <div class="head-actions">
      <button class="btn" onclick={openEdit}>Edit</button>
      <button class="btn danger" onclick={deleteProduct}>Delete</button>
    </div>
  </section>

  {#if message}<div class="notice" role="status">{message}</div>{/if}

  <section class="card panel">
    <div class="panel-head">
      <h2>Price history</h2>
      <div class="ranges" role="group" aria-label="Time range">
        {#each RANGES as r (r.days)}
          <button class="range" class:active={range === r.days} aria-pressed={range === r.days} onclick={() => setRange(r.days)}
            >{r.label}</button
          >
        {/each}
      </div>
    </div>
    <PriceChart {series} target={product.target_price ?? null} />
  </section>

  <section class="card panel">
    <div class="panel-head">
      <h2>Shops</h2>
    </div>
    {#if product.links.length}
      <LinkTable links={product.links} {range} {busy} onrefresh={refreshLink} ondelete={deleteLink} />
    {:else}
      <p class="muted">No shop links yet.</p>
    {/if}
    {#if product.links.length < 10}
      <form class="add" onsubmit={addLink}>
        <input type="url" bind:value={newUrl} placeholder="Add another shop link: https://…" aria-label="New shop link" />
        <button class="btn primary" disabled={adding || !newUrl.trim()}>
          {#if adding}<span class="spinner"></span>{/if}
          Add link
        </button>
      </form>
    {/if}
  </section>
{/if}

{#if editing && product}
  <ProductForm
    {product}
    allTags={knownTags}
    onclose={() => (editing = false)}
    onsaved={async () => {
      editing = false
      await reload()
    }}
  />
{/if}

<style>
  .back {
    display: inline-block;
    margin-bottom: 16px;
    text-decoration: none;
    color: var(--ink-2);
  }
  .head {
    display: flex;
    gap: 16px;
    align-items: center;
    margin-bottom: 20px;
    flex-wrap: wrap;
  }
  .thumb {
    width: 88px;
    height: 88px;
    border-radius: 14px;
    background: #fff;
    border: 1px solid var(--border);
    display: grid;
    place-items: center;
    overflow: hidden;
    font-size: 36px;
    flex-shrink: 0;
  }
  .thumb img {
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
  }
  .info {
    flex: 1;
    min-width: 220px;
  }
  h1 {
    margin: 0 0 4px;
    font-size: 24px;
    line-height: 1.25;
  }
  .tags {
    margin-bottom: 6px;
  }
  .info p {
    margin: 0;
  }
  .head-actions {
    display: flex;
    gap: 8px;
  }
  .panel {
    padding: 20px;
    margin-bottom: 20px;
  }
  .panel-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }
  h2 {
    margin: 0;
    font-size: 17px;
  }
  .ranges {
    display: inline-flex;
    background: var(--surface-2);
    border-radius: 10px;
    padding: 3px;
  }
  .range {
    border: 0;
    background: transparent;
    padding: 4px 12px;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
    color: var(--ink-2);
  }
  .range.active {
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow);
  }
  .add {
    display: flex;
    gap: 8px;
    margin-top: 16px;
  }
  .notice {
    background: var(--accent-soft);
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 16px;
  }
</style>
