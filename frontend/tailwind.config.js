import daisyui from 'daisyui'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    screens: { sm: '600px', md: '768px', lg: '900px', xl: '1200px' },
    extend: {
      fontFamily: {
        sans:    ['Barlow', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        display: ['Barlow Condensed', 'Arial Narrow', 'sans-serif'],
        mono:    ['JetBrains Mono Variable', 'JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      // Studio radio is square: the size names stay for the admin consoles.
      borderRadius: { lg: '2px', xl: '2px', '2xl': '2px', '3xl': '2px' },
      boxShadow: {
        e1: 'none', e2: 'none', e3: 'none', e4: 'var(--shadow-cover)',
      },
      transitionTimingFunction: {
        'out-soft': 'cubic-bezier(0.22, 1, 0.36, 1)',
        spring:    'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
    },
  },
  plugins: [daisyui],
  daisyui: {
    themes: [
      {
        soj: {
          primary:           '#ffd23f',
          'primary-content': '#0b0b0b',
          secondary:         '#bdbdbd',
          accent:            '#ffd23f',
          'accent-content':  '#0b0b0b',
          neutral:           '#1c1c1c',
          'neutral-content': '#f5f5f5',
          'base-100':        '#0b0b0b',
          'base-200':        '#141414',
          'base-300':        '#262626',
          'base-content':    '#f5f5f5',
          info:              '#9ccfff',
          success:           '#9be0b4',
          warning:           '#ffd23f',
          error:             '#ff6b4a',
          '--rounded-box':   '0',
          '--rounded-btn':   '0',
          '--rounded-badge': '0',
          '--btn-text-case': 'none',
          '--animation-btn': '0',
        },
      },
    ],
    darkTheme: 'soj',
    logs: false,
  },
}
