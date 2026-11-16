import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import LeadersView from './views/LeadersView.vue'
import AskView from './views/AskView.vue'
import PlayerView from './views/PlayerView.vue'
import StandingsView from './views/StandingsView.vue'
import LoginView from './views/LoginView.vue'
import { refreshUser } from './auth'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/leaders' },
    { path: '/leaders', component: LeadersView, meta: { title: 'Leaders' } },
    { path: '/players/:playerId', component: PlayerView, meta: { title: 'Player' } },
    { path: '/standings/:season?', component: StandingsView, meta: { title: 'Standings' } },
    { path: '/ask', component: AskView, meta: { title: 'Ask AI' } },
    { path: '/login', component: LoginView, meta: { title: 'Sign in' } },
    { path: '/:pathMatch(.*)*', redirect: '/leaders' },
  ],
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · Baseball GPT` : 'Baseball GPT'
})

refreshUser()
createApp(App).use(router).mount('#app')
