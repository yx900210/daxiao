<template>
  <div class="detail" v-if="video">
    <button class="back-btn" @click="$router.push('/')">← 返回</button>

    <div class="video-header">
      <div class="header-left">
        <img v-if="video.cover_url" :src="video.cover_url" class="cover-thumb" />
        <div class="cover-placeholder" v-else>🎬</div>
      </div>
      <div class="header-info">
        <h2>{{ video.title || '无标题' }}</h2>
        <div class="meta-row">
          <span v-if="video.publish_time">{{ formatTime(video.publish_time) }}</span>
          <span>时长 {{ fmtDuration(video.duration) }}</span>
          <span>❤️ {{ video.like_count }}</span>
          <span>💬 {{ video.comment_count }}</span>
        </div>
        <span class="status-pill" :class="'s-' + video.fetch_status">{{ statusLabel(video.fetch_status) }}</span>
      </div>
    </div>

    <section class="section" v-if="video.result && (video.result.organized_subtitle || video.result.full_subtitle)">
      <div class="section-head">
        <span>📝 字幕文稿</span>
        <div class="section-actions">
          <button class="btn-sm" @click="organize" :disabled="organizing">
            {{ organizing ? '整理中...' : '🤖 AI 整理' }}
          </button>
        </div>
      </div>
      <pre class="subtitle-text" v-if="video.result.organized_subtitle">{{ video.result.organized_subtitle }}</pre>
      <pre class="subtitle-text subtitle-raw" v-else>{{ video.result.full_subtitle }}</pre>
      <p class="msg" v-if="organizeMsg">{{ organizeMsg }}</p>
    </section>

    <section class="section" v-if="video.result && (video.result.organized_subtitle || video.result.full_subtitle)">
      <div class="section-head">
        <span>📈 股市观点</span>
        <div class="section-actions">
          <button class="btn-sm" @click="extractViewpoints" :disabled="viewpointing">
            {{ viewpointing ? '提炼中...' : '🤖 提炼观点' }}
          </button>
        </div>
      </div>
      <div v-if="video.result.stock_summary">
        <p class="summary">{{ video.result.stock_summary }}</p>
        <div class="tags" v-if="parsedKeywords.length">
          <span class="tag" v-for="k in parsedKeywords" :key="k">{{ k }}</span>
        </div>
        <div class="sentiment" v-if="video.result.stock_sentiment">
          情绪: <strong>{{ video.result.stock_sentiment }}</strong>
        </div>
      </div>
      <p v-else class="hint">点击上方按钮提取核心观点</p>
    </section>

    <section class="section" v-if="video.bonsai">
      <div class="section-head"><span>🪴 盆景解读</span></div>
      <div v-if="video.bonsai.screenshot_path">
        <img :src="'/screenshots/' + getRelativePath(video.bonsai.screenshot_path)" class="bonsai-img" />
      </div>
      <p v-if="video.bonsai.record_time">录制时间: {{ video.bonsai.record_time }}</p>
      <p v-if="video.bonsai.species">品种: {{ video.bonsai.species }}</p>
      <p v-if="video.bonsai.description">{{ video.bonsai.description }}</p>
      <p v-if="video.bonsai.meaning" class="meaning">寓意: {{ video.bonsai.meaning }}</p>
    </section>

    <section class="section" v-if="video.subtitles && video.subtitles.length">
      <div class="section-head"><span>🔤 OCR 逐帧结果 ({{ video.subtitles.filter(s => s.text).length }}/{{ video.subtitles.length }})</span></div>
      <div class="ocr-list">
        <div class="ocr-item" v-for="s in video.subtitles.filter(x => x.text)" :key="s.frame_index">
          <span class="ocr-ts">{{ s.timestamp?.toFixed(1) }}s</span>
          <span class="ocr-text">{{ s.text }}</span>
        </div>
      </div>
    </section>

    <section class="section meta-section">
      <div class="section-head"><span>📋 元信息</span></div>
      <p>抖音视频ID: {{ video.douyin_video_id }}</p>
      <p v-if="video.result && video.result.processed_at">处理时间: {{ formatTime(video.result.processed_at) }}</p>
      <p v-if="video.error_msg" class="error">错误: {{ video.error_msg }}</p>
    </section>
  </div>
  <div v-else class="loading">加载中...</div>
</template>

<script>
export default {
  data() { return { video: null, organizing: false, organizeMsg: '', viewpointing: false, viewpointMsg: '' } },
  computed: {
    parsedKeywords() {
      if (!this.video?.result?.stock_keywords) return []
      try { return JSON.parse(this.video.result.stock_keywords) } catch { return [] }
    }
  },
  mounted() { this.fetchDetail() },
  methods: {
    async fetchDetail() {
      const r = await fetch(`/api/videos/${this.$route.params.id}`)
      this.video = await r.json()
    },
    async organize() {
      this.organizing = true; this.organizeMsg = ''
      try {
        const r = await fetch(`/api/videos/${this.$route.params.id}/organize`, { method: 'POST' })
        if (!r.ok) { const d = await r.json(); throw new Error(d.detail || '失败') }
        const d = await r.json()
        this.video.result.organized_subtitle = d.text
        this.organizeMsg = '整理完成'
      } catch(e) { this.organizeMsg = e.message }
      this.organizing = false
    },
    async extractViewpoints() {
      this.viewpointing = true; this.viewpointMsg = ''
      try {
        const r = await fetch(`/api/videos/${this.$route.params.id}/viewpoints`, { method: 'POST' })
        if (!r.ok) { const d = await r.json(); throw new Error(d.detail || '失败') }
        const d = await r.json()
        this.video.result.stock_summary = d.stock_summary
        this.video.result.stock_keywords = d.stock_keywords
        this.video.result.stock_sentiment = d.stock_sentiment
      } catch(e) { this.viewpointMsg = e.message }
      this.viewpointing = false
    },
    formatTime(t) { return t ? new Date(t).toLocaleString('zh-CN') : '-' },
    fmtDuration(s) { const m = Math.floor(s / 60); return `${m}:${String(Math.floor(s % 60)).padStart(2,'0')}` },
    statusLabel(s) { const map = { pending:'待处理',processing:'处理中',screenshotted:'已截图',done:'已完成',failed:'失败' }; return map[s] || s },
    getRelativePath(abs) { return abs.replace(/.*screenshots\//, '') },
  }
}
</script>

<style scoped>
.back-btn { background: none; border: none; color: #666; cursor: pointer; font-size: 14px; margin-bottom: 20px; display: block; padding: 0; }
.video-header { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.06); display: flex; gap: 16px; }
.cover-thumb { width: 120px; height: 68px; object-fit: cover; border-radius: 8px; flex-shrink: 0; }
.cover-placeholder { width: 120px; height: 68px; background: #e8eaed; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 24px; flex-shrink: 0; }
.header-info h2 { font-size: 18px; font-weight: 600; margin-bottom: 6px; }
.meta-row { display: flex; gap: 14px; font-size: 12px; color: #888; }
.status-pill { display: inline-block; margin-top: 8px; padding: 2px 10px; border-radius: 10px; font-size: 11px; color: #fff; }
.s-pending { background: #999; } .s-processing { background: #3b82f6; } .s-screenshotted { background: #f59e0b; } .s-done { background: #22c55e; } .s-failed { background: #ef4444; }
.section { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; font-size: 15px; font-weight: 600; }
.btn-sm { background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; border: none; padding: 5px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; transition: all .15s; }
.btn-sm:disabled { opacity: .5; }
.summary { line-height: 1.8; white-space: pre-wrap; font-size: 14px; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 10px; }
.tag { background: #eef2ff; color: #4f46e5; padding: 2px 10px; border-radius: 10px; font-size: 11px; }
.sentiment { margin-top: 8px; font-size: 13px; }
.meaning { margin-top: 8px; font-style: italic; color: #555; }
.subtitle-text { white-space: pre-wrap; font-size: 14px; line-height: 1.9; background: #f8f9fc; padding: 14px; border-radius: 8px; }
.subtitle-raw { color: #666; font-size: 13px; }
.ocr-list { max-height: 400px; overflow-y: auto; }
.ocr-item { padding: 5px 0; border-bottom: 1px solid #f5f5f5; font-size: 13px; display: flex; gap: 10px; }
.ocr-ts { color: #999; font-family: monospace; font-size: 11px; min-width: 50px; }
.hint { font-size: 13px; color: #999; }
.msg { font-size: 12px; color: #22c55e; margin-top: 6px; }
.meta-section p { font-size: 13px; margin-bottom: 4px; color: #666; }
.error { color: #ef4444; }
.bonsai-img { max-width: 300px; border-radius: 8px; margin-top: 8px; }
.loading { text-align: center; padding: 60px; color: #888; }
</style>
