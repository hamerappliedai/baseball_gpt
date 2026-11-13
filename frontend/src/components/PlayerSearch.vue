<script setup>
// Header typeahead: debounced search, arrow keys to move, Enter to open.
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getJSON } from '../api'

const router = useRouter()
const q = ref('')
const results = ref([])
const open = ref(false)
const active = ref(-1)
const searching = ref(false)
let timer = null
let controller = null

watch(q, (text) => {
  clearTimeout(timer)
  controller?.abort()
  const query = text.trim()
  if (query.length < 2) {
    results.value = []
    searching.value = false
    return
  }
  searching.value = true
  timer = setTimeout(async () => {
    controller = new AbortController()
    try {
      const data = await getJSON('/api/players', { q: query, limit: 8 }, controller.signal)
      results.value = data.results
      active.value = data.results.length ? 0 : -1
      open.value = true
    } catch (e) {
      if (e.name !== 'AbortError') results.value = []
    } finally {
      searching.value = false
    }
  }, 200)
})

function go(player) {
  if (!player) return
  router.push(`/players/${player.player_id}`)
  q.value = ''
  results.value = []
  open.value = false
}

function onKeydown(e) {
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault()
    open.value = true
    const n = results.value.length
    if (n) active.value = (active.value + (e.key === 'ArrowDown' ? 1 : -1) + n) % n
  } else if (e.key === 'Enter') {
    e.preventDefault()
    go(results.value[active.value])
  } else if (e.key === 'Escape') {
    open.value = false
  }
}

const years = (p) => (p.first_season === p.last_season ? p.first_season : `${p.first_season}–${p.last_season}`)
</script>

<template>
  <div class="search" @focusout="(e) => !e.currentTarget.contains(e.relatedTarget) && (open = false)">
    <input
      v-model="q"
      type="search"
      placeholder="Search players…"
      aria-label="Search players"
      role="combobox"
      aria-autocomplete="list"
      :aria-expanded="open && q.trim().length >= 2"
      aria-controls="player-results"
      @focus="open = true"
      @keydown="onKeydown"
    />
    <ul v-if="open && q.trim().length >= 2" id="player-results" class="search-results" role="listbox">
      <li v-for="(p, i) in results" :key="p.player_id" role="option" :aria-selected="i === active">
        <button type="button" :class="{ active: i === active }" @mousedown.prevent="go(p)" @mouseenter="active = i">
          <span class="who">
            {{ p.full_name }}
            <span v-if="p.is_hall_of_famer" class="tag" title="Hall of Fame">HOF</span>
          </span>
          <span class="meta">{{ years(p) }} · {{ p.primary_position || '—' }} · {{ p.teams }}</span>
        </button>
      </li>
      <li v-if="!results.length" class="search-empty">{{ searching ? 'Searching…' : 'No players found' }}</li>
    </ul>
  </div>
</template>
