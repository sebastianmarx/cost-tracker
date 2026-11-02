<script lang="ts">
  import { onMount } from 'svelte'
  import { completeSignIn, currentUser, signIn, signOut } from './lib/auth'
  import { link, navigate, route } from './lib/router.svelte'
  import Dashboard from './routes/Dashboard.svelte'
  import ProductDetail from './routes/ProductDetail.svelte'

  let phase = $state<'loading' | 'ready' | 'error'>('loading')
  let email = $state<string | null>(null)
  let error = $state('')

  onMount(async () => {
    try {
      if (route.path === '/callback') {
        const target = await completeSignIn()
        navigate(target, true)
      }
      const user = await currentUser()
      if (!user) {
        await signIn()
        return
      }
      email = (user.profile.email as string | undefined) ?? null
      phase = 'ready'
    } catch (e) {
      error = e instanceof Error ? e.message : String(e)
      phase = 'error'
    }
  })

  const productId = $derived(route.path.match(/^\/products\/([0-9a-f]{32})$/)?.[1] ?? null)
</script>

<header>
  <div class="bar">
    <a href="/" onclick={link} class="brand">
      <img src="/logo.svg" alt="" width="32" height="32" />
      Cost Tracker
    </a>
    {#if phase === 'ready'}
      <div class="user">
        <span class="muted email">{email}</span>
        <button class="btn small" onclick={() => signOut()}>Sign out</button>
      </div>
    {/if}
  </div>
</header>

<main>
  {#if phase === 'loading'}
    <p class="muted center"><span class="spinner"></span> Signing in…</p>
  {:else if phase === 'error'}
    <div class="error-box">
      <strong>Sign-in failed.</strong>
      {error}
      <div style="margin-top:10px"><button class="btn" onclick={() => signIn('/')}>Try again</button></div>
    </div>
  {:else if productId}
    {#key productId}
      <ProductDetail id={productId} />
    {/key}
  {:else if route.path === '/'}
    <Dashboard />
  {:else}
    <p>Page not found. <a href="/" onclick={link}>Back to overview</a></p>
  {/if}
</main>

<style>
  header {
    position: sticky;
    top: 0;
    z-index: 10;
    background: color-mix(in srgb, var(--page) 88%, transparent);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid var(--border);
  }
  .bar,
  main {
    max-width: 1120px;
    margin: 0 auto;
    padding: 0 16px;
  }
  .bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 56px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 700;
    font-size: 17px;
    text-decoration: none;
  }
  .brand img {
    display: block;
    flex-shrink: 0;
  }
  .user {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  main {
    padding-top: 24px;
    padding-bottom: 64px;
  }
  .center {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: center;
    padding: 64px 0;
  }
  @media (max-width: 560px) {
    .email {
      display: none;
    }
  }
</style>
