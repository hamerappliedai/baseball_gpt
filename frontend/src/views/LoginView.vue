<script setup>
// Sign in for Ask AI. Accounts are created by the site admin; there is no sign-up.
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth, signIn } from '../auth'

const route = useRoute()
const router = useRouter()
const email = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

// Only same-site paths, so ?next= can't send people elsewhere.
const next = () => {
  const n = route.query.next
  return typeof n === 'string' && n.startsWith('/') && !n.startsWith('//') ? n : '/ask'
}

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await signIn(email.value, password.value)
    password.value = ''
    router.replace(next())
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <main class="page login">
    <h1>Sign in</h1>
    <p v-if="auth.user" class="muted">
      You're signed in as {{ auth.user.display_name }}.
      <RouterLink :to="next()">Continue</RouterLink>
    </p>
    <form v-else class="login-form" @submit.prevent="submit">
      <label>
        Email
        <input v-model="email" type="email" autocomplete="username" required autofocus />
      </label>
      <label>
        Password
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>
      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <button type="submit" :disabled="busy">{{ busy ? 'Signing in…' : 'Sign in' }}</button>
      <p class="muted small">
        Ask AI sends your questions to Claude, which costs money per question, so it's open to
        invited accounts only. Leaders, Players and Standings are free for everyone.
      </p>
    </form>
  </main>
</template>
