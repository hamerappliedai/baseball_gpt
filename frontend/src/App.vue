<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="shell">
    <header class="topbar">
      <RouterLink to="/" class="brand">⚾ Baseball GPT</RouterLink>
      <nav>
        <RouterLink to="/leaders">Leaders</RouterLink>
        <RouterLink to="/ask">Ask AI</RouterLink>
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
