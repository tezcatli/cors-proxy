import daisyui from 'daisyui'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  corePlugins: { preflight: false },
  theme: {
    screens: { sm: '600px', md: '768px', lg: '900px', xl: '1200px' },
  },
  plugins: [daisyui],
  daisyui: {
    themes: [
      {
        soj: {
          primary:           '#e94560',
          'primary-content': '#ffffff',
          secondary:         '#ff6b81',
          accent:            '#e94560',
          neutral:           '#1a2a50',
          'base-100':        '#0f0f1a',
          'base-200':        '#16213e',
          'base-300':        '#1a2a50',
          'base-content':    '#e8e8f0',
          '--rounded-box':   '12px',
          '--rounded-btn':   '8px',
          '--rounded-badge': '20px',
        },
      },
    ],
    darkTheme: 'soj',
    logs: false,
  },
}
