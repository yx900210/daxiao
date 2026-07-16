<template>
  <div class="settings-page">
    <h2>系统设置</h2>

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
      resetting: false,
      resetMsg: '',
    }
  },
  methods: {
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
.btn-save { margin-top: 8px; background: #1a1a2e; color: #fff; border: none; padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-save:disabled { opacity: .5; }
.btn-reset { background: #ef4444; }
.reset-group { border: 1px solid #fecaca; }
.msg { margin-left: 10px; font-size: 12px; color: #22c55e; }
.back { display: inline-block; margin-top: 12px; color: #666; text-decoration: none; font-size: 14px; }
</style>
