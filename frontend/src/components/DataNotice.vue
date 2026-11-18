<script setup>
// "Stats run through the 2025 season" notice. The latest season comes from
// /api/meta, so the text moves on by itself when a new Lahman release is loaded.
// Pass `season` to show it only when that season is the latest (a player
// whose career reaches the present).
import { computed, ref } from 'vue'
import { getMeta } from '../api'

const props = defineProps({ season: { type: Number, default: null } })
const last = ref(null)
getMeta().then((m) => (last.value = m.seasons.last)).catch(() => {})

const show = computed(() => last.value && (props.season == null || props.season >= last.value))
</script>

<template>
  <p v-if="show" class="data-notice" role="note">
    Stats run through the {{ last }} season. {{ last + 1 }} season data will be added in early {{ last + 2 }}.
  </p>
</template>
