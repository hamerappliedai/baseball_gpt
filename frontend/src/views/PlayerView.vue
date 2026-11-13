<script setup>
// One player's page, from GET /api/players/{id}. No AI involved.
import { computed, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { getJSON } from '../api'
import { formatDate } from '../format'
import StatTable from '../components/StatTable.vue'

const route = useRoute()
const data = ref(null)
const error = ref('')
const loading = ref(false)

watch(
  () => route.params.playerId,
  async (id) => {
    if (!id) return
    loading.value = true
    error.value = ''
    try {
      data.value = await getJSON(`/api/players/${encodeURIComponent(id)}`)
      document.title = `${data.value.player.full_name} · Baseball GPT`
    } catch (e) {
      data.value = null
      error.value = e.message
    } finally {
      loading.value = false
    }
  },
  { immediate: true },
)

const c = (key, label, format = 'int', title) => ({ key, label, format, title })

const battingCols = [
  c('season', 'Year', 'year'), c('team_ids', 'Team', 'text'), c('league_ids', 'Lg', 'text'),
  c('g', 'G'), c('pa', 'PA'), c('ab', 'AB'), c('r', 'R'), c('h', 'H'), c('doubles', '2B'),
  c('triples', '3B'), c('hr', 'HR'), c('rbi', 'RBI'), c('sb', 'SB'), c('cs', 'CS'), c('bb', 'BB'),
  c('so', 'SO'), c('avg', 'AVG', 'rate3'), c('obp', 'OBP', 'rate3'), c('slg', 'SLG', 'rate3'),
  c('ops', 'OPS', 'rate3'), c('tb', 'TB'),
]
const pitchingCols = [
  c('season', 'Year', 'year'), c('team_ids', 'Team', 'text'), c('league_ids', 'Lg', 'text'),
  c('w', 'W'), c('l', 'L'), c('win_pct', 'W-L%', 'rate3'), c('era', 'ERA', 'dec2'), c('g', 'G'),
  c('gs', 'GS'), c('cg', 'CG'), c('sho', 'SHO'), c('sv', 'SV'), c('ip_display', 'IP', 'ip'),
  c('h', 'H'), c('r', 'R'), c('er', 'ER'), c('hr', 'HR'), c('bb', 'BB'), c('so', 'SO'),
  c('whip', 'WHIP', 'dec2'), c('so9', 'SO/9', 'dec2'),
]
const fieldingCols = [
  c('position', 'Pos', 'text'), c('years', 'Years', 'text'), c('g', 'G'), c('gs', 'GS'),
  c('po', 'PO', 'int', 'Putouts'), c('a', 'A', 'int', 'Assists'), c('e', 'E', 'int', 'Errors'),
  c('dp', 'DP', 'int', 'Double plays'), c('fielding_pct', 'Fld%', 'rate3'),
]
const postBattingCols = [
  c('season', 'Year', 'year'), c('round_name', 'Round', 'text'), c('team_id', 'Team', 'text'),
  c('g', 'G'), c('pa', 'PA'), c('h', 'H'), c('hr', 'HR'), c('rbi', 'RBI'), c('bb', 'BB'), c('so', 'SO'),
  c('avg', 'AVG', 'rate3'), c('obp', 'OBP', 'rate3'), c('slg', 'SLG', 'rate3'),
]
const postPitchingCols = [
  c('season', 'Year', 'year'), c('round_name', 'Round', 'text'), c('team_id', 'Team', 'text'),
  c('w', 'W'), c('l', 'L'), c('g', 'G'), c('gs', 'GS'), c('sv', 'SV'), c('ip_display', 'IP', 'ip'),
  c('h', 'H'), c('er', 'ER'), c('bb', 'BB'), c('so', 'SO'), c('era', 'ERA', 'dec2'), c('whip', 'WHIP', 'dec2'),
]
const votingCols = [
  c('season', 'Year', 'year'), c('award', 'Award', 'text'), c('league_id', 'Lg', 'text'),
  c('finish', 'Finish'), c('vote_share', 'Share', 'pct'), c('first_place_votes', '1st-place votes'),
]
const hofCols = [
  c('season', 'Year', 'year'), c('voted_by', 'Voted by', 'text'), c('votes', 'Votes'),
  c('votes_needed', 'Needed'), c('vote_pct', 'Share', 'pct'), c('result', 'Result', 'text'),
]

const p = computed(() => data.value?.player)
// Pitchers see their pitching first.
const pitchingFirst = computed(() => p.value?.primary_position === 'P')

const fielding = computed(() =>
  (data.value?.fielding ?? []).map((f) => ({
    ...f,
    years: f.first_season === f.last_season ? `${f.first_season}` : `${f.first_season}–${f.last_season}`,
  })),
)
const hofVoting = computed(() =>
  (data.value?.honors.hall_of_fame_voting ?? []).map((v) => ({ ...v, result: v.is_inducted ? 'Inducted' : '' })),
)

const place = (...parts) => parts.filter(Boolean).join(', ')
const height = (inches) => (inches ? `${Math.floor(inches / 12)}′${inches % 12}″` : '')

const bioLines = computed(() => {
  const x = p.value
  if (!x) return []
  const lines = []
  if (x.birth_date || x.birth_city) {
    lines.push(`Born ${[formatDate(x.birth_date), place(x.birth_city, x.birth_state, x.birth_country)].filter(Boolean).join(' in ')}`)
  }
  if (x.death_date || x.death_city) {
    lines.push(`Died ${[formatDate(x.death_date), place(x.death_city, x.death_state, x.death_country)].filter(Boolean).join(' in ')}`)
  }
  const body = [x.bats && `Bats ${x.bats}`, x.throws && `Throws ${x.throws}`, height(x.height_in),
    x.weight_lbs && `${x.weight_lbs} lb`].filter(Boolean)
  if (body.length) lines.push(body.join(' · '))
  if (x.debut_date) lines.push(`Debut ${formatDate(x.debut_date)} · Last game ${formatDate(x.final_game_date)}`)
  return lines
})

const span = (seasons) => {
  if (!seasons.length) return ''
  return seasons.length > 1 && seasons.at(-1) - seasons[0] === seasons.length - 1
    ? `${seasons[0]}–${seasons.at(-1)}`
    : seasons.join(', ')
}

const bbrefUrl = computed(() => {
  const id = p.value?.bbref_id
  return id ? `https://www.baseball-reference.com/players/${id[0]}/${id}.shtml` : null
})
</script>

<template>
  <main class="page player">
    <p v-if="loading && !data" class="muted">Loading…</p>
    <p v-else-if="error" class="error">{{ error }}</p>

    <template v-if="p">
      <header class="player-head">
        <div>
          <h1>{{ p.full_name }}</h1>
          <p class="muted">
            {{ p.first_season === p.last_season ? p.first_season : `${p.first_season}–${p.last_season}` }}
            · {{ p.primary_position || '—' }} · {{ p.teams }}
          </p>
          <div class="badges">
            <span v-if="p.is_hall_of_famer" class="tag hof">
              Hall of Fame {{ p.hof_induction_year }}<template v-if="p.hof_voted_by"> · {{ p.hof_voted_by }}</template>
            </span>
            <span v-if="p.played_negro_leagues" class="tag">Negro Leagues</span>
            <span v-if="p.is_manager" class="tag">Also managed</span>
          </div>
        </div>
        <div class="player-links">
          <RouterLink :to="{ path: '/ask', query: { q: `Tell me about ${p.full_name}'s career.` } }">
            Ask AI about {{ p.full_name.split(' ').at(-1) }}
          </RouterLink>
          <a v-if="bbrefUrl" :href="bbrefUrl" target="_blank" rel="noopener">Baseball-Reference ↗</a>
        </div>
      </header>

      <section class="bio">
        <p v-for="line in bioLines" :key="line">{{ line }}</p>
        <p v-if="p.name_given" class="muted">Full name: {{ p.name_given }} {{ p.full_name.split(' ').at(-1) }}</p>
      </section>

      <div :class="['stat-sections', { 'pitching-first': pitchingFirst }]">
        <section v-if="data.batting" class="batting">
          <h2>Batting</h2>
          <StatTable :columns="battingCols" :rows="data.batting.seasons" :footer="data.batting.career"
                     :row-key="(r) => r.season" />
        </section>
        <section v-if="data.pitching" class="pitching">
          <h2>Pitching</h2>
          <StatTable :columns="pitchingCols" :rows="data.pitching.seasons" :footer="data.pitching.career"
                     :row-key="(r) => r.season" />
        </section>
      </div>

      <section v-if="fielding.length">
        <h2>Fielding by position</h2>
        <StatTable :columns="fieldingCols" :rows="fielding" :row-key="(r) => r.position" />
      </section>

      <section v-if="data.postseason.batting.length || data.postseason.pitching.length">
        <h2>Postseason</h2>
        <StatTable v-if="data.postseason.batting.length" :columns="postBattingCols" :rows="data.postseason.batting" />
        <StatTable v-if="data.postseason.pitching.length" :columns="postPitchingCols" :rows="data.postseason.pitching" />
      </section>

      <section v-if="data.honors.awards.length || data.honors.all_star_seasons.length || data.honors.award_voting.length || hofVoting.length">
        <h2>Honors</h2>
        <ul class="honors">
          <li v-if="data.honors.all_star_seasons.length">
            <strong>All-Star</strong> ({{ data.honors.all_star_seasons.length }}×): {{ span(data.honors.all_star_seasons) }}
          </li>
          <li v-for="a in data.honors.awards" :key="a.award">
            <strong>{{ a.award }}</strong><template v-if="a.seasons.length > 1"> ({{ a.seasons.length }}×)</template>:
            {{ span(a.seasons) }}
          </li>
        </ul>
        <template v-if="data.honors.award_voting.length">
          <h3>Top-5 award finishes</h3>
          <StatTable :columns="votingCols" :rows="data.honors.award_voting" />
        </template>
        <template v-if="hofVoting.length">
          <h3>Hall of Fame voting</h3>
          <StatTable :columns="hofCols" :rows="hofVoting" />
        </template>
      </section>

      <p class="muted source">Source: SABR Lahman Baseball Database (CC BY-SA 3.0). Straight from SQL, no AI.</p>
    </template>
  </main>
</template>
