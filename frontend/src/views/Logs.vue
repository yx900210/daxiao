<template>
  <div class="logs-page">
    <h2>系统日志 <button class="btn-refresh" @click="fetchLogs">🔄 刷新</button></h2>
    <div class="log-box" ref="logBox">{{ logs }}</div>
  </div>
</template>

<script>
export default {
  data() {
    return { logs: '', timer: null }
  },
  mounted() {
    this.fetchLogs()
    this.timer = setInterval(this.fetchLogs, 5000)
  },
  beforeUnmount() {
    clearInterval(this.timer)
  },
  methods: {
    async fetchLogs() {
      try {
        const r = await fetch('/api/logs?lines=200')
        const d = await r.json()
        this.logs = d.lines.join('')
        this.$nextTick(() => {
          const el = this.$refs.logBox
          if (el) el.scrollTop = el.scrollHeight
        })
      } catch(e) {}
    },
  },
}
</script>

<style scoped>
.logs-page { max-width: 100%; }
h2 { font-size: 16px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; }
.btn-refresh { background: #1a1a2e; color: #fff; border: none; padding: 4px 12px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.log-box { background: #0d1117; color: #7ee787; font-family: 'SF Mono', 'Menlo', monospace; font-size: 12px; padding: 16px; border-radius: 6px; height: calc(100vh - 120px); overflow-y: auto; white-space: pre-wrap; word-break: break-all; line-height: 1.6; }
</style>
