<template>
  <div class="app-layout">
    <button class="menu-toggle" @click="menuOpen = !menuOpen">☰</button>
    <aside class="sidebar" :class="{ open: menuOpen }">
      <div class="logo">🌳<span class="logo-text">李大霄是个好人</span></div>
      <nav class="nav-links">
        <router-link to="/" class="nav-item" @click="menuOpen = false">🏠 首页</router-link>
        <router-link to="/logs" class="nav-item" @click="menuOpen = false">📋 日志</router-link>
        <router-link to="/settings" class="nav-item" @click="menuOpen = false">⚙️ 设置</router-link>
      </nav>
    </aside>
    <div class="sidebar-overlay" v-if="menuOpen" @click="menuOpen = false"></div>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script>
export default {
  data() { return { menuOpen: false } },
}
</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; color: #1a1a2e; }
.app-layout { display: flex; min-height: 100vh; position: relative; }
.menu-toggle { display: none; }
.sidebar { width: 200px; background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%); color: #a8b2d1; padding: 24px 0; flex-shrink: 0; flex-direction: column; transition: transform .25s; z-index: 200; }
.logo { padding: 0 20px 24px; font-size: 18px; font-weight: 700; color: #e0e6ff; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 8px; }
.logo-text { font-size: 15px; }
.nav-links { flex: 1; padding: 8px 12px; }
.nav-item { display: block; padding: 10px 14px; border-radius: 8px; color: #8892b0; text-decoration: none; font-size: 14px; font-weight: 500; transition: all .15s; margin-bottom: 2px; }
.nav-item:hover { background: rgba(255,255,255,0.06); color: #ccd6f6; }
.nav-item.router-link-active { background: rgba(99,102,241,0.2); color: #a5b4fc; }
.main-content { flex: 1; padding: 28px 32px; overflow-y: auto; min-width: 0; }
.sidebar-overlay { display: none; }

@media (max-width: 768px) {
  .menu-toggle { display: flex; align-items: center; justify-content: center; position: fixed; top: 10px; left: 10px; z-index: 210; background: #1a1a2e; color: #fff; border: none; width: 36px; height: 36px; border-radius: 8px; font-size: 18px; cursor: pointer; }
  .sidebar { position: fixed; top: 0; left: 0; bottom: 0; transform: translateX(-100%); display: flex; }
  .sidebar.open { transform: translateX(0); }
  .sidebar-overlay { display: block; position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 190; }
  .main-content { padding: 56px 12px 12px; }
}
</style>
