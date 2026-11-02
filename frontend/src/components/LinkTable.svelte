<script lang="ts">
  import { ago, dateTime, money } from '../lib/format'
  import type { Link, RangeDays, WindowStats } from '../lib/types'
  import StatusBadge from './StatusBadge.svelte'

  let {
    links,
    range,
    busy,
    onrefresh,
    ondelete,
  }: {
    links: Link[]
    range: RangeDays
    busy: Record<string, boolean>
    onrefresh: (link: Link) => void
    ondelete: (link: Link) => void
  } = $props()

  const key = { 30: 'd30', 90: 'd90', 180: 'd180', 365: 'd365', 0: 'all' } as const

  function windowStats(link: Link): WindowStats | null {
    return link.stats?.[key[range]] ?? null
  }
</script>

<div class="scroll">
  <table>
    <thead>
      <tr>
        <th>Shop</th>
        <th class="r">Current</th>
        <th class="r">Min</th>
        <th class="r">Avg</th>
        <th class="r">Max</th>
        <th class="r">Lowest ever</th>
        <th>Last check</th>
        <th><span class="sr-only">Actions</span></th>
      </tr>
    </thead>
    <tbody>
      {#each links as link, index (link.id)}
        {@const stats = windowStats(link)}
        <tr>
          <td class="shop">
            <span class="swatch" style="background: var(--series-{index}, var(--muted))"></span>
            <div>
              <a href={link.url} target="_blank" rel="noopener noreferrer nofollow">{link.shop} ↗</a>
              {#if link.title}<div class="muted title" title={link.title}>{link.title}</div>{/if}
            </div>
          </td>
          <td class="r num current">
            {money(link.last_price, link.currency)}
            {#if link.last_in_stock === false}<div class="bad small">out of stock</div>{/if}
          </td>
          <td class="r num">{money(stats?.min, link.currency)}</td>
          <td class="r num">{money(stats?.avg, link.currency)}</td>
          <td class="r num">{money(stats?.max, link.currency)}</td>
          <td class="r num">
            {money(link.stats?.all_time_low?.price, link.currency)}
            {#if link.stats?.all_time_low}
              <div class="muted small">{new Date(link.stats.all_time_low.ts).toLocaleDateString('de-DE')}</div>
            {/if}
          </td>
          <td>
            <div title={dateTime(link.last_checked)}>{ago(link.last_checked)}</div>
            {#if link.last_status !== 'ok'}
              <StatusBadge status={link.last_status} error={link.last_error} />
            {/if}
          </td>
          <td class="actions">
            <button
              class="btn icon"
              title="Check price now"
              aria-label="Check price now for {link.shop}"
              disabled={busy[link.id]}
              onclick={() => onrefresh(link)}
            >
              {#if busy[link.id]}<span class="spinner"></span>{:else}↻{/if}
            </button>
            <button
              class="btn icon danger"
              title="Remove link"
              aria-label="Remove link to {link.shop}"
              onclick={() => ondelete(link)}>✕</button
            >
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
</div>

<style>
  .scroll {
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
    padding: 8px 10px;
    border-bottom: 1px solid var(--grid);
    white-space: nowrap;
  }
  td {
    padding: 12px 10px;
    border-bottom: 1px solid var(--grid);
    vertical-align: top;
  }
  tr:last-child td {
    border-bottom: 0;
  }
  .r {
    text-align: right;
    white-space: nowrap;
  }
  .current {
    font-weight: 700;
    font-size: 15px;
  }
  .shop {
    display: flex;
    gap: 10px;
    min-width: 180px;
  }
  .shop a {
    font-weight: 600;
    text-decoration: none;
  }
  .shop a:hover {
    text-decoration: underline;
  }
  .swatch {
    width: 12px;
    height: 3px;
    border-radius: 2px;
    margin-top: 9px;
    flex-shrink: 0;
  }
  .title {
    font-size: 12px;
    max-width: 260px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .small {
    font-size: 12px;
    font-weight: 400;
  }
  .actions {
    white-space: nowrap;
    text-align: right;
  }
</style>
