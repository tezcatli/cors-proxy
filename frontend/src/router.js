import { createRouter, createWebHistory } from 'vue-router'
import { isAdmin, isLoggedIn } from './lib/auth.js'
import { noteVisit, guardHome } from './lib/home.js'
import DetailView  from './components/DetailView.vue'
import EpisodeView from './components/EpisodeView.vue'
import PodcastView from './components/PodcastView.vue'
import { PODCAST_BY_ID } from './lib/podcasts.js'
import LoginPage   from './pages/LoginPage.vue'

const Empty = { render: () => null }

const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    // The one base view (the Ludothèque) is rendered by App.vue, kept mounted
    // under the overlays. `/jeux` (the old games tab) leads there, search kept.
    { path: '/',                                  component: Empty,       meta: { depth: 0 } },
    { path: '/jeux',                              redirect: to => ({ path: '/', query: to.query }) },
    { path: '/episodes',                          redirect: '/' },
    { path: '/game/:slug',                        component: DetailView,  meta: { depth: 1 } },
    { path: '/episode/:episodeSlug',              component: EpisodeView, meta: { depth: 1 } },
    // A podcast's page; an unknown one leads back to the Ludothèque.
    { path: '/podcast/:id',                       component: PodcastView, meta: { depth: 1 },
      beforeEnter: to => (PODCAST_BY_ID[to.params.id] ? true : { path: '/' }) },
    { path: '/login',                             component: LoginPage,   meta: { depth: 1 } },
    // Admin-only, and lazily loaded — no reason to ship the dashboard to the
    // readers who make up every ordinary session.
    { path: '/admin/resolution', meta: { depth: 1, admin: true },
      component: () => import('./pages/ResolutionStatsPage.vue') },
    { path: '/admin/users', meta: { depth: 1, admin: true },
      component: () => import('./pages/AdminUsersPage.vue') },
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

router.afterEach(to => noteVisit(router, to))
guardHome(router)

export default router
