<template>
  <div class="settings-page">
    <h2>系统设置</h2>

    <div class="setting-group">
      <label>Douyin Cookie</label>
      <textarea v-model="cookie" rows="4" placeholder="粘贴从浏览器复制的完整 Cookie 字符串"></textarea>
      <button class="btn-save" @click="saveCookie" :disabled="savingCookie">保存</button>
      <span class="msg" v-if="cookieMsg">{{ cookieMsg }}</span>
    </div>

    <div class="setting-group">
      <label>HTTP 代理</label>
      <input v-model="proxy" type="text" placeholder="http://nas.900210.top:53128" />
      <button class="btn-save" @click="saveProxy" :disabled="savingProxy">保存</button>
      <span class="msg" v-if="proxyMsg">{{ proxyMsg }}</span>
    </div>

    <div class="setting-group reset-group">
      <label style="color:#ef4444">清空所有数据</label>
      <p style="font-size:13px;color:#888;margin-bottom:8px">删除所有视频、截图、抓取日志。此操作不可撤销。</p>
      <button class="btn-save btn-reset" @click="resetAll" :disabled="resetting">
        {{ resetting ? '清空中...' : '确认清空' }}
      </button>
      <span class="msg" v-if="resetMsg">{{ resetMsg }}</span>
    </div>

    <router-link to="/" class="back">← 返回首页</router-link>
  </div>
</template>

<script>
export default {
  data() {
    return {
      cookie: '',
      proxy: '',
      savingCookie: false,
      savingProxy: false,
      cookieMsg: '',
      proxyMsg: '',
      resetting: false,
      resetMsg: '',
    }
  },
  async mounted() {
    const r = await fetch('/api/settings')
    const data = await r.json()
    this.cookie = data.douyin_cookie || ''
    this.proxy = data.http_proxy || ''
  },
  methods: {
    async saveCookie() {
      this.savingCookie = true
      await fetch('/api/settings/douyin_cookie', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: this.cookie }),
      })
      this.cookieMsg = '已保存'
      this.savingCookie = false
    },
    async saveProxy() {
      this.savingProxy = true
      await fetch('/api/settings/http_proxy', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value: this.proxy }),
      })
      this.proxyMsg = '已保存'
      this.savingProxy = false
    },
    async resetAll() {
      if (!confirm('确定要清空所有数据吗？此操作不可撤销！')) return
      this.resetting = true
      try {
        const r = await fetch('/api/reset', { method: 'POST' })
        const d = await r.json()
        this.resetMsg = d.msg
      } catch(e) {
        this.resetMsg = '请求失败'
      }
      this.resetting = false
      setTimeout(() => { this.resetMsg = '' }, 3000)
    },
  },
}
</script>

<style scoped>
.settings-page { max-width: 600px; }
h2 { font-size: 20px; margin-bottom: 24px; }
.setting-group { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
label { display: block; font-size: 14px; font-weight: 600; margin-bottom: 8px; }
textarea, input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 13px; font-family: monospace; resize: vertical; }
input { font-family: inherit; }
.btn-save { margin-top: 8px; background: #1a1a2e; color: #fff; border: none; padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-save:disabled { opacity: .5; }
.msg { margin-left: 10px; font-size: 12px; color: #22c55e; }
.btn-reset { background: #ef4444; }
.reset-group { border: 1px solid #fecaca; }
.back { display: inline-block; margin-top: 12px; color: #666; text-decoration: none; font-size: 14px; }
</style>
