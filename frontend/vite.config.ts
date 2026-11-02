import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// In development the SPA talks to the deployed API and reads the deployed
// runtime config, so no local backend is needed. Sign-in redirects back to
// http://localhost:5173/callback (allowed via extra_callback_urls).
const deployed = process.env.COST_TRACKER_URL ?? 'https://costtracker.marxai.de'

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: deployed, changeOrigin: true },
      '/config.json': { target: deployed, changeOrigin: true },
    },
  },
  build: {
    target: 'es2022',
    sourcemap: false,
  },
})
