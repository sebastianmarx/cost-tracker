<script lang="ts">
  import { statusLabel } from '../lib/format'
  import type { LinkStatus } from '../lib/types'

  let { status, error = '' }: { status: LinkStatus | null; error?: string } = $props()

  // Status color always ships with an icon and a label, never color alone.
  const look: Record<LinkStatus, { icon: string; tone: string }> = {
    ok: { icon: '✓', tone: 'good' },
    pending: { icon: '…', tone: 'neutral' },
    blocked: { icon: '⛔', tone: 'serious' },
    parse_error: { icon: '?', tone: 'warning' },
    http_error: { icon: '!', tone: 'critical' },
  }
</script>

{#if status}
  <span class="badge {look[status].tone}" title={error || statusLabel[status]}>
    <span aria-hidden="true">{look[status].icon}</span>
    {statusLabel[status]}
  </span>
{/if}

<style>
  .badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    font-weight: 600;
    padding: 1px 8px;
    border-radius: 999px;
    border: 1px solid var(--tone);
    background: color-mix(in srgb, var(--tone) 12%, transparent);
    color: var(--ink);
    white-space: nowrap;
  }
  .good {
    --tone: var(--status-good);
  }
  .warning {
    --tone: var(--status-warning);
  }
  .serious {
    --tone: var(--status-serious);
  }
  .critical {
    --tone: var(--status-critical);
  }
  .neutral {
    --tone: var(--muted);
  }
</style>
