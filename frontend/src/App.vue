<script setup>
import { RouterLink, RouterView, useRouter } from 'vue-router'
import PlayerSearch from './components/PlayerSearch.vue'
import { auth, signOut } from './auth'

const router = useRouter()
async function onSignOut() {
  await signOut()
  if (router.currentRoute.value.path === '/ask') router.replace('/login?next=/ask')
}
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink to="/" class="brand">⚾ Baseball GPT</RouterLink>
      <PlayerSearch />
      <nav>
        <RouterLink to="/leaders">Leaders</RouterLink>
        <RouterLink to="/standings">Standings</RouterLink>
        <RouterLink to="/ask">Ask AI</RouterLink>
        <button v-if="auth.user" type="button" class="link account" :title="`Signed in as ${auth.user.email}`"
                @click="onSignOut">Sign out</button>
        <RouterLink v-else-if="auth.checked" to="/login" class="account">Sign in</RouterLink>
      </nav>
    </header>
    <!-- KeepAlive so the chat survives a trip to another page. -->
    <RouterView v-slot="{ Component }">
      <KeepAlive include="AskView">
        <component :is="Component" />
      </KeepAlive>
    </RouterView>
  </div>
</template>
