import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  plugins: [svelte()],
  // The built app is served by the FastAPI panel at /static/app/.
  base: '/static/app/',
  resolve: { alias: { '@monos/ui': fileURLToPath(new URL('./vendor/monos-ui/src/index.js', import.meta.url)) } },
  build: {
    outDir: '../src/llm_hub/static/app',
    emptyOutDir: true,
  },
});
