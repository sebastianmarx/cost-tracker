<script lang="ts">
  let { tags = [], onselect }: { tags?: string[]; onselect?: (tag: string) => void } = $props()
</script>

{#if tags.length}
  <ul class="tags" aria-label="Tags">
    {#each tags as tag (tag)}
      <li>
        {#if onselect}
          <button
            type="button"
            class="tag"
            onclick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onselect(tag)
            }}>{tag}</button
          >
        {:else}
          <span class="tag">{tag}</span>
        {/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .tag {
    display: inline-block;
    font-size: 12px;
    line-height: 1.4;
    padding: 1px 8px;
    border-radius: 999px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    color: var(--ink-2);
  }
  button.tag {
    cursor: pointer;
    font: inherit;
    font-size: 12px;
  }
  button.tag:hover {
    border-color: var(--accent);
    color: var(--ink);
  }
</style>
