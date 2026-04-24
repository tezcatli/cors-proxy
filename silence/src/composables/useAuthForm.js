import { ref } from 'vue'

export function useAuthForm() {
  const busy     = ref(false)
  const errorMsg = ref('')
  const infoMsg  = ref('')

  function clearMessages() {
    errorMsg.value = ''
    infoMsg.value  = ''
  }

  async function run(fn, { redirect } = {}) {
    clearMessages()
    busy.value = true
    try {
      await fn()
      return true
    } catch (err) {
      errorMsg.value = err.message
      return false
    } finally {
      busy.value = false
    }
  }

  return { busy, errorMsg, infoMsg, clearMessages, run }
}
