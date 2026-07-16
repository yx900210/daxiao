<template>
  <div class="detail" v-if="video">
    <button class="back-btn" @click="$router.push('/')">← 返回</button>

    <div class="video-header">
      <h2>{{ video.title || '无标题' }}</h2>
      <div class="meta-row">
        <span v-if="video.publish_time">{{ formatTime(video.publish_time) }}</span>
        <span>时长 {{ fmtDuration(video.duration) }}</span>
        <span>❤️ {{ video.like_count }}</span>
        <span>💬 {{ video.comment_count }}</span>
        <span>↗️ {{ video.share_count }}</span>
      </div>
      <span class="status-badge" :class="'s-' + video.fetch_status">{{ statusLabel(video.fetch_status) }}</span>
    </div>

    <section class="section" v-if="video.result && video.result.stock_summary">
      <h3>📈 股市观点</h3>
      <p class="summary">{{ video.result.stock_summary }}</p>
      <div class="tags" v-if="parsedKeywords.length">
        <span class="tag" v-for="k in parsedKeywords" :key="k">{{ k }}</span>
      </div>
      <div class="sentiment" v-if="video.result.stock_sentiment">
        情绪: <strong>{{ video.result.stock_sentiment }}</strong>
      </div>
    </section>

    <section class="section" v-if="video.bonsai">
      <h3>🪴 盆景解读</h3>
      <div v-if="video.bonsai.screenshot_path">
        <img :src="'/screenshots/' + getRelativePath(video.bonsai.screenshot_path)" style="max-width:300px;border-radius:8px;" />
      </div>
      <p v-if="video.bonsai.record_time">录制时间: {{ video.bonsai.record_time }}</p>
      <p v-if="video.bonsai.species">品种: {{ video.bonsai.species }}</p>
      <p v-if="video.bonsai.description">{{ video.bonsai.description }}</p>
      <p v-if="video.bonsai.meaning" class="meaning">寓意: {{ video.bonsai.meaning }}</p>
    </section>

    <section class="section" v-if="video.result && video.result.full_subtitle">
      <h3>📝 完整字幕
        <button class="btn-ai" @click="organize" :disabled="organizing">
          {{ organizing ? '整理中...' : '🤖 AI 整理' }}
        </button>
      </h3>
      <pre class="subtitle-text">{{ video.result.full_subtitle }}</pre>
      <p class="msg" v-if="organizeMsg">{{ organizeMsg }}</p>
    </section>

    <section class="section" v-if="video.subtitles && video.subtitles.length">
      <h3>🔤 OCR 逐帧结果</h3>
      <div class="ocr-list">
        <div class="ocr-item" v-for="s in video.subtitles" :key="s.frame_index">
          <span class="ocr-ts">{{ s.timestamp?.toFixed(1) }}s</span>
          <span class="ocr-text">{{ s.text || '(未识别)' }}</span>
        </div>
      </div>
    </section>

    <section class="section meta-section">
      <h3>📋 元信息</h3>
      <p>抖音视频ID: {{ video.douyin_video_id }}</p>
      <p>处理状态: {{ statusLabel(video.fetch_status) }}</p>
      <p v-if="video.result && video.result.processed_at">处理时间: {{ formatTime(video.result.processed_at) }}</p>
      <p v-if="video.error_msg" class="error">错误: {{ video.error_msg }}</p>
    </section>
  </div>
  <div v-else class="loading">加载中...</div>
</template>

<script>
export default {
  data() {
    return { video: null, organizing: false, organizeMsg: '' }
  },
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
      this.organizing = true
      this.organizeMsg = ''
      try {
        const r = await fetch(`/api/videos/${this.$route.params.id}/organize`, { method: 'POST' })
        if (!r.ok) { const d = await r.json(); throw new Error(d.detail || '失败') }
        const d = await r.json()
        this.video.result.full_subtitle = d.text
        this.organizeMsg = '整理完成'
      } catch(e) {
        this.organizeMsg = e.message
      }
      this.organizing = false
    },
    formatTime(t) { return t ? new Date(t).toLocaleString('zh-CN') : '-' },
    fmtDuration(s) { const m = Math.floor(s / 60); const sec = Math.floor(s % 60); return `${m}:${String(sec).padStart(2,'0')}` },
    statusLabel(s) {
      const map = { pending:'待处理',processing:'处理中',screenshotted:'已截图',done:'已完成',failed:'失败' }
      return map[s] || s
    },
    getRelativePath(abs) {
      return abs.replace(/.*screenshots\//, '')
    },
  }
}
</script>

<style scoped>
.back-btn { background: none; border: none; color: #666; cursor: pointer; font-size: 14px; margin-bottom: 16px; display: block; }
.video-header { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.video-header h2 { font-size: 18px; margin-bottom: 8px; }
.meta-row { display: flex; gap: 16px; font-size: 13px; color: #888; }
.status-badge { display: inline-block; margin-top: 8px; padding: 2px 10px; border-radius: 10px; font-size: 12px; color: #fff; }
.s-pending { background: #999; }
.s-processing, .s-screenshotted { background: #3b82f6; }
.s-done { background: #22c55e; }
.s-failed { background: #ef4444; }
.section { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.section h3 { font-size: 16px; margin-bottom: 12px; }
.summary { line-height: 1.7; white-space: pre-wrap; }
.tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.tag { background: #e8f0fe; color: #1a73e8; padding: 2px 10px; border-radius: 10px; font-size: 12px; }
.sentiment { margin-top: 8px; font-size: 14px; }
.meaning { margin-top: 8px; font-style: italic; color: #555; }
.subtitle-text { white-space: pre-wrap; font-size: 13px; line-height: 1.8; background: #f9f9f9; padding: 12px; border-radius: 6px; }
.ocr-list { max-height: 400px; overflow-y: auto; }
.ocr-item { padding: 6px 0; border-bottom: 1px solid #f5f5f5; font-size: 13px; }
.ocr-ts { color: #999; margin-right: 10px; font-family: monospace; }
.meta-section p { font-size: 13px; margin-bottom: 4px; color: #666; }
.error { color: #ef4444; }
.loading { text-align: center; padding: 40px; color: #888; }
.btn-ai { background: linear-gradient(135deg, #667eea, #764ba2); color: #fff; border: none; padding: 4px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; float: right; }
.btn-ai:disabled { opacity: .5; }
.msg { font-size: 12px; color: #22c55e; margin-top: 6px; }
</style>
