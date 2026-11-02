<script lang="ts">
  let {
    tags = $bindable([]),
    suggestions = [],
    max = 10,
  }: { tags: string[]; suggestions?: string[]; max?: number } = $props()

  let draft = $state('')
  const listId = `tag-suggestions-${Math.random().toString(36).slice(2, 8)}`
  const available = $derived(
    suggestions.filter((s) => !tags.some((t) => t.toLowerCase() === s.toLowerCase())),
  )

  function add(raw: string) {
    const tag = raw.replace(/\s+/g, ' ').trim().slice(0, 30)
    if (!tag || tags.length >= max) return
    if (!tags.some((t) => t.toLowerCase() === tag.toLowerCase())) tags = [...tags, tag]
    draft = ''
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' || event.key === ',') {
      event.preventDefault()
      add(draft)
    } else if (event.key === 'Backspace' && !draft && tags.length) {
      tags = tags.slice(0, -1)
    }
  }

  function oninput() {
    // Picking an entry from the datalist fills the whole value at once.
    if (suggestions.includes(draft)) add(draft)
    else if (draft.includes(',')) draft.split(',').forEach(add)
  }
</script>

<div class="tag-input">
  {#each tags as tag (tag)}
    <span class="chip">
      {tag}
      <button type="button" aria-label="Remove tag {tag}" onclick={() => (tags = tags.filter((t) => t !== tag))}
        >✕</button
      >
    </span>
  {/each}
  {#if tags.length < max}
    <input
      type="text"
      bind:value={draft}
      {onkeydown}
      {oninput}
      onblur={() => add(draft)}
      list={listId}
      maxlength="30"
      placeholder={tags.length ? '' : 'e.g. Audio, Kitchen — Enter to add'}
      aria-label="Add tag"
    />
    <datalist id={listId}>
      {#each available as suggestion (suggestion)}
        <option value={suggestion}></option>
      {/each}
    </datalist>
  {/if}
</div>

<style>
  .tag-input {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
    border: 1px solid var(--border);
    background: var(--surface);
    border-radius: 10px;
    padding: 6px 8px;
    font-weight: 400;
  }
  .tag-input:focus-within {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  input {
    flex: 1;
    min-width: 140px;
    border: 0;
    background: transparent;
    padding: 2px 4px;
    outline: none;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: var(--accent-soft);
    border-radius: 999px;
    padding: 2px 4px 2px 10px;
    font-size: 13px;
  }
  .chip button {
    border: 0;
    background: transparent;
    cursor: pointer;
    font-size: 11px;
    padding: 2px 5px;
    border-radius: 999px;
    color: var(--ink-2);
  }
  .chip button:hover {
    background: color-mix(in srgb, var(--ink) 10%, transparent);
  }
</style>
