import { createRouter, createWebHistory } from 'vue-router'
import { isLoggedIn } from './lib/auth.js'
import DetailView from './components/DetailView.vue'
import LoginPage  from './pages/LoginPage.vue'

const Empty = { render: () => null }

const router = createRouter({
  history: createWebHistory('/silence/'),
  routes: [
    { path: '/',             component: Empty },
    { path: '/game/:slug',   component: DetailView },
    { path: '/login',        component: LoginPage },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach((to) => {
  // Forward legacy reset/invite query params to the login page
  if (to.query.reset)  return { path: '/login', query: { reset:  to.query.reset  } }
  if (to.query.invite) return { path: '/login', query: { invite: to.query.invite } }

  // Auth guard — all routes except /login require a valid session
  if (to.path !== '/login' && !isLoggedIn()) {
    const redirect = to.fullPath !== '/' ? { redirect: to.fullPath } : {}
    return { path: '/login', query: redirect }
  }
})

export default router
