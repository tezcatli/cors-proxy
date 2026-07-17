import { createRouter, createWebHistory } from 'vue-router'
import { isAdmin, isLoggedIn } from './lib/auth.js'
import DetailView  from './components/DetailView.vue'
import EpisodeView from './components/EpisodeView.vue'
import LoginPage   from './pages/LoginPage.vue'

const Empty = { render: () => null }

const router = createRouter({
  history: createWebHistory('/silence/'),
  routes: [
    { path: '/',                                  component: Empty,       meta: { depth: 0 } },
    { path: '/episodes',                          component: Empty,       meta: { depth: 0 } },
    { path: '/game/:slug',                        component: DetailView,  meta: { depth: 1 } },
    { path: '/episode/:episodeSlug',              component: EpisodeView, meta: { depth: 1 } },
    { path: '/login',                             component: LoginPage,   meta: { depth: 1 } },
    // Admin-only, and lazily loaded — no reason to ship the dashboard to the
    // readers who make up every ordinary session.
    { path: '/admin/resolution', meta: { depth: 1, admin: true },
      component: () => import('./pages/ResolutionStatsPage.vue') },
    { path: '/:pathMatch(.*)*',                   redirect: '/' },
  ],
})

router.beforeEach((to) => {
  // Forward reset/invite query params from non-login routes to the login page.
  // Guard is skipped when already on /login to avoid an infinite redirect loop.
  if (to.path !== '/login') {
    if (to.query.reset)  return { path: '/login', query: { reset:  to.query.reset  } }
    if (to.query.invite) return { path: '/login', query: { invite: to.query.invite } }
  }

  // Auth guard — all routes except /login require a valid session
  if (to.path !== '/login' && !isLoggedIn()) {
    const redirect = to.fullPath !== '/' ? { redirect: to.fullPath } : {}
    return { path: '/login', query: redirect }
  }

  // Admin routes: hide the UI from non-admins. Cosmetic — the endpoints behind
  // it enforce the real check, so this only avoids showing a page that 403s.
  if (to.meta.admin && !isAdmin()) return { path: '/' }
})

export default router
