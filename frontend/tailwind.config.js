import daisyui from 'daisyui'

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    screens: { sm: '600px', md: '768px', lg: '900px', xl: '1200px' },
    extend: {
      fontFamily: {
        sans: [
          'Inter Variable',
          'Inter',
          'Segoe UI',
          'system-ui',
          '-apple-system',
          'sans-serif',
        ],
        mono: [
          'JetBrains Mono Variable',
          'JetBrains Mono',
          'ui-monospace',
          'SFMono-Regular',
          'monospace',
        ],
      },
      borderRadius: {
        lg: '16px',
        xl: '20px',
        '2xl': '24px',
        '3xl': '32px',
      },
      boxShadow: {
        e1: '0 1px 2px rgba(0,0,0,0.30)',
        e2: '0 6px 16px -4px rgba(0,0,0,0.45)',
        e3: '0 14px 32px -8px rgba(0,0,0,0.55)',
        e4: '0 28px 60px -12px rgba(0,0,0,0.65)',
      },
      transitionTimingFunction: {
        'out-soft': 'cubic-bezier(0.22, 1, 0.36, 1)',
        spring:    'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      backdropBlur: {
        glass: '18px',
      },
      keyframes: {
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition:  '200% 0' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.6s linear infinite',
      },
    },
  },
  plugins: [daisyui],
  daisyui: {
    themes: [
      {
        soj: {
          primary:           '#e94560',
          'primary-content': '#ffffff',
          secondary:         '#ff8aa0',
          accent:            '#8b5cf6',
          'accent-content':  '#ffffff',
          neutral:           '#16162a',
          'neutral-content': '#e8e8f0',
          'base-100':        '#08080f',
          'base-200':        '#0f0f1c',
          'base-300':        '#1a1a2e',
          'base-content':    '#f5f5fa',
          info:              '#22d3ee',
          success:           '#4ade80',
          warning:           '#fbbf24',
          error:             '#f87171',
          '--rounded-box':   '16px',
          '--rounded-btn':   '10px',
          '--rounded-badge': '999px',
          '--btn-text-case': 'none',
        },
      },
    ],
    darkTheme: 'soj',
    logs: false,
  },
}
