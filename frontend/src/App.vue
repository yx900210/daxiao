<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="logo">🌳<span class="logo-text">李大霄是个好人</span></div>
      <nav class="nav-links">
        <router-link to="/" class="nav-item">🏠 首页</router-link>
        <router-link to="/logs" class="nav-item">📋 日志</router-link>
        <router-link to="/settings" class="nav-item">⚙️ 设置</router-link>
      </nav>
    </aside>
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f0f2f5; color: #1a1a2e; }
.app-layout { display: flex; min-height: 100vh; }
.sidebar { width: 200px; background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%); color: #a8b2d1; padding: 24px 0; flex-shrink: 0; display: flex; flex-direction: column; }
.logo { padding: 0 20px 24px; font-size: 18px; font-weight: 700; color: #e0e6ff; display: flex; align-items: center; gap: 8px; border-bottom: 1px solid rgba(255,255,255,0.08); margin-bottom: 8px; }
.logo-text { font-size: 15px; }
.nav-links { flex: 1; padding: 8px 12px; }
.nav-item { display: block; padding: 10px 14px; border-radius: 8px; color: #8892b0; text-decoration: none; font-size: 14px; font-weight: 500; transition: all .15s; margin-bottom: 2px; }
.nav-item:hover { background: rgba(255,255,255,0.06); color: #ccd6f6; }
.nav-item.router-link-active { background: rgba(99,102,241,0.2); color: #a5b4fc; }
.main-content { flex: 1; padding: 28px 32px; overflow-y: auto; max-width: 1200px; }
</style>
