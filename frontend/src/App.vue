<script setup>
import { nextTick, ref } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { streamChat } from './api'

const messages = ref([]) // [{ role, content, error? }]
const question = ref('')
const streaming = ref(false)
const logEl = ref(null)
let controller = null

const render = (text) => DOMPurify.sanitize(marked.parse(text))

async function scrollToBottom() {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
}

async function ask() {
  const text = question.value.trim()
  if (!text || streaming.value) return

  // History sent to the API: only successful turns.
  const history = messages.value
    .filter((m) => !m.error && m.content)
    .map(({ role, content }) => ({ role, content }))
  history.push({ role: 'user', content: text })

  messages.value.push({ role: 'user', content: text })
  messages.value.push({ role: 'assistant', content: '' })
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
        else if (event.type === 'error') reply.error = event.message
        scrollToBottom()
      },
      controller.signal,
    )
  } catch (err) {
    if (err.name !== 'AbortError') reply.error = err.message
  } finally {
    streaming.value = false
    controller = null
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
    <header>
      <h1>Claude Chat Agent</h1>
      <button class="link" :disabled="streaming || !messages.length" @click="clearChat">New chat</button>
    </header>

    <section ref="logEl" class="log">
      <p v-if="!messages.length" class="empty">Ask a question to get started.</p>
      <div v-for="(m, i) in messages" :key="i" :class="['msg', m.role]">
        <div v-if="m.role === 'user'" class="bubble">{{ m.content }}</div>
        <div v-else class="bubble">
          <div v-if="m.content" class="md" v-html="render(m.content)"></div>
          <span v-else-if="streaming && i === messages.length - 1" class="typing">Thinking…</span>
          <p v-if="m.error" class="error">{{ m.error }}</p>
        </div>
      </div>
    </section>

    <form class="composer" @submit.prevent="ask">
      <textarea
        v-model="question"
        rows="3"
        placeholder="Ask Claude anything… (Enter to send, Shift+Enter for a new line)"
        :disabled="streaming"
        @keydown="onKeydown"
      ></textarea>
      <button v-if="streaming" type="button" @click="stop">Stop</button>
      <button v-else type="submit" :disabled="!question.trim()">Send</button>
    </form>
  </main>
</template>
