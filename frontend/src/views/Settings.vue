<template>
  <div class="settings-page">
    <h2>系统设置</h2>

    <div class="setting-group">
      <label>AI 段落整理 — 提示词</label>
      <p class="desc">占位符: <code>{subtitle}</code> 会被替换为原始字幕</p>
      <textarea v-model="promptOrganize" rows="8"></textarea>
      <button class="btn-save" @click="savePrompt('prompt_organize', promptOrganize)" :disabled="savingOrg">保存</button>
      <span class="msg" v-if="orgMsg">{{ orgMsg }}</span>
    </div>

    <div class="setting-group">
      <label>AI 观点提炼 — 提示词</label>
      <p class="desc">占位符: <code>{text}</code> 会被替换为整理后的文稿</p>
      <textarea v-model="promptViewpoint" rows="8"></textarea>
      <button class="btn-save" @click="savePrompt('prompt_viewpoint', promptViewpoint)" :disabled="savingVp">保存</button>
      <span class="msg" v-if="vpMsg">{{ vpMsg }}</span>
    </div>

    <div class="setting-group">
      <label>盆景元素识别 — 提示词</label>
      <textarea v-model="promptBonsaiElements" rows="5"></textarea>
      <button class="btn-save" @click="savePrompt('prompt_bonsai_elements', promptBonsaiElements)" :disabled="savingBe">保存</button>
      <span class="msg" v-if="beMsg">{{ beMsg }}</span>
    </div>

    <div class="setting-group">
      <label>盆景寓意解读 — 提示词</label>
      <p class="desc">占位符: <code>{elements}</code> 会被替换为 Stage 1 识别出的元素列表</p>
      <textarea v-model="promptBonsaiMeaning" rows="5"></textarea>
      <button class="btn-save" @click="savePrompt('prompt_bonsai_meaning', promptBonsaiMeaning)" :disabled="savingBm">保存</button>
      <span class="msg" v-if="bmMsg">{{ bmMsg }}</span>
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
      promptOrganize: '',
      promptViewpoint: '',
      promptBonsaiElements: '',
      promptBonsaiMeaning: '',
      savingOrg: false, orgMsg: '',
      savingVp: false, vpMsg: '',
      savingBe: false, beMsg: '',
      savingBm: false, bmMsg: '',
      resetting: false, resetMsg: '',
    }
  },
  async mounted() {
    const r = await fetch('/api/settings')
    const data = await r.json()
    this.promptOrganize = data.prompt_organize || ''
    this.promptViewpoint = data.prompt_viewpoint || ''
    this.promptBonsaiElements = data.prompt_bonsai_elements || ''
    this.promptBonsaiMeaning = data.prompt_bonsai_meaning || ''
  },
  methods: {
    async savePrompt(key, value) {
      if (key === 'prompt_organize') { this.savingOrg = true; this.orgMsg = '' }
      else if (key === 'prompt_viewpoint') { this.savingVp = true; this.vpMsg = '' }
      else if (key === 'prompt_bonsai_elements') { this.savingBe = true; this.beMsg = '' }
      else { this.savingBm = true; this.bmMsg = '' }
      await fetch(`/api/settings/${key}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ value }),
      })
      if (key === 'prompt_organize') { this.orgMsg = '已保存'; this.savingOrg = false }
      else if (key === 'prompt_viewpoint') { this.vpMsg = '已保存'; this.savingVp = false }
      else if (key === 'prompt_bonsai_elements') { this.beMsg = '已保存'; this.savingBe = false }
      else { this.bmMsg = '已保存'; this.savingBm = false }
    },
    async resetAll() {
      if (!confirm('确定要清空所有数据吗？此操作不可撤销！')) return
      this.resetting = true
      try {
        const r = await fetch('/api/reset', { method: 'POST' })
        const d = await r.json()
        this.resetMsg = d.msg
      } catch(e) { this.resetMsg = '请求失败' }
      this.resetting = false
      setTimeout(() => { this.resetMsg = '' }, 3000)
    },
  },
}
</script>

<style scoped>
.settings-page { max-width: 700px; }
h2 { font-size: 20px; margin-bottom: 24px; }
.setting-group { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
label { display: block; font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.desc { font-size: 12px; color: #888; margin-bottom: 8px; }
code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 11px; }
textarea { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; font-size: 12px; font-family: 'SF Mono', 'Menlo', monospace; resize: vertical; line-height: 1.5; }
.btn-save { margin-top: 8px; background: #1a1a2e; color: #fff; border: none; padding: 6px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-save:disabled { opacity: .5; }
.btn-reset { background: #ef4444; }
.reset-group { border: 1px solid #fecaca; }
.msg { margin-left: 10px; font-size: 12px; color: #22c55e; }
.back { display: inline-block; margin-top: 12px; color: #666; text-decoration: none; font-size: 14px; }
</style>
