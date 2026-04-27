import './style.css'
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router.js'
import App from './App.vue'

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/silence/sw.js', { scope: '/silence/' })
}

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
