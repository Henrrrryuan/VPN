/**
 * /admin/orders — 订单列表、确认收款（行内更新）、复制订阅链接、开通结果抽屉。
 * 依赖 AdminTokenStore（admin_api.js）。
 */
(function () {
  "use strict";

  var S = window.AdminTokenStore;
  if (!S) {
    console.error("admin_api.js must load before admin_orders.js");
    return;
  }

  var els = {};
  var drawerState = { uuid: "", url: "" };

  function $(id) {
    return document.getElementById(id);
  }

  function cacheEls() {
    els.tokenInput = $("admin-token");
    els.badge = $("admin-login-badge");
    els.saveToken = $("save-token");
    els.clearToken = $("clear-admin-token");
    els.loadOrders = $("load-orders");
    els.ordersMsg = $("orders-msg");
    els.ordersWrap = $("orders-wrap");
    els.ordersBody = $("orders-body");
    els.stats = $("orders-stats");
    els.statWaiting = $("stat-waiting");
    els.statCompleted = $("stat-completed");
    els.drawer = $("provision-drawer");
    els.drawerBackdrop = $("provision-drawer-backdrop");
    els.drawerClose = $("provision-drawer-close");
    els.drawerUuid = $("drawer-uuid");
    els.drawerUrl = $("drawer-url");
    els.copyUuid = $("copy-uuid");
    els.copyUrl = $("copy-url");
    els.toast = $("admin-toast");
  }

  function escapeAttr(s) {
    if (s == null) return "";
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function formatCreatedAt(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(iso);
      if (isNaN(d.getTime())) return escapeHtml(iso);
      return d.toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    } catch (e) {
      return escapeHtml(iso);
    }
  }

  function statusBadgeHtml(status) {
    if (status === "waiting") {
      return '<span class="inline-flex items-center rounded-full border border-amber-400/25 bg-amber-500/15 px-2.5 py-0.5 text-xs font-medium text-amber-200">待审核</span>';
    }
    if (status === "completed") {
      return '<span class="inline-flex items-center rounded-full border border-emerald-400/25 bg-emerald-500/15 px-2.5 py-0.5 text-xs font-medium text-emerald-200">已完成</span>';
    }
    return '<span class="text-slate-500">' + escapeHtml(status || "—") + "</span>";
  }

  function actionsHtml(o) {
    var id = o.id;
    var waiting = o.status === "waiting";
    var hasLink = !!(o.subscription_url && String(o.subscription_url).trim());
    var parts = [];
    if (waiting) {
      parts.push(
        '<button type="button" class="confirm-btn rounded-lg bg-gradient-to-r from-violet-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow shadow-indigo-500/25 transition hover:from-violet-500 hover:to-indigo-500 disabled:cursor-not-allowed disabled:opacity-50" data-id="' +
          id +
          '">确认收款</button>'
      );
    }
    if (!waiting && hasLink) {
      parts.push(
        '<button type="button" class="copy-sub-btn ml-1 rounded-lg border border-emerald-500/35 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-200 transition hover:bg-emerald-500/20" data-url="' +
          escapeAttr(o.subscription_url) +
          '">复制订阅链接</button>'
      );
    }
    if (!waiting && !hasLink) {
      parts.push('<span class="text-xs text-slate-600">—</span>');
    }
    return '<div class="flex flex-wrap items-center justify-end gap-1">' + parts.join("") + "</div>";
  }

  function buildRow(o) {
    var tr = document.createElement("tr");
    tr.className = "order-row transition-colors hover:bg-white/[0.03]";
    tr.dataset.orderDbId = String(o.id);
    tr.dataset.status = o.status || "";
    tr.dataset.clientUuid = o.client_uuid || "";
    tr.dataset.subscriptionUrl = o.subscription_url || "";

    tr.innerHTML =
      '<td class="max-w-[200px] truncate px-4 py-3 text-slate-300" data-col="email" title="' +
      escapeAttr(o.user_email) +
      '">' +
      escapeHtml(o.user_email || "—") +
      "</td>" +
      '<td class="px-4 py-3 font-medium text-slate-200" data-col="plan">' +
      escapeHtml(o.plan || "—") +
      "</td>" +
      '<td class="px-4 py-3 text-slate-300" data-col="period">' +
      escapeHtml(o.period || "—") +
      "</td>" +
      '<td class="px-4 py-3 tabular-nums text-slate-200" data-col="amount">¥' +
      (o.amount != null ? escapeHtml(String(o.amount)) : "—") +
      "</td>" +
      '<td class="max-w-[200px] px-4 py-3 font-mono text-[11px] text-slate-400" data-col="trade" title="' +
      escapeAttr(o.alipay_trade_no) +
      '">' +
      escapeHtml(o.alipay_trade_no || "—") +
      "</td>" +
      '<td class="px-4 py-3" data-col="status">' +
      statusBadgeHtml(o.status) +
      "</td>" +
      '<td class="whitespace-nowrap px-4 py-3 text-slate-400" data-col="created">' +
      formatCreatedAt(o.created_at) +
      "</td>" +
      '<td class="px-4 py-3 text-right" data-col="actions">' +
      actionsHtml(o) +
      "</td>";

    return tr;
  }

  function bindRowActions(tr) {
    var confirmBtn = tr.querySelector(".confirm-btn");
    if (confirmBtn) {
      confirmBtn.onclick = function () {
        onConfirmClick(tr, confirmBtn);
      };
    }
    tr.querySelectorAll(".copy-sub-btn").forEach(function (btn) {
      btn.onclick = function () {
        var u = btn.getAttribute("data-url") || "";
        copyToClipboard(u, "订阅链接");
      };
    });
  }

  function updateStats(rows) {
    var w = 0,
      c = 0;
    rows.forEach(function (o) {
      if (o.status === "waiting") w++;
      else if (o.status === "completed") c++;
    });
    if (els.statWaiting) els.statWaiting.textContent = String(w);
    if (els.statCompleted) els.statCompleted.textContent = String(c);
    if (els.stats) els.stats.classList.remove("hidden");
  }

  function showToast(msg) {
    if (!els.toast) return;
    els.toast.textContent = msg;
    els.toast.classList.remove("hidden");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () {
      els.toast.classList.add("hidden");
    }, 2200);
  }

  function copyToClipboard(text, label) {
    if (!text) {
      showToast("无可复制内容");
      return;
    }
    var done = function () {
      showToast((label || "内容") + " 已复制");
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {
        fallbackCopy(text, done);
      });
    } else {
      fallbackCopy(text, done);
    }
  }

  function fallbackCopy(text, cb) {
    var ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      if (cb) cb();
    } catch (e) {
      showToast("复制失败，请手动选择复制");
    }
    document.body.removeChild(ta);
  }

  function setDrawerContent(uuid, url) {
    drawerState.uuid = uuid || "";
    drawerState.url = url || "";
    if (els.drawerUuid) els.drawerUuid.textContent = drawerState.uuid || "—";
    if (els.drawerUrl) els.drawerUrl.textContent = drawerState.url || "—";
  }

  function openDrawer() {
    if (!els.drawer || !els.drawerBackdrop) return;
    els.drawerBackdrop.classList.remove("hidden");
    els.drawer.classList.remove("hidden");
    requestAnimationFrame(function () {
      els.drawer.classList.remove("translate-y-full");
      els.drawer.classList.add("translate-y-0");
    });
  }

  function closeDrawer() {
    if (!els.drawer || !els.drawerBackdrop) return;
    els.drawer.classList.remove("translate-y-0");
    els.drawer.classList.add("translate-y-full");
    setTimeout(function () {
      els.drawer.classList.add("hidden");
      els.drawerBackdrop.classList.add("hidden");
    }, 280);
  }

  function applyCompletedRow(tr, data) {
    var uuid = (data && data.client_uuid) || "";
    var url = (data && data.subscription_url) || "";
    tr.dataset.status = "completed";
    tr.dataset.clientUuid = uuid;
    tr.dataset.subscriptionUrl = url;

    var statusCell = tr.querySelector('[data-col="status"]');
    if (statusCell) statusCell.innerHTML = statusBadgeHtml("completed");

    var actionsCell = tr.querySelector('[data-col="actions"]');
    if (actionsCell) {
      var id = tr.dataset.orderDbId;
      actionsCell.innerHTML = actionsHtml({
        id: Number(id, 10),
        status: "completed",
        subscription_url: url,
      });
      bindRowActions(tr);
    }

    setDrawerContent(uuid, url);
    openDrawer();
  }

  async function onConfirmClick(tr, btn) {
    var id = Number(tr.dataset.orderDbId, 10);
    if (!id || btn.disabled) return;
    btn.disabled = true;
    var prevText = btn.textContent;
    btn.textContent = "处理中…";

    var r2 = await S.adminFetch("/api/admin/orders/" + id + "/confirm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });

    var b2;
    try {
      b2 = await r2.json();
    } catch (e) {
      b2 = { message: "invalid json" };
    }

    btn.disabled = false;
    btn.textContent = prevText;

    if (r2.ok && b2.success && b2.data) {
      applyCompletedRow(tr, b2.data);
      updateStatsFromDom();
      if (els.ordersMsg) els.ordersMsg.textContent = "订单 #" + id + " 已确认并同步 X-UI";
    } else {
      showToast((b2 && b2.message) || "确认失败 HTTP " + r2.status);
      if (els.ordersMsg) els.ordersMsg.textContent = (b2 && b2.message) || "HTTP " + r2.status;
    }
  }

  function updateStatsFromDom() {
    if (!els.ordersBody) return;
    var w = 0,
      c = 0;
    els.ordersBody.querySelectorAll("tr.order-row").forEach(function (tr) {
      var s = tr.dataset.status;
      if (s === "waiting") w++;
      else if (s === "completed") c++;
    });
    if (els.statWaiting) els.statWaiting.textContent = String(w);
    if (els.statCompleted) els.statCompleted.textContent = String(c);
  }

  async function loadOrders() {
    if (!els.ordersMsg) return;
    if (!S.getToken()) {
      els.ordersMsg.textContent = "请先填写管理令牌并点击「保存令牌」。";
      return;
    }
    els.ordersMsg.textContent = "加载中…";
    if (els.loadOrders) els.loadOrders.disabled = true;

    var resp = await S.adminFetch("/api/admin/orders", {});
    var body;
    try {
      body = await resp.json();
    } catch (e) {
      body = null;
    }

    if (els.loadOrders) els.loadOrders.disabled = false;

    if (!resp.ok) {
      els.ordersMsg.textContent = (body && body.message) || "HTTP " + resp.status;
      return;
    }

    var orders = (body.data && body.data.orders) || [];
    els.ordersMsg.textContent = "共 " + orders.length + " 条订单（最近 300 条）";
    updateStats(orders);

    els.ordersBody.innerHTML = "";
    orders.forEach(function (o) {
      var tr = buildRow(o);
      els.ordersBody.appendChild(tr);
      bindRowActions(tr);
    });

    els.ordersWrap.classList.remove("hidden");
  }

  function syncTokenUI() {
    var tok = S.getToken();
    if (els.badge) {
      if (tok) els.badge.classList.remove("hidden");
      else els.badge.classList.add("hidden");
    }
    if (els.tokenInput) {
      if (tok) els.tokenInput.value = tok;
      else els.tokenInput.value = "";
    }
  }

  function init() {
    cacheEls();
    if (!els.tokenInput) return;

    ["admin-token-saved", "admin-token-cleared", "admin-token-invalid"].forEach(function (ev) {
      window.addEventListener(ev, syncTokenUI);
    });

    els.tokenInput.value = S.getToken();
    syncTokenUI();

    els.saveToken.onclick = function () {
      var v = els.tokenInput.value.trim();
      if (!v) {
        els.ordersMsg.textContent = "请先输入令牌。";
        return;
      }
      S.setToken(v);
      els.ordersMsg.textContent = "令牌已保存。";
    };

    els.clearToken.onclick = function () {
      S.clearToken();
      els.ordersMsg.textContent = "已清除本地令牌。";
    };

    els.loadOrders.onclick = loadOrders;

    if (els.drawerClose) els.drawerClose.onclick = closeDrawer;
    if (els.drawerBackdrop) els.drawerBackdrop.onclick = closeDrawer;

    if (els.copyUuid) {
      els.copyUuid.onclick = function () {
        copyToClipboard(drawerState.uuid, "UUID");
      };
    }
    if (els.copyUrl) {
      els.copyUrl.onclick = function () {
        copyToClipboard(drawerState.url, "订阅链接");
      };
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && els.drawer && !els.drawer.classList.contains("hidden")) {
        closeDrawer();
      }
    });

    if (S.getToken()) loadOrders();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
