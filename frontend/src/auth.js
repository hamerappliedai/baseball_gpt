// Who is signed in, shared by the header, the sign-in page and Ask AI.
// The session itself is an HttpOnly cookie the browser sends; this only
// mirrors /api/auth/me so the UI knows what to show.
import { reactive } from 'vue'

export const auth = reactive({
  user: null, // { email, display_name, role }
  allowance: null, // { tokens_today, daily_token_limit, questions_last_hour, hourly_question_limit, max_turns }
  checked: false,
})

async function postJSON(path, body) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  let data = null
  try {
    data = await res.json()
  } catch {}
  if (!res.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `${res.status} ${res.statusText}`)
  return data
}

export async function refreshUser() {
  try {
    const res = await fetch('/api/auth/me')
    if (res.ok) {
      const data = await res.json()
      auth.user = data.user
      auth.allowance = data.allowance
    } else {
      auth.user = null
      auth.allowance = null
    }
  } catch {
    // Network trouble: keep whatever we knew.
  } finally {
    auth.checked = true
  }
}

export async function signIn(email, password) {
  await postJSON('/api/auth/login', { email, password })
  await refreshUser()
}

export async function signOut() {
  try {
    await postJSON('/api/auth/logout')
  } finally {
    auth.user = null
    auth.allowance = null
  }
}

export function signedOut() {
  auth.user = null
  auth.allowance = null
}
