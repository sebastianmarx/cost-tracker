<script lang="ts">
  import { onMount } from 'svelte'
  import { api, ApiError } from '../lib/api'
  import type { Product } from '../lib/types'
  import TagInput from './TagInput.svelte'

  let {
    product = null,
    allTags = [],
    onclose,
    onsaved,
  }: {
    product?: Product | null
    allTags?: string[]
    onclose: () => void
    onsaved: (product: Product) => void
  } = $props()

  // The form edits a snapshot: later prop changes must not overwrite typing.
  // svelte-ignore state_referenced_locally
  const editing = product !== null
  // svelte-ignore state_referenced_locally
  let name = $state(product?.name ?? '')
  // svelte-ignore state_referenced_locally
  let target = $state(product?.target_price?.toString().replace('.', ',') ?? '')
  // svelte-ignore state_referenced_locally
  let tags = $state<string[]>([...(product?.tags ?? [])])
  let links = $state<string[]>([''])
  let saving = $state(false)
  let error = $state('')
  let dialog: HTMLDialogElement

  onMount(() => dialog.showModal())

  function parseTarget(): number | null | 'invalid' {
    const raw = target.trim().replace(/\s|€/g, '')
    if (!raw) return null
    const normalized = raw.includes(',') ? raw.replace(/\./g, '').replace(',', '.') : raw
    const value = Number(normalized)
    return Number.isFinite(value) && value > 0 ? Math.round(value * 100) / 100 : 'invalid'
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault()
    error = ''
    const targetPrice = parseTarget()
    if (targetPrice === 'invalid') {
      error = 'Target price must be a positive number.'
      return
    }
    saving = true
    try {
      const saved = editing
        ? await api.updateProduct(product!.id, { name: name.trim(), target_price: targetPrice, tags })
        : await api.createProduct({
            name: name.trim(),
            target_price: targetPrice,
            tags,
            links: links.map((l) => l.trim()).filter(Boolean),
          })
      onsaved(saved)
    } catch (e) {
      error = e instanceof ApiError ? e.message : 'Saving failed.'
    } finally {
      saving = false
    }
  }
</script>

<dialog bind:this={dialog} onclose={onclose} aria-labelledby="form-title">
  <form onsubmit={submit}>
    <h2 id="form-title">{editing ? 'Edit product' : 'Add product'}</h2>

    <label>
      <span>Name</span>
      <input type="text" bind:value={name} required maxlength="120" placeholder="e.g. Sony WH-1000XM6" />
    </label>

    <label>
      <span>Target price <small class="muted">(optional — email alert when reached)</small></span>
      <input type="text" inputmode="decimal" bind:value={target} placeholder="e.g. 299,00" />
    </label>

    <div class="field">
      <span>Tags <small class="muted">(optional — to group and filter products)</small></span>
      <TagInput bind:tags suggestions={allTags} />
    </div>

    {#if !editing}
      <fieldset>
        <legend>Shop links <small class="muted">(Amazon or any shop, up to 10)</small></legend>
        {#each links as _, index (index)}
          <div class="row">
            <input
              type="url"
              bind:value={links[index]}
              placeholder="https://www.amazon.de/dp/…"
              aria-label="Shop link {index + 1}"
            />
            {#if links.length > 1}
              <button
                type="button"
                class="btn icon"
                aria-label="Remove link"
                onclick={() => links.splice(index, 1)}>✕</button
              >
            {/if}
          </div>
        {/each}
        {#if links.length < 10}
          <button type="button" class="btn small" onclick={() => links.push('')}>+ Another shop</button>
        {/if}
      </fieldset>
    {/if}

    {#if error}<div class="error-box">{error}</div>{/if}

    <div class="actions">
      <button type="button" class="btn" onclick={() => dialog.close()}>Cancel</button>
      <button type="submit" class="btn primary" disabled={saving || !name.trim()}>
        {#if saving}<span class="spinner"></span>{/if}
        {editing ? 'Save' : 'Add product'}
      </button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    border: 1px solid var(--border);
    border-radius: var(--radius);
    background: var(--surface);
    color: var(--ink);
    padding: 0;
    width: min(520px, calc(100vw - 32px));
  }
  dialog::backdrop {
    background: rgba(0, 0, 0, 0.45);
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 24px;
  }
  h2 {
    margin: 0;
    font-size: 20px;
  }
  label,
  .field,
  fieldset {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-weight: 550;
  }
  fieldset {
    border: 0;
    padding: 0;
    margin: 0;
    gap: 8px;
  }
  legend {
    margin-bottom: 6px;
    padding: 0;
  }
  small {
    font-weight: 400;
  }
  .row {
    display: flex;
    gap: 8px;
  }
  fieldset .btn.small {
    align-self: flex-start;
  }
  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
</style>
