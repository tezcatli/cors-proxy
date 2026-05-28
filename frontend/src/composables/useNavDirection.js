import { ref, watch } from 'vue'

export function useNavDirection(route, router) {
  let _prevPos   = router.options.history.state?.position ?? 0
  let _prevDepth = route.meta?.depth ?? 0
  const navDir   = ref('nav-fade')

  watch(() => route.path, (newPath, oldPath) => {
    const newPos   = router.options.history.state?.position ?? 0
    const newDepth = route.meta?.depth ?? 0
    if (newPath === '/login' || oldPath === '/login') navDir.value = 'nav-fade'
    else if (newDepth === 0 && _prevDepth === 0)      navDir.value = 'nav-fade'
    else if (newPos < _prevPos)                        navDir.value = 'nav-back'
    else if (newDepth > _prevDepth)                    navDir.value = 'nav-overlay'
    else                                               navDir.value = 'nav-forward'
    _prevPos   = newPos
    _prevDepth = newDepth
  }, { flush: 'sync' })

  return { navDir }
}
