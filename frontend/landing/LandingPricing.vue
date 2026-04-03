<template>
  <div>
    <div class="flex items-end justify-between gap-6">
      <div>
        <h2 class="text-2xl font-extrabold sm:text-3xl">选择你的套餐</h2>
        <p class="mt-2 text-slate-300">人工开通：购买后联系客服完成开通与交付。</p>
      </div>
      <div class="hidden rounded-2xl border border-white/10 bg-white/5 px-4 py-3 md:block">
        <div class="text-xs text-slate-400">支持</div>
        <div class="mt-1 text-sm font-semibold text-white">ChatGPT / Netflix / 全球节点</div>
      </div>
    </div>

    <div class="mt-8 grid gap-5 lg:grid-cols-3">
      <!-- 三档套餐：与 app/static/js/landing/LandingPricing.js 保持同步 -->
      <div class="rounded-[2rem] border border-white/10 bg-white/5 p-6 sm:p-7">
        <div class="flex items-start justify-between">
          <div>
            <div class="text-lg font-bold text-white">Basic</div>
            <div class="mt-1 text-sm text-slate-300">100GB / 月</div>
          </div>
          <div class="rounded-xl border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-slate-200">入门</div>
        </div>
        <div class="mt-6">
          <div class="text-4xl font-extrabold text-white">$9.99</div>
          <div class="mt-1 text-sm text-slate-400">按月订阅</div>
        </div>
        <button
          type="button"
          class="mt-7 inline-flex w-full justify-center rounded-2xl bg-indigo-500/90 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500"
          @click="openPurchase('basic')"
        >
          购买 Basic
        </button>
      </div>

      <div class="relative rounded-[2rem] border border-indigo-400/30 bg-gradient-to-b from-indigo-500/15 to-white/5 p-6 sm:p-7">
        <div
          class="absolute -top-3 left-6 rounded-full bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-4 py-1 text-xs font-semibold text-white shadow-lg shadow-indigo-500/20"
        >
          最受欢迎
        </div>
        <div class="pt-4">
          <div class="flex items-start justify-between">
            <div>
              <div class="text-lg font-bold text-white">Pro</div>
              <div class="mt-1 text-sm text-slate-300">300GB / 月</div>
            </div>
            <div class="rounded-xl border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-slate-200">高性价比</div>
          </div>
          <div class="mt-6">
            <div class="text-4xl font-extrabold text-white">$19.99</div>
            <div class="mt-1 text-sm text-slate-400">按月订阅</div>
          </div>
          <button
            type="button"
            class="mt-7 inline-flex w-full justify-center rounded-2xl bg-gradient-to-r from-indigo-500 to-fuchsia-500 px-4 py-3 text-sm font-semibold text-white transition hover:opacity-95"
            @click="openPurchase('pro')"
          >
            购买 Pro
          </button>
        </div>
      </div>

      <div class="rounded-[2rem] border border-white/10 bg-white/5 p-6 sm:p-7">
        <div class="flex items-start justify-between">
          <div>
            <div class="text-lg font-bold text-white">Premium</div>
            <div class="mt-1 text-sm text-slate-300">1TB / 月</div>
          </div>
          <div class="rounded-xl border border-white/15 bg-white/5 px-3 py-1.5 text-xs text-slate-200">重度用户</div>
        </div>
        <div class="mt-6">
          <div class="text-4xl font-extrabold text-white">$39.99</div>
          <div class="mt-1 text-sm text-slate-400">按月订阅</div>
        </div>
        <button
          type="button"
          class="mt-7 inline-flex w-full justify-center rounded-2xl bg-indigo-500/90 px-4 py-3 text-sm font-semibold text-white transition hover:bg-indigo-500"
          @click="openPurchase('premium')"
        >
          购买 Premium
        </button>
      </div>
    </div>

    <ContactModal v-model:open="modalOpen" :plan-id="planId" />
  </div>
</template>

<script setup>
import { ref } from "vue";
import ContactModal from "./ContactModal.vue";

const modalOpen = ref(false);
const planId = ref("basic");

function openPurchase(id) {
  planId.value = id;
  modalOpen.value = true;
}
</script>
