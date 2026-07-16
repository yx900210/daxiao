import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import Dashboard from './views/Dashboard.vue'
import Detail from './views/Detail.vue'
import Settings from './views/Settings.vue'
import Logs from './views/Logs.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/video/:id', component: Detail },
  { path: '/settings', component: Settings },
  { path: '/logs', component: Logs },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

createApp(App).use(router).mount('#app')
