<template>
  <teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[100] flex items-end justify-center bg-black/60 p-4 backdrop-blur-sm sm:items-center"
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
          <div v-for="row in rows" :key="row.key" class="rounded-xl border border-white/10 bg-white/5 p-3">
            <div class="text-xs font-medium text-slate-400">{{ row.label }}</div>
            <div class="mt-1 flex items-center justify-between gap-2">
              <span class="truncate font-mono text-sm text-white">{{ row.value }}</span>
              <button
                type="button"
                class="shrink-0 rounded-lg bg-indigo-500/90 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500"
                @click="copy(row.key)"
              >
                {{ copiedKey === row.key ? "已复制" : "复制" }}
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
</template>

<script setup>
import { computed, ref, watch } from "vue";

const props = defineProps({
  open: { type: Boolean, default: false },
  planId: { type: String, default: "" },
});

const emit = defineEmits(["update:open"]);

const contacts = {
  telegram: "@your_telegram",
  wechat: "your_wechat_id",
  qq: "1234567890",
};

const copiedKey = ref("");

const planTitle = computed(() => {
  const m = { basic: "Basic", pro: "Pro", premium: "Premium" };
  return m[props.planId] || "套餐";
});

const rows = computed(() => [
  { key: "telegram", label: "Telegram", value: contacts.telegram },
  { key: "wechat", label: "微信", value: contacts.wechat },
  { key: "qq", label: "QQ", value: contacts.qq },
]);

watch(
  () => props.open,
  (v) => {
    if (v) copiedKey.value = "";
  }
);

function close() {
  emit("update:open", false);
}

async function copy(key) {
  const text = contacts[key];
  try {
    await navigator.clipboard.writeText(text);
    copiedKey.value = key;
    setTimeout(() => {
      if (copiedKey.value === key) copiedKey.value = "";
    }, 1600);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    copiedKey.value = key;
  }
}
</script>
