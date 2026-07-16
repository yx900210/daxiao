<template>
  <div class="dashboard">
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-num">{{ stats.total_videos }}</div>
        <div class="stat-label">总视频</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.processed }}</div>
        <div class="stat-label">已处理</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">{{ stats.pending }}</div>
        <div class="stat-label">待处理</div>
      </div>
    </div>

    <div class="toolbar">
      <button class="btn-primary" @click="triggerScrape" :disabled="scraping">
        {{ scraping ? '抓取中...' : '立即抓取' }}
      </button>
      <button class="btn-primary btn-process" @click="triggerProcess" :disabled="processing">
        {{ processing ? '处理中...' : '处理所有视频' }}
      </button>
      <span class="last-scrape" v-if="stats.last_scrape">
        上次抓取: {{ formatTime(stats.last_scrape) }}
      </span>
      <span class="msg" v-if="scrapeMsg">{{ scrapeMsg }}</span>
    </div>

    <div class="filter-bar">
      <button v-for="s in statusFilters" :key="s.value"
              :class="{ active: statusFilter === s.value }"
              @click="statusFilter = s.value">{{ s.label }}</button>
    </div>

    <div class="video-list" v-if="videos.length">
      <div class="video-row" v-for="v in videos" :key="v.id" @click="goDetail(v.id)">
        <div class="vid-status">
          <span class="status-dot" :class="statusClass(v.fetch_status)"></span>
          {{ statusLabel(v.fetch_status) }}
        </div>
        <div class="vid-info">
          <div class="vid-title">{{ v.title || '无标题' }}</div>
          <div class="vid-meta">
            {{ formatTime(v.publish_time) }} &middot; {{ fmtDuration(v.duration) }}
            &middot; ❤️{{ v.like_count }}
          </div>
        </div>
        <div class="vid-actions">
          <button class="btn-tiny" @click.stop="processOne(v.id)" :disabled="v.fetch_status === 'processing'">
            {{ v.fetch_status === 'processing' ? '⏳' : '▶' }}
          </button>
        </div>
      </div>
    </div>

    <div class="pagination" v-if="total > pageSize">
      <button :disabled="page <= 1" @click="page--">上一页</button>
      <span>{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
      <button :disabled="page >= Math.ceil(total / pageSize)" @click="page++">下一页</button>
    </div>
  </div>
</template>

<script>
export default {
  data() {
    return {
      stats: { total_videos: 0, processed: 0, pending: 0, last_scrape: null },
      videos: [],
      total: 0,
      page: 1,
      pageSize: 20,
      statusFilter: '',
      statusFilters: [
        { label: '全部', value: '' },
        { label: '待处理', value: 'pending' },
        { label: '进行中', value: 'processing' },
        { label: '已完成', value: 'done' },
        { label: '失败', value: 'failed' },
      ],
      scraping: false,
      scrapeMsg: '',
      processing: false,
      processMsg: '',
    }
  },
  watch: {
    statusFilter() { this.page = 1; this.fetchVideos() },
    page() { this.fetchVideos() },
  },
    mounted() {
      this.fetchStats()
      this.fetchVideos()
    },
  methods: {
    async fetchStats() {
      const r = await fetch('/api/stats')
      this.stats = await r.json()
    },
    async fetchVideos() {
      const p = this.statusFilter ? `&status=${this.statusFilter}` : ''
      const r = await fetch(`/api/videos?page=${this.page}&page_size=${this.pageSize}${p}`)
      const d = await r.json()
      this.videos = d.items
      this.total = d.total
    },
    async triggerScrape() {
      this.scraping = true
      this.scrapeMsg = ''
      try {
        const r = await fetch('/api/scrape/trigger', { method: 'POST' })
        const d = await r.json()
        this.scrapeMsg = d.ok ? `抓取完成，新增 ${d.new} 条` : `失败: ${d.error}`
        if (d.ok) { this.fetchStats(); this.fetchVideos() }
      } catch(e) {
        this.scrapeMsg = '请求失败'
      }
      this.scraping = false
    },
    async triggerProcess() {
      this.processing = true
      this.processMsg = '处理任务已启动...'
      try {
        const r = await fetch('/api/process/pending', { method: 'POST' })
        const d = await r.json()
        this.processMsg = d.msg
        this.fetchStats()
        this.fetchVideos()
      } catch(e) {
        this.processMsg = '请求失败'
      }
      this.processing = false
    },
    goDetail(id) { this.$router.push(`/video/${id}`) },
    async processOne(id) {
      await fetch(`/api/videos/${id}/process`, { method: 'POST' })
      this.fetchStats()
      this.fetchVideos()
    },
    formatTime(t) { return t ? new Date(t).toLocaleString('zh-CN') : '-' },
    fmtDuration(s) { const m = Math.floor(s / 60); const sec = Math.floor(s % 60); return `${m}:${String(sec).padStart(2,'0')}` },
    statusClass(s) { return 's-' + (s || 'pending') },
    statusLabel(s) {
      const map = { pending: '待处理', processing: '处理中', screenshotted: '已截图', done: '已完成', failed: '失败' }
      return map[s] || s
    },
  }
}
</script>

<style scoped>
.stats-row { display: flex; gap: 16px; margin-bottom: 20px; }
.stat-card { background: #fff; border-radius: 8px; padding: 20px; flex: 1; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.stat-num { font-size: 28px; font-weight: 700; color: #1a1a2e; }
.stat-label { font-size: 13px; color: #888; margin-top: 4px; }
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.btn-primary { background: #1a1a2e; color: #fff; border: none; padding: 8px 20px; border-radius: 6px; cursor: pointer; font-size: 14px; }
.btn-primary:disabled { opacity: .5; cursor: default; }
.last-scrape { font-size: 13px; color: #888; }
.msg { font-size: 13px; color: #2b8a3e; }
.filter-bar { display: flex; gap: 8px; margin-bottom: 16px; }
.filter-bar button { background: #fff; border: 1px solid #ddd; padding: 6px 14px; border-radius: 16px; cursor: pointer; font-size: 13px; }
.filter-bar button.active { background: #1a1a2e; color: #fff; border-color: #1a1a2e; }
.video-list { background: #fff; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,.08); overflow: hidden; }
.video-row { padding: 14px 16px; border-bottom: 1px solid #f0f0f0; cursor: pointer; display: flex; gap: 12px; align-items: flex-start; }
.video-row:hover { background: #fafafa; }
.vid-status { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #888; min-width: 60px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.s-pending { background: #ccc; }
.s-processing, .s-screenshotted { background: #3b82f6; }
.s-done { background: #22c55e; }
.s-failed { background: #ef4444; }
.vid-info { flex: 1; min-width: 0; }
.vid-title { font-size: 15px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vid-meta { font-size: 12px; color: #999; margin-top: 4px; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 16px; }
.pagination button { background: #fff; border: 1px solid #ddd; padding: 6px 14px; border-radius: 6px; cursor: pointer; }
.pagination button:disabled { opacity: .4; }
.vid-actions { display: flex; align-items: center; }
.btn-tiny { background: #1a1a2e; color: #fff; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.btn-tiny:disabled { opacity: .4; }
</style>
