<script setup>
import { nextTick, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { streamChat } from '../api'
import { auth, refreshUser, signedOut } from '../auth'

// [{ role, content, error?, queries?: [{ id, purpose, sql, status, rows?, truncated?, error? }] }]
const messages = ref([])
const question = ref('')
const streaming = ref(false)
const logEl = ref(null)
const route = useRoute()
let controller = null

// A link like /ask?q=... (from a player page) prefills the question; the user still sends it.
watch(
  () => route.query.q,
  (q) => {
    if (typeof q === 'string' && q && !streaming.value) question.value = q
  },
  { immediate: true },
)

const examples = [
  'Who hit the most home runs in a single season?',
  'Compare Ted Williams and Joe DiMaggio in 1941.',
  'Which franchises have won the most World Series?',
  "What were Josh Gibson's best seasons?",
]

// A different person (or nobody) signed in: don't show the last conversation.
watch(
  () => auth.user?.email,
  (now, before) => {
    if (now !== before) {
      controller?.abort()
      messages.value = []
    }
  },
)

// Tables go in a scroll box so wide results scroll sideways instead of wrapping.
const render = (text) =>
  DOMPurify.sanitize(marked.parse(text))
    .replaceAll('<table>', '<div class="table-scroll"><table>')
    .replaceAll('</table>', '</table></div>')
const fmt = (n) => Number(n).toLocaleString()
const usedPct = () => {
  const a = auth.allowance
  if (!a) return 0
  if (a.daily_token_limit <= 0) return 100
  return Math.min(100, Math.round((100 * a.tokens_today) / a.daily_token_limit))
}

async function scrollToBottom() {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}

function queryLabel(q) {
  if (q.status === 'running') return 'running…'
  if (q.error) return 'failed'
  return `${q.rows} row${q.rows === 1 ? '' : 's'}${q.truncated ? '+' : ''}`
}

async function ask(text = question.value.trim()) {
  if (!text || streaming.value) return

  // History sent to the API: only successful turns, as plain text.
  const history = messages.value
    .filter((m) => !m.error && m.content)
    .map(({ role, content }) => ({ role, content }))
  history.push({ role: 'user', content: text })

  messages.value.push({ role: 'user', content: text })
  messages.value.push({ role: 'assistant', content: '', queries: [] })
  const reply = messages.value[messages.value.length - 1]
  question.value = ''
  streaming.value = true
  controller = new AbortController()
  scrollToBottom()

  try {
    await streamChat(
      history,
      (event) => {
        if (event.type === 'text') reply.content += event.text
        else if (event.type === 'query') {
          reply.queries.push({ id: event.id, purpose: event.purpose, sql: event.sql, status: 'running' })
        } else if (event.type === 'query_result') {
          const q = reply.queries.find((x) => x.id === event.id)
          if (q) Object.assign(q, { status: 'done', rows: event.rows, truncated: event.truncated, error: event.error })
        } else if (event.type === 'error') reply.error = event.message
        scrollToBottom()
      },
      controller.signal,
    )
  } catch (err) {
    if (err.status === 401) signedOut() // session expired: show the sign-in prompt
    if (err.name !== 'AbortError') reply.error = err.message
  } finally {
    streaming.value = false
    controller = null
    refreshUser() // updates the allowance shown under the composer
  }
}

function stop() {
  controller?.abort()
}

function clearChat() {
  messages.value = []
}

function onKeydown(e) {
  // Enter sends, Shift+Enter inserts a newline.
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    ask()
  }
}
</script>

<template>
  <main class="chat">
    <div class="page-head">
      <h1>Ask AI</h1>
      <button v-if="auth.user" class="link" :disabled="streaming || !messages.length" @click="clearChat">New chat</button>
    </div>

    <section v-if="auth.checked && !auth.user" class="gate">
      <h2>Sign in to ask questions</h2>
      <p>
        Ask AI sends your question to Claude, which writes and runs SQL against the database and
        explains the answer. Each question costs real money, so it's open to invited accounts only.
      </p>
      <p>
        <RouterLink :to="{ path: '/login', query: { next: '/ask' } }" class="button">Sign in</RouterLink>
      </p>
      <p class="muted">
        Everything else is free and needs no account:
        <RouterLink to="/leaders">Leaders</RouterLink>, <RouterLink to="/standings">Standings</RouterLink>
        and player pages (use the search box).
      </p>
    </section>

    <section v-else ref="logEl" class="log">
      <div v-if="!messages.length" class="empty">
        <p>Ask about 150 years of major league baseball, Negro Leagues included.<br />Answers come from SQL over the SABR Lahman database.</p>
        <div class="examples">
          <button v-for="ex in examples" :key="ex" class="example" @click="ask(ex)">{{ ex }}</button>
        </div>
      </div>
      <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
        <div v-if="m.role === 'user'" class="bubble">{{ m.content }}</div>
        <div v-else class="bubble">
          <details v-if="m.queries?.length" class="queries">
            <summary>
              {{ m.queries.length }} quer{{ m.queries.length === 1 ? 'y' : 'ies' }}
              <span v-if="m.queries.some((q) => q.status === 'running')" class="typing">running…</span>
            </summary>
            <div v-for="q in m.queries" :key="q.id" class="query">
              <div class="query-head">
                <span>{{ q.purpose || 'Query' }}</span>
                <span :class="['badge', { failed: q.error }]">{{ queryLabel(q) }}</span>
              </div>
              <pre><code>{{ q.sql }}</code></pre>
              <p v-if="q.error" class="error">{{ q.error }}</p>
            </div>
          </details>
          <div v-if="m.content" class="md" v-html="render(m.content)"></div>
          <span v-else-if="streaming && i === messages.length - 1" class="typing">
            {{ m.queries?.length ? 'Querying the database…' : 'Thinking…' }}
          </span>
          <p v-if="m.error" class="error">{{ m.error }}</p>
        </div>
      </div>
    </section>

    <form v-if="auth.user" class="composer" @submit.prevent="ask()">
      <textarea
        v-model="question"
        rows="3"
        placeholder="Ask a baseball question… (Enter to send, Shift+Enter for a new line)"
        :disabled="streaming"
        @keydown="onKeydown"
      ></textarea>
      <button v-if="streaming" type="button" @click="stop">Stop</button>
      <button v-else type="submit" :disabled="!question.trim()">Send</button>
    </form>
    <p v-if="auth.user && auth.allowance" class="allowance muted"
       :title="`${fmt(auth.allowance.tokens_today)} of ${fmt(auth.allowance.daily_token_limit)} tokens in the last 24 hours (cache reads count a tenth)`">
      {{ usedPct() }}% of today's allowance used ·
      {{ auth.allowance.questions_last_hour }}/{{ auth.allowance.hourly_question_limit }} questions this hour
    </p>
  </main>
</template>
