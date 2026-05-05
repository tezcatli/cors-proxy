import './style.css'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router.js'
import App from './App.vue'

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/silence/sw.js', { scope: '/silence/' })
      .catch(err => console.warn('SW registration failed:', err))
  })
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    window.location.reload()
  })
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
