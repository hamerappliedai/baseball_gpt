<script setup>
// Final standings and postseason results for one season, from
// GET /api/standings/{season}. No AI involved.
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getJSON } from '../api'
import { formatValue } from '../format'

const route = useRoute()
const router = useRouter()
const data = ref(null)
const seasons = ref(null) // { first, last }
const error = ref('')
const loading = ref(false)

async function load(param) {
  error.value = ''
  loading.value = true
  try {
    if (!seasons.value) seasons.value = (await getJSON('/api/meta')).seasons
    // /standings with no year shows the latest season.
    if (!param) {
      router.replace(`/standings/${seasons.value.last}`)
      return
    }
    data.value = await getJSON(`/api/standings/${encodeURIComponent(param)}`)
    document.title = `${data.value.season} Standings · Baseball GPT`
  } catch (e) {
    data.value = null
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => route.params.season, (s) => route.path.startsWith('/standings') && load(s), { immediate: true })

const season = computed(() => data.value?.season ?? Number(route.params.season))
const years = computed(() => {
  if (!seasons.value) return []
  const out = []
  for (let y = seasons.value.last; y >= seasons.value.first; y--) out.push(y)
  return out
})
const go = (y) => y && router.push(`/standings/${y}`)

const gb = (v) => (Number(v) === 0 ? '—' : Number(v) % 1 ? Number(v).toFixed(1) : String(Number(v)))
const diff = (v) => (v > 0 ? `+${v}` : String(v))
const pct = (v) => formatValue(v, 'rate3')

function badges(t) {
  const out = []
  if (t.won_world_series) out.push({ label: 'WS', title: 'Won the World Series', cls: 'ws' })
  else if (t.won_pennant) out.push({ label: 'Pennant', title: 'Won the pennant', cls: 'pen' })
  if (t.won_division) out.push({ label: 'Div', title: 'Won the division', cls: '' })
  if (t.won_wild_card) out.push({ label: 'WC', title: 'Wild card', cls: '' })
  return out
}

const champion = computed(() => data.value?.champion)
</script>

<template>
  <main class="page standings">
    <div class="page-head">
      <h1>{{ season || '' }} Standings</h1>
      <div v-if="seasons" class="season-picker">
        <button type="button" class="secondary" :disabled="!data || season <= seasons.first"
                aria-label="Previous season" @click="go(season - 1)">‹</button>
        <select :value="season" aria-label="Season" @change="go($event.target.value)">
          <option v-for="y in years" :key="y" :value="y">{{ y }}</option>
        </select>
        <button type="button" class="secondary" :disabled="!data || season >= seasons.last"
                aria-label="Next season" @click="go(season + 1)">›</button>
      </div>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-else-if="loading && !data" class="muted">Loading…</p>

    <template v-if="data">
      <p v-if="champion" class="champion">
        🏆 <strong>{{ champion.winner_team_name }}</strong> won the World Series,
        beating the {{ champion.loser_team_name }} {{ champion.wins }}–{{ champion.losses }}<template v-if="champion.ties">–{{ champion.ties }}</template>.
      </p>

      <section v-for="lg in data.leagues" :key="lg.league_id" :class="['league', { stale: loading }]">
        <h2>
          {{ lg.league_name }}
          <span v-if="lg.is_negro_leagues && !lg.is_independent_clubs" class="tag">Negro Leagues</span>
        </h2>
        <p v-if="lg.is_independent_clubs" class="muted">
          Independent clubs didn't play a league schedule; these are their recorded games.
        </p>
        <div class="divisions">
          <div v-for="dv in lg.divisions" :key="dv.division_id ?? 'all'" class="division">
            <h3 v-if="dv.name">{{ dv.name }}</h3>
            <div class="table-wrap">
              <table class="data">
                <thead>
                  <tr>
                    <th>Team</th>
                    <th class="num">W</th>
                    <th class="num">L</th>
                    <th class="num">PCT</th>
                    <th class="num">GB</th>
                    <th class="num" title="Runs scored">RS</th>
                    <th class="num" title="Runs allowed">RA</th>
                    <th class="num" title="Run differential">Diff</th>
                    <th class="num" title="Pythagorean (expected) record from runs scored and allowed">Pyth</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="t in dv.teams" :key="t.team_id">
                    <td class="name">
                      {{ t.team_name }}
                      <span v-for="b in badges(t)" :key="b.label" :class="['tag', b.cls]" :title="b.title">{{ b.label }}</span>
                    </td>
                    <td class="num">{{ t.w }}</td>
                    <td class="num">{{ t.l }}</td>
                    <td class="num">{{ pct(t.win_pct) }}</td>
                    <td class="num">{{ gb(t.gb) }}</td>
                    <td class="num">{{ t.r ?? '—' }}</td>
                    <td class="num">{{ t.ra ?? '—' }}</td>
                    <td :class="['num', t.run_diff > 0 ? 'pos' : t.run_diff < 0 ? 'neg' : '']">{{ t.run_diff == null ? '—' : diff(t.run_diff) }}</td>
                    <td class="num">{{ t.pythag_w == null ? '—' : `${t.pythag_w}-${t.pythag_l}` }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <section v-if="data.postseason.length" class="postseason">
        <h2>Postseason</h2>
        <div class="bracket">
          <div v-for="stage in data.postseason" :key="stage.stage_order" class="stage">
            <h3>{{ stage.stage }}</h3>
            <div v-for="s in stage.series" :key="s.round" class="series" :title="s.round_name">
              <div class="series-name">{{ s.round_name }}</div>
              <div class="winner"><span>{{ s.winner_team_name }}</span><span>{{ s.wins }}</span></div>
              <div class="loser"><span>{{ s.loser_team_name }}</span><span>{{ s.losses }}</span></div>
              <div v-if="s.ties" class="muted">{{ s.ties }} tie{{ s.ties > 1 ? 's' : '' }}</div>
            </div>
          </div>
        </div>
      </section>
      <p v-else class="muted">No postseason series recorded for {{ data.season }}.</p>

      <p class="muted source">
        Teams are listed in Lahman's final order, which includes tiebreakers. GB is games behind the
        leader. Pyth is the record expected from runs scored and allowed.
      </p>
    </template>
  </main>
</template>
