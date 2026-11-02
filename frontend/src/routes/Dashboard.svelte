<script lang="ts">
  import { onDestroy, onMount } from 'svelte'
  import { api, ApiError } from '../lib/api'
  import { loadPref, savePref } from '../lib/prefs'
  import { navigate, route, setQuery } from '../lib/router.svelte'
  import type { ProductSummary } from '../lib/types'
  import ProductCard from '../components/ProductCard.svelte'
  import ProductForm from '../components/ProductForm.svelte'
  import ProductList from '../components/ProductList.svelte'

  const VIEWS = ['grid', 'list'] as const
  const SORTS = ['name', 'price', 'change', 'target'] as const
  const DIRS = ['asc', 'desc'] as const

  let products = $state<ProductSummary[] | null>(null)
  let error = $state('')
  let adding = $state(false)
  let refreshing = $state(false)
  let notice = $state('')
  let search = $state('')
  let view = $state(loadPref('view', VIEWS, 'grid'))
  let sort = $state(loadPref('sort', SORTS, 'name'))
  let dir = $state(loadPref('dir', DIRS, 'asc'))
  let poll: ReturnType<typeof setInterval> | null = null

  $effect(() => savePref('view', view))
  $effect(() => savePref('sort', sort))
  $effect(() => savePref('dir', dir))

  // Selected tags live in the URL (?tags=a,b) so a filtered view can be bookmarked.
  const selected = $derived(
    (new URLSearchParams(route.search).get('tags') ?? '')
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean),
  )

  /** Every tag with its product count, most used first. */
  const allTags = $derived.by(() => {
    const counts = new Map<string, { tag: string; count: number }>()
    for (const product of products ?? []) {
      for (const tag of product.tags ?? []) {
        const key = tag.toLowerCase()
        const entry = counts.get(key) ?? { tag, count: 0 }
        entry.count++
        counts.set(key, entry)
      }
    }
    return [...counts.values()].sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag, 'de-DE'))
  })

  const isSelected = (tag: string) => selected.some((s) => s.toLowerCase() === tag.toLowerCase())

  function toggleTag(tag: string) {
    const next = isSelected(tag)
      ? selected.filter((s) => s.toLowerCase() !== tag.toLowerCase())
      : [...selected, tag]
    setQuery({ tags: next.join(',') || null })
  }

  // A product matches when it has ANY of the selected tags.
  const visible = $derived.by(() => {
    const needle = search.trim().toLowerCase()
    const wanted = new Set(selected.map((s) => s.toLowerCase()))
    return (products ?? []).filter(
      (p) =>
        (!wanted.size || (p.tags ?? []).some((t) => wanted.has(t.toLowerCase()))) &&
        (!needle || p.name.toLowerCase().includes(needle)),
    )
  })

  async function load() {
    try {
      products = await api.listProducts()
      error = ''
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) error = e instanceof Error ? e.message : String(e)
    }
  }

  async function refreshAll() {
    refreshing = true
    try {
      const { queued } = await api.refreshAll()
      notice = `Checking ${queued} ${queued === 1 ? 'link' : 'links'} in the background — this page updates by itself.`
      // The scraper waits a few seconds between shops; poll for ~5 minutes.
      let ticks = 0
      if (poll) clearInterval(poll)
      poll = setInterval(async () => {
        await load()
        if (++ticks >= 15 && poll) {
          clearInterval(poll)
          poll = null
          notice = ''
        }
      }, 20_000)
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
    } finally {
      refreshing = false
    }
  }

  onMount(load)
  onDestroy(() => poll && clearInterval(poll))
</script>

<div class="head">
  <div>
    <h1>Products</h1>
    <p class="muted">Prices are checked daily at 06:00 and 18:00.</p>
  </div>
  <div class="actions">
    <button class="btn" onclick={refreshAll} disabled={refreshing || !products?.length}>
      {#if refreshing}<span class="spinner"></span>{:else}↻{/if}
      Refresh all
    </button>
    <button class="btn primary" onclick={() => (adding = true)}>+ Add product</button>
  </div>
</div>

{#if notice}<div class="notice">{notice}</div>{/if}
{#if error}<div class="error-box">{error}</div>{/if}

{#if products === null && !error}
  <p class="muted"><span class="spinner"></span> Loading…</p>
{:else if products && products.length === 0}
  <div class="card empty">
    <h2>Nothing tracked yet</h2>
    <p class="secondary">Add a product and paste one or more shop links (Amazon or any other shop).</p>
    <button class="btn primary" onclick={() => (adding = true)}>+ Add your first product</button>
  </div>
{:else if products}
  <div class="toolbar">
    <input class="search" type="search" bind:value={search} placeholder="Search products…" aria-label="Search products" />
    <div class="views" role="group" aria-label="View">
      <button class="view" class:active={view === 'grid'} aria-pressed={view === 'grid'} onclick={() => (view = 'grid')}>
        <span aria-hidden="true">▦</span> Cards
      </button>
      <button class="view" class:active={view === 'list'} aria-pressed={view === 'list'} onclick={() => (view = 'list')}>
        <span aria-hidden="true">☰</span> List
      </button>
    </div>
  </div>

  {#if allTags.length}
    <div class="filters" role="group" aria-label="Filter by tag">
      <button class="filter" class:active={!selected.length} aria-pressed={!selected.length} onclick={() => setQuery({ tags: null })}>
        All <span class="count">{products.length}</span>
      </button>
      {#each allTags as { tag, count } (tag)}
        <button class="filter" class:active={isSelected(tag)} aria-pressed={isSelected(tag)} onclick={() => toggleTag(tag)}>
          {tag} <span class="count">{count}</span>
        </button>
      {/each}
    </div>
  {/if}

  {#if visible.length === 0}
    <p class="muted">No products match this filter.</p>
  {:else if view === 'list'}
    <ProductList products={visible} bind:sort bind:dir />
  {:else}
    <div class="grid">
      {#each visible as product (product.id)}
        <ProductCard {product} />
      {/each}
    </div>
  {/if}
{/if}

{#if adding}
  <ProductForm
    allTags={allTags.map((t) => t.tag)}
    onclose={() => (adding = false)}
    onsaved={(p) => navigate(`/products/${p.id}`)}
  />
{/if}

<style>
  .head {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 20px;
  }
  h1 {
    margin: 0;
    font-size: 26px;
  }
  .head p {
    margin: 2px 0 0;
  }
  .actions {
    display: flex;
    gap: 8px;
  }
  .toolbar {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 12px;
  }
  .search {
    flex: 1;
    max-width: 360px;
    border: 1px solid var(--border);
    background: var(--surface);
    border-radius: 10px;
    padding: 7px 12px;
  }
  .views {
    display: inline-flex;
    margin-left: auto;
    background: var(--surface-2);
    border-radius: 10px;
    padding: 3px;
  }
  .view {
    border: 0;
    background: transparent;
    padding: 4px 12px;
    border-radius: 8px;
    cursor: pointer;
    font-weight: 600;
    font-size: 13px;
    color: var(--ink-2);
  }
  .view.active {
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow);
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 16px;
  }
  .filter {
    border: 1px solid var(--border);
    background: var(--surface);
    border-radius: 999px;
    padding: 4px 12px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 550;
    color: var(--ink-2);
  }
  .filter:hover {
    border-color: var(--accent);
  }
  .filter.active {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-ink);
  }
  .count {
    font-weight: 400;
    opacity: 0.75;
    margin-left: 2px;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 16px;
  }
  .empty {
    padding: 40px 24px;
    text-align: center;
  }
  .empty h2 {
    margin-top: 0;
  }
  .notice {
    background: var(--accent-soft);
    border-radius: 10px;
    padding: 10px 14px;
    margin-bottom: 16px;
  }
  .error-box {
    margin-bottom: 16px;
  }
  @media (max-width: 560px) {
    .search {
      max-width: none;
    }
  }
</style>
