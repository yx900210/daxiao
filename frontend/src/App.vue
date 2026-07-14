<template>
  <div id="app-root">
    <header class="app-header">
      <h1>🌳 李大霄视频追踪</h1>
      <nav>
        <router-link to="/">首页</router-link>
      </nav>
    </header>
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f5f5f5; color: #333; }
.app-header { background: #1a1a2e; color: #eee; padding: 16px 24px; display: flex; align-items: center; justify-content: space-between; }
.app-header h1 { font-size: 18px; }
.app-header a { color: #8ab4f8; text-decoration: none; font-size: 14px; }
.app-main { max-width: 960px; margin: 0 auto; padding: 20px; }
</style>
