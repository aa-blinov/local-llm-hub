import preset from './vendor/monos-ui/src/tailwind-preset.js';

/** @type {import('tailwindcss').Config} */
export default {
  presets: [preset],
  content: ['./src/**/*.{svelte,js}', './vendor/monos-ui/src/**/*.{svelte,js}'],
};
