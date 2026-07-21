<template>
  <div class="dashboard">
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-icon">📊</div>
        <div class="stat-body">
          <div class="stat-num">{{ stats.total_videos }}</div>
          <div class="stat-label">总视频</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">✅</div>
        <div class="stat-body">
          <div class="stat-num">{{ stats.processed }}</div>
          <div class="stat-label">已完成</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon">⏳</div>
        <div class="stat-body">
          <div class="stat-num">{{ stats.pending }}</div>
          <div class="stat-label">待处理</div>
        </div>
      </div>
    </div>

    <div class="toolbar">
      <button class="btn" @click="triggerScrape" :disabled="scraping">
        {{ scraping ? '抓取中...' : '🔄 立即抓取' }}
      </button>
      <button class="btn btn-accent" @click="triggerProcess" :disabled="processing">
        {{ processing ? '处理中...' : '⚡ 一键处理全部' }}
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

    <div class="card-list" v-if="videos.length">
      <div class="video-card" v-for="v in videos" :key="v.id">
        <div class="card-cover" @click.stop="playVideo(v)">
          <img v-if="v.cover_url" :src="v.cover_url" class="cover-img" />
          <div class="cover-placeholder" v-else>🎬</div>
          <div class="play-overlay">▶</div>
          <span class="duration-badge">{{ fmtDuration(v.duration) }}</span>
          <span class="status-pill" :class="'s-' + v.fetch_status">{{ statusLabel(v.fetch_status) }}</span>
        </div>
        <div class="card-body" @click="goDetail(v.id)">
          <h3 class="card-title">{{ v.title || '无标题' }}</h3>
          <div class="card-meta">
            <span v-if="v.publish_time">{{ formatTime(v.publish_time) }}</span>
            <span class="dot" v-if="v.publish_time">·</span>
            <span>❤️ {{ fmtCount(v.like_count) }}</span>
          </div>
          <p class="card-viewpoint" v-if="v.stock_summary">
            <span class="sect-tag tg-viewpoint">观点</span>{{ viewpointPreview(v.stock_summary) }}
          </p>
          <p class="card-preview" v-if="v.subtitle_preview" :class="{ expanded: isExpanded(v.id) }">
            <span class="sect-tag tg-subtitle">字幕</span>{{ isExpanded(v.id) ? (v.subtitle_preview_full || v.subtitle_preview) : v.subtitle_preview }}<span class="expand-link" @click.stop="toggleExpand(v)" v-if="hasMore(v)">{{ isExpanded(v.id) ? '收起▲' : '...展开▼' }}</span>
          </p>
          <div class="card-bonsai-text" v-if="v.bonsai_species || v.bonsai_meaning">
            <p class="bonsai-elements" v-if="v.bonsai_species">
              <span class="sect-tag tg-bonsai">盆景</span>{{ v.bonsai_species }}
            </p>
            <p class="bonsai-meaning" v-if="v.bonsai_meaning">
              <span class="sect-tag tg-meaning">寓意</span>{{ v.bonsai_meaning.substring(0, 80) }}{{ v.bonsai_meaning.length > 80 ? '...' : '' }}
            </p>
          </div>
          <div class="card-tags" v-if="parsedKeywords(v).length">
            <span class="tag" v-for="k in parsedKeywords(v).slice(0,4)" :key="k">{{ k }}</span>
          </div>
        </div>
        <div class="card-actions" @click.stop>
          <button class="act-btn" @click="processOne(v.id)" :disabled="v.fetch_status === 'processing'" title="处理">▶</button>
        </div>

        <div class="card-bonsai" v-if="v.bonsai_image" @click.stop="previewBonsai(v)">
          <div class="bonsai-thumb">
            <img :src="'screenshots/' + bgRel(v.bonsai_image)" />
          </div>
        </div>
      </div>
    </div>

    <div class="video-modal" v-if="playingVideo" @click="closePlayer">
      <div class="modal-content" @click.stop>
        <span class="modal-close" @click="closePlayer">✕</span>
        <video :src="playingVideo" controls autoplay class="modal-video"></video>
      </div>
    </div>

    <div class="img-modal" v-if="previewImg" @click="previewImg = ''">
      <img :src="previewImg" @click.stop />
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
      videos: [], total: 0, page: 1, pageSize: 10,
      statusFilter: '',
      statusFilters: [
        { label: '全部', value: '' }, { label: '待处理', value: 'pending' },
        { label: '已截图', value: 'screenshotted' }, { label: '已完成', value: 'done' },
        { label: '失败', value: 'failed' },
      ],
      scraping: false, scrapeMsg: '', processing: false, processMsg: '',
      expandedIds: new Set(),
      playingVideo: '',
      previewImg: '',
    }
  },
  watch: {
    statusFilter() { this.page = 1; this.fetchVideos() },
    page() { this.fetchVideos() },
  },
  mounted() { this.fetchStats(); this.fetchVideos() },
  methods: {
    async fetchStats() {
      const r = await fetch('/api/stats')
      this.stats = await r.json()
    },
    async fetchVideos() {
      const p = this.statusFilter ? `&status=${this.statusFilter}` : ''
      const r = await fetch(`/api/videos?page=${this.page}&page_size=${this.pageSize}${p}`)
      const d = await r.json()
      this.videos = d.items; this.total = d.total
    },
    async triggerScrape() {
      this.scraping = true; this.scrapeMsg = ''
      try {
        const r = await fetch('/api/scrape/trigger', { method: 'POST' })
        const d = await r.json()
        this.scrapeMsg = d.ok ? `新增 ${d.new} 条` : `失败: ${d.error}`
        if (d.ok) { this.fetchStats(); this.fetchVideos() }
      } catch(e) { this.scrapeMsg = '请求失败' }
      this.scraping = false
    },
    async triggerProcess() {
      this.processing = true
      await fetch('/api/process/pending', { method: 'POST' })
      this.fetchStats(); this.fetchVideos()
      this.processing = false
    },
    async processOne(id) {
      await fetch(`/api/videos/${id}/process`, { method: 'POST' })
      this.fetchStats(); this.fetchVideos()
    },
    goDetail(id) { this.$router.push(`/video/${id}`) },
    hasMore(v) { return (v.subtitle_preview_full || v.subtitle_preview || '').length > 80 },
    isExpanded(id) { return this.expandedIds.has(id) },
    toggleExpand(v) {
      if (this.expandedIds.has(v.id)) this.expandedIds.delete(v.id)
      else this.expandedIds.add(v.id)
      this.expandedIds = new Set(this.expandedIds)
    },
    viewpointPreview(s) {
      if (!s) return ''
      const lines = s.split('\n').filter(l => l.trim())
      return lines.slice(0, 3).join(' · ')
    },
    playVideo(v) {
      if (v.douyin_video_id) {
        this.playingVideo = `/videos/${v.douyin_video_id}.mp4`
      }
    },
    closePlayer() { this.playingVideo = '' },
    previewBonsai(v) { if (v.bonsai_image) this.previewImg = 'screenshots/' + this.bgRel(v.bonsai_image) },
    bgRel(abs) { return abs ? abs.replace(/.*screenshots\//, '') : '' },
    firstLine(s) { if (!s) return ''; const idx = s.indexOf('\n'); return idx > 0 ? s.substring(0, idx) : s.substring(0, 80) },
    formatTime(t) { return t ? new Date(t).toLocaleString('zh-CN') : '-' },
    fmtDuration(s) { const m = Math.floor(s / 60); return `${m}:${String(Math.floor(s % 60)).padStart(2,'0')}` },
    fmtCount(n) { return n >= 10000 ? (n / 10000).toFixed(1) + '万' : n },
    parsedKeywords(v) { try { return JSON.parse(v.stock_keywords || '[]') } catch { return [] } },
    statusLabel(s) {
      const map = { pending:'待处理', processing:'处理中', screenshotted:'已截图', done:'已完成', failed:'失败' }
      return map[s] || s
    },
  }
}
</script>

<style scoped>
.stats-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 24px; }
.stat-card { background: #fff; border-radius: 12px; padding: 20px; display: flex; align-items: center; gap: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.stat-icon { font-size: 28px; }
.stat-num { font-size: 26px; font-weight: 700; color: #1a1a2e; }
.stat-label { font-size: 13px; color: #888; margin-top: 2px; }
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.btn { background: #1a1a2e; color: #fff; border: none; padding: 8px 18px; border-radius: 8px; cursor: pointer; font-size: 13px; font-weight: 500; transition: all .15s; }
.btn:hover { opacity: .85; transform: translateY(-1px); }
.btn:disabled { opacity: .45; transform: none; }
.btn-accent { background: linear-gradient(135deg, #667eea, #764ba2); }
.last-scrape { font-size: 12px; color: #999; }
.msg { font-size: 12px; color: #22c55e; }
.filter-bar { display: flex; gap: 6px; margin-bottom: 20px; }
.filter-bar button { background: #fff; border: 1px solid #e0e0e0; padding: 6px 14px; border-radius: 20px; cursor: pointer; font-size: 12px; color: #666; transition: all .15s; }
.filter-bar button.active { background: #1a1a2e; color: #fff; border-color: #1a1a2e; }
.card-list { display: flex; flex-direction: column; gap: 16px; }
.video-card { background: #fff; border-radius: 12px; box-shadow: 0 1px 4px rgba(0,0,0,.06); cursor: pointer; transition: all .2s; display: flex; flex-wrap: wrap; overflow: hidden; }
.video-card:hover { transform: translateY(-2px); box-shadow: 0 4px 20px rgba(0,0,0,.1); }
.card-cover { width: 280px; flex-shrink: 0; position: relative; background: #1a1a2e; min-height: 210px; cursor: pointer; }
.cover-img { width: 100%; height: 100%; object-fit: contain; position: absolute; top: 0; left: 0; background: #000; }
.play-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 40px; color: rgba(255,255,255,.8); opacity: 0; transition: opacity .2s; background: rgba(0,0,0,.3); }
.card-cover:hover .play-overlay { opacity: 1; }
.cover-placeholder { display: flex; align-items: center; justify-content: center; height: 100%; font-size: 48px; }
.duration-badge { position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,.7); color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.status-pill { position: absolute; top: 8px; left: 8px; padding: 2px 8px; border-radius: 10px; font-size: 10px; color: #fff; }
.s-pending { background: #999; } .s-processing { background: #3b82f6; }
.s-screenshotted { background: #f59e0b; } .s-done { background: #22c55e; } .s-failed { background: #ef4444; }
.card-body { flex: 1; padding: 16px 20px; min-width: 0; }
.card-title { font-size: 15px; font-weight: 600; line-height: 1.4; margin-bottom: 6px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-meta { font-size: 12px; color: #999; margin-bottom: 8px; }
.dot { margin: 0 6px; }
.card-viewpoint { font-size: 13px; color: #4f46e5; font-weight: 500; margin-bottom: 6px; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-preview { font-size: 12px; color: #777; line-height: 1.6; margin-bottom: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.card-preview.expanded { display: block; -webkit-line-clamp: unset; }
.expand-link { color: #4f46e5; cursor: pointer; font-size: 11px; margin-left: 2px; }
.expand-link:hover { text-decoration: underline; }
.sect-tag { display: inline-block; padding: 0 5px; border-radius: 3px; font-size: 10px; font-weight: 600; margin-right: 5px; vertical-align: 1px; letter-spacing: 0.5px; }
.tg-viewpoint { background: #eef2ff; color: #4f46e5; }
.tg-subtitle  { background: #f3f4f6; color: #6b7280; }
.tg-bonsai    { background: #ecfdf5; color: #059669; }
.tg-meaning   { background: #fffbeb; color: #d97706; }
.video-modal { position: fixed; inset: 0; background: rgba(0,0,0,.85); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.modal-content { position: relative; width: 90%; max-width: 900px; }
.modal-close { position: absolute; top: -40px; right: 0; color: #fff; font-size: 28px; cursor: pointer; }
.modal-video { width: 100%; border-radius: 8px; max-height: 80vh; }
.card-tags { display: flex; gap: 4px; flex-wrap: wrap; }
.tag { background: #eef2ff; color: #4f46e5; padding: 1px 8px; border-radius: 10px; font-size: 10px; }
.card-actions { display: flex; align-items: flex-start; padding: 16px 12px 0 0; flex-shrink: 0; }
.act-btn { background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; border: none; width: 34px; height: 34px; border-radius: 50%; cursor: pointer; font-size: 15px; transition: all .15s; display: flex; align-items: center; justify-content: center; }
.act-btn:hover { transform: scale(1.1); }
.act-btn:disabled { opacity: .4; transform: none; }
.card-bonsai { width: 240px; flex-shrink: 0; display: flex; align-items: stretch; padding: 12px; cursor: pointer; transition: background .15s; border-left: 1px solid #eee; }
.card-bonsai:hover { background: #f8f9fc; }
.bonsai-thumb { flex: 1; border-radius: 8px; overflow: hidden; display: flex; align-items: center; justify-content: center; }
.bonsai-thumb img { width: 100%; height: 100%; object-fit: contain; }
.card-bonsai-text { margin-top: 8px; padding-top: 8px; border-top: 1px solid #f0f0f0; }
.card-bonsai-text .bonsai-elements { font-size: 12px; color: #333; line-height: 1.6; margin-bottom: 3px; }
.card-bonsai-text .bonsai-meaning { font-size: 11px; color: #888; line-height: 1.5; margin: 0; }
.img-modal { position: fixed; inset: 0; background: rgba(0,0,0,.9); z-index: 1001; display: flex; align-items: center; justify-content: center; cursor: pointer; }
.img-modal img { max-width: 90vw; max-height: 90vh; object-fit: contain; border-radius: 8px; }
.pagination { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 24px; }
.pagination button { background: #fff; border: 1px solid #ddd; padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 13px; }
.pagination button:disabled { opacity: .4; }
@media (max-width: 768px) {
  .main-content { padding: 12px; }
  .stats-row { grid-template-columns: 1fr; }
  .video-card { flex-direction: column; }
  .card-cover { width: 100%; height: 200px; min-height: 180px; }
  .card-bonsai { width: 100%; border-left: none; border-top: 1px solid #eee; }
  .card-bonsai .bonsai-thumb { height: 200px; flex: none; }
  .card-actions { position: absolute; top: 140px; right: 12px; padding: 0; }
}
</style>
