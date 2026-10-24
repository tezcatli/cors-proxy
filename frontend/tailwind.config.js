/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    screens: { sm: '600px', md: '768px', lg: '900px', xl: '1200px' },
    extend: {
      fontFamily: {
        sans:    ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        display: ['Sora', 'system-ui', 'sans-serif'],
        mono:    ['Inter', 'system-ui', 'sans-serif'],
      },
      // The panels are square: the size names stay for the admin consoles.
      borderRadius: { lg: '2px', xl: '2px', '2xl': '2px', '3xl': '2px' },
      boxShadow: {
        e1: 'none', e2: 'none', e3: 'none', e4: 'var(--shadow-cover)',
      },
      // The design tokens (tokens.css), for the few utilities that need
      // them: `bg-page`, `bg-surface`, `text-accent`, `text-danger`…
      colors: {
        page:    'var(--c-bg)',
        surface: 'var(--c-surface)',
        raised:  'var(--c-raised)',
        line:    'var(--c-line)',
        accent:  'var(--c-accent)',
        danger:  'var(--c-danger)',
      },
      transitionTimingFunction: {
        'out-soft': 'cubic-bezier(0.22, 1, 0.36, 1)',
        spring:    'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
    },
  },
  plugins: [],
}
