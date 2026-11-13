<script setup>
// Leaderboard builder. Every filter lives in the URL query string, so any view
// can be shared as a link; the route is the single source of truth.
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { getJSON } from '../api'
import { formatValue, isNumeric } from '../format'

const route = useRoute()
const router = useRouter()

const PAGE = 50
const meta = ref(null)
const board = ref(null)
const rows = ref([])
const loading = ref(false)
const loadingMore = ref(false)
const error = ref('')
let controller = null

// --- Filters, read from and written to the URL ---------------------------------

const int = (v) => (v === undefined || v === '' || v === null || isNaN(Number(v)) ? null : Number(v))

const filters = computed(() => {
  const q = route.query
  const category = q.category === 'pitching' ? 'pitching' : 'batting'
  return {
    category,
    stat: q.stat || meta.value?.default_stat[category] || (category === 'batting' ? 'hr' : 'so'),
    scope: q.scope === 'career' ? 'career' : 'season',
    from: int(q.from),
    to: int(q.to),
    league: q.scope === 'career' ? 'all' : q.league || 'all',
    qualified: q.qualified === 'true',
  }
})

function update(changes) {
  const next = { ...filters.value, ...changes }
  const defaults = { category: 'batting', scope: 'season', league: 'all', qualified: false }
  const query = {}
  for (const [k, v] of Object.entries(next)) {
    if (v === null || v === '' || v === defaults[k]) continue
    if (k === 'stat' && v === meta.value?.default_stat[next.category]) continue
    query[k] = String(v)
  }
  router.replace({ query })
}

// --- Derived options -------------------------------------------------------------

const statOptions = computed(() => meta.value?.stats[filters.value.category] ?? [])
const currentStat = computed(() => statOptions.value.find((s) => s.key === filters.value.stat))

const leagueGroups = computed(() => {
  const leagues = meta.value?.leagues ?? []
  return [
    { label: 'Major leagues', items: leagues.filter((l) => !l.is_negro_leagues) },
    { label: 'Negro Leagues', items: leagues.filter((l) => l.is_negro_leagues && !l.is_independent_clubs) },
  ]
})

const eraKey = computed(() => {
  const { from, to } = filters.value
  return meta.value?.eras.find((e) => e.from === from && e.to === to)?.key ?? 'custom'
})

function setCategory(category) {
  update({ category, stat: meta.value.default_stat[category], qualified: false })
}

function setEra(key) {
  const era = meta.value.eras.find((e) => e.key === key)
  if (era) update({ from: era.from, to: era.to })
}

function setYear(which, value) {
  const n = int(value)
  const { first, last } = meta.value.seasons
  update({ [which]: n === null ? null : Math.min(Math.max(n, first), last) })
}

// --- Loading -----------------------------------------------------------------------

function apiParams(offset = 0) {
  const f = filters.value
  return { ...f, qualified: f.qualified ? 'true' : undefined, limit: PAGE, offset }
}

async function load() {
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  error.value = ''
  try {
    const data = await getJSON('/api/leaderboard', apiParams(), controller.signal)
    board.value = data
    rows.value = data.rows
  } catch (e) {
    if (e.name !== 'AbortError') error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  loadingMore.value = true
  try {
    const data = await getJSON('/api/leaderboard', apiParams(rows.value.length))
    rows.value = rows.value.concat(data.rows)
  } catch (e) {
    error.value = e.message
  } finally {
    loadingMore.value = false
  }
}

onMounted(async () => {
  try {
    meta.value = await getJSON('/api/meta')
  } catch (e) {
    error.value = e.message
    return
  }
  load()
})

watch(() => route.fullPath, () => {
  if (meta.value && route.path === '/leaders') load()
})

// Show a rank only on the first row of a tie, as reference sites do.
const showRank = (i) => i === 0 || rows.value[i].rank !== rows.value[i - 1].rank

const title = computed(() => {
  const f = filters.value
  const s = currentStat.value
  if (!s || !meta.value) return ''
  const span = f.from || f.to
    ? `, ${f.from ?? meta.value.seasons.first}–${f.to ?? meta.value.seasons.last}`
    : ''
  return `${f.scope === 'career' ? 'Career' : 'Single-season'} ${s.label} leaders${span}`
})
</script>

<template>
  <main class="page leaders">
    <div class="page-head">
      <h1>Leaders</h1>
      <span class="muted">Straight from the database, no AI</span>
    </div>

    <p v-if="!meta && error" class="error">Couldn't load: {{ error }}</p>

    <section v-if="meta" class="controls" aria-label="Leaderboard filters">
      <div class="segmented" role="group" aria-label="Category">
        <button v-for="c in ['batting', 'pitching']" :key="c" type="button"
                :class="{ active: filters.category === c }" @click="setCategory(c)">
          {{ c === 'batting' ? 'Batting' : 'Pitching' }}
        </button>
      </div>

      <div class="segmented" role="group" aria-label="Scope">
        <button type="button" :class="{ active: filters.scope === 'season' }" @click="update({ scope: 'season' })">
          Single season
        </button>
        <button type="button" :class="{ active: filters.scope === 'career' }"
                @click="update({ scope: 'career', league: 'all' })">
          Career
        </button>
      </div>

      <label class="field">
        <span>Stat</span>
        <select :value="filters.stat" @change="update({ stat: $event.target.value })">
          <optgroup label="Totals">
            <option v-for="s in statOptions.filter((s) => !s.rate)" :key="s.key" :value="s.key">
              {{ s.label }} · {{ s.description }}
            </option>
          </optgroup>
          <optgroup label="Rates (qualified players)">
            <option v-for="s in statOptions.filter((s) => s.rate)" :key="s.key" :value="s.key">
              {{ s.label }} · {{ s.description }}
            </option>
          </optgroup>
        </select>
      </label>

      <label class="field">
        <span>Era</span>
        <select :value="eraKey" @change="setEra($event.target.value)">
          <option v-for="e in meta.eras" :key="e.key" :value="e.key">{{ e.label }}</option>
          <option v-if="eraKey === 'custom'" value="custom">Custom range</option>
        </select>
      </label>

      <div class="field years">
        <span>Seasons</span>
        <div>
          <input type="number" inputmode="numeric" :min="meta.seasons.first" :max="meta.seasons.last"
                 :placeholder="meta.seasons.first" :value="filters.from ?? ''" aria-label="From season"
                 @change="setYear('from', $event.target.value)" />
          <span>–</span>
          <input type="number" inputmode="numeric" :min="meta.seasons.first" :max="meta.seasons.last"
                 :placeholder="meta.seasons.last" :value="filters.to ?? ''" aria-label="To season"
                 @change="setYear('to', $event.target.value)" />
        </div>
      </div>

      <label class="field">
        <span>League</span>
        <select :value="filters.league" :disabled="filters.scope === 'career'"
                :title="filters.scope === 'career' ? 'League filters apply to single seasons' : ''"
                @change="update({ league: $event.target.value })">
          <option value="all">All leagues</option>
          <option value="negro">All Negro Leagues</option>
          <optgroup v-for="g in leagueGroups" :key="g.label" :label="g.label">
            <option v-for="l in g.items" :key="l.league_id" :value="l.league_id">
              {{ l.league_name }} ({{ l.first_season }}–{{ l.last_season ?? 'now' }})
            </option>
          </optgroup>
        </select>
      </label>

      <label class="check" :title="currentStat?.rate ? 'Rate stats always use qualified players' : ''">
        <input type="checkbox" :checked="currentStat?.rate || filters.qualified"
               :disabled="currentStat?.rate" @change="update({ qualified: $event.target.checked })" />
        Qualified only
      </label>
    </section>

    <section v-if="meta" class="results">
      <div class="results-head">
        <h2>{{ title }}</h2>
        <span v-if="board" class="muted">{{ board.total.toLocaleString('en-US') }} {{ board.total === 1 ? 'row' : 'rows' }}</span>
      </div>
      <p v-if="error" class="error">{{ error }}</p>

      <div v-if="board" :class="['table-wrap', { stale: loading }]">
        <table class="data">
          <thead>
            <tr>
              <th v-for="c in board.columns" :key="c.key"
                  :class="{ num: isNumeric(c.format) || c.key === 'rank', hl: c.highlight }">{{ c.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="`${r.player_id}-${r.season ?? ''}-${r.league ?? ''}`">
              <td v-for="c in board.columns" :key="c.key"
                  :class="{ num: isNumeric(c.format) || c.key === 'rank', hl: c.highlight, name: c.format === 'player' }">
                <template v-if="c.key === 'rank'">{{ showRank(i) ? r.rank : '' }}</template>
                <RouterLink v-else-if="c.format === 'player'" :to="`/players/${r.player_id}`">{{ r.full_name }}</RouterLink>
                <template v-else>{{ formatValue(r[c.key], c.format) }}</template>
              </td>
            </tr>
            <tr v-if="!rows.length && !loading">
              <td :colspan="board.columns.length" class="empty-row">No players match these filters.</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else-if="loading" class="muted">Loading…</p>

      <div v-if="board" class="results-foot">
        <button v-if="rows.length < board.total" type="button" class="secondary"
                :disabled="loadingMore" @click="loadMore">
          {{ loadingMore ? 'Loading…' : `Show ${Math.min(PAGE, board.total - rows.length)} more` }}
        </button>
        <ul v-if="board.notes.length" class="notes">
          <li v-for="n in board.notes" :key="n">{{ n }}</li>
        </ul>
      </div>
    </section>
  </main>
</template>
