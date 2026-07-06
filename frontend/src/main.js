import './style.css'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router.js'
import App from './App.vue'

if ('serviceWorker' in navigator && import.meta.env.MODE !== 'development') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/silence/sw.js', { scope: '/silence/' })
      .catch(err => console.warn('SW registration failed:', err))
  })
  const prevController = navigator.serviceWorker.controller
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (prevController) window.location.reload()
  })
} else if ('serviceWorker' in navigator) {
  // Dev: a SW left over from a prior prod build on this origin would keep serving
  // stale cached API responses (dev never re-registers to update it). Tear it down
  // and drop its caches so dev always hits the live backend.
  navigator.serviceWorker.getRegistrations().then(rs => rs.forEach(r => r.unregister()))
  if (window.caches) caches.keys().then(ks => ks.forEach(k => k.startsWith('soj-') && caches.delete(k)))
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
