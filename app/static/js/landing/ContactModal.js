/**
 * 联系方式弹窗：Telegram / 微信 / QQ + 复制
 */
export default {
  name: "ContactModal",
  props: {
    open: { type: Boolean, default: false },
    planId: { type: String, default: "" },
  },
  emits: ["update:open"],
  data() {
    return {
      copiedKey: "",
      contacts: {
        telegram: "@your_telegram",
        wechat: "your_wechat_id",
        qq: "1234567890",
      },
    };
  },
  computed: {
    planTitle() {
      const m = { basic: "Basic", pro: "Pro", premium: "Premium" };
      return m[this.planId] || "套餐";
    },
  },
  watch: {
    open(v) {
      if (v) this.copiedKey = "";
    },
  },
  methods: {
    close() {
      this.$emit("update:open", false);
    },
    async copy(key) {
      const text = this.contacts[key];
      try {
        await navigator.clipboard.writeText(text);
        this.copiedKey = key;
        setTimeout(() => {
          if (this.copiedKey === key) this.copiedKey = "";
        }, 1600);
      } catch {
        const ta = document.createElement("textarea");
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        this.copiedKey = key;
      }
    },
  },
  template: `
    <teleport to="body">
      <div
        v-if="open"
        class="fixed inset-0 z-[100] flex items-end justify-center sm:items-center p-4 bg-black/60 backdrop-blur-sm"
        @click.self="close"
      >
        <div
          class="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900 shadow-2xl"
          role="dialog"
          aria-modal="true"
        >
          <div class="flex items-start justify-between gap-3 border-b border-white/10 px-5 py-4">
            <div>
              <div class="text-lg font-bold text-white">联系客服开通</div>
              <div class="mt-1 text-sm text-slate-400">
                已选：<span class="text-indigo-300">{{ planTitle }}</span> · 人工审核后开通
              </div>
            </div>
            <button
              type="button"
              class="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-sm text-slate-300 hover:bg-white/10"
              @click="close"
            >
              关闭
            </button>
          </div>

          <div class="space-y-3 px-5 py-4">
            <div class="rounded-xl border border-white/10 bg-white/5 p-3">
              <div class="text-xs font-medium text-slate-400">Telegram</div>
              <div class="mt-1 flex items-center justify-between gap-2">
                <span class="truncate text-sm text-white font-mono">{{ contacts.telegram }}</span>
                <button
                  type="button"
                  class="shrink-0 rounded-lg bg-indigo-500/90 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
                  @click="copy('telegram')"
                >
                  {{ copiedKey === 'telegram' ? '已复制' : '复制' }}
                </button>
              </div>
            </div>
            <div class="rounded-xl border border-white/10 bg-white/5 p-3">
              <div class="text-xs font-medium text-slate-400">微信</div>
              <div class="mt-1 flex items-center justify-between gap-2">
                <span class="truncate text-sm text-white font-mono">{{ contacts.wechat }}</span>
                <button
                  type="button"
                  class="shrink-0 rounded-lg bg-indigo-500/90 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
                  @click="copy('wechat')"
                >
                  {{ copiedKey === 'wechat' ? '已复制' : '复制' }}
                </button>
              </div>
            </div>
            <div class="rounded-xl border border-white/10 bg-white/5 p-3">
              <div class="text-xs font-medium text-slate-400">QQ</div>
              <div class="mt-1 flex items-center justify-between gap-2">
                <span class="truncate text-sm text-white font-mono">{{ contacts.qq }}</span>
                <button
                  type="button"
                  class="shrink-0 rounded-lg bg-indigo-500/90 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
                  @click="copy('qq')"
                >
                  {{ copiedKey === 'qq' ? '已复制' : '复制' }}
                </button>
              </div>
            </div>
          </div>

          <div class="border-t border-white/10 px-5 py-3 text-xs text-slate-500">
            请备注所选套餐与账号邮箱，便于快速处理。
          </div>
        </div>
      </div>
    </teleport>
  `,
};
