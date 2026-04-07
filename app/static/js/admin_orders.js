/**
 * /admin/orders — 分页列表、确认收款、删除订单、复制订阅链接、开通结果抽屉。
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
  var ordersState = { page: 1, perPage: 10, totalPages: 1 };

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
    els.ordersPagination = $("orders-pagination");
    els.ordersPageInfo = $("orders-page-info");
    els.ordersPrevPage = $("orders-prev-page");
    els.ordersNextPage = $("orders-next-page");
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
    parts.push(
      '<button type="button" class="delete-order-btn ml-1 rounded-lg border border-red-500/35 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-200 transition hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-50" data-id="' +
        id +
        '">删除</button>'
    );
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
    var delBtn = tr.querySelector(".delete-order-btn");
    if (delBtn) {
      delBtn.onclick = function () {
        onDeleteClick(tr, delBtn);
      };
    }
  }

  function updateStatsFromApi(stats) {
    if (!stats) return;
    if (els.statWaiting) els.statWaiting.textContent = String(stats.waiting != null ? stats.waiting : 0);
    if (els.statCompleted) els.statCompleted.textContent = String(stats.completed != null ? stats.completed : 0);
    if (els.stats) els.stats.classList.remove("hidden");
  }

  function renderPagination(d) {
    var total = d.total != null ? d.total : 0;
    var page = d.page != null ? d.page : 1;
    var tp = d.total_pages != null ? d.total_pages : 1;
    var per = d.per_page != null ? d.per_page : ordersState.perPage;
    ordersState.page = page;
    ordersState.totalPages = tp;
    if (!els.ordersPagination || !els.ordersPageInfo) return;
    if (total === 0) {
      els.ordersPagination.classList.add("hidden");
      return;
    }
    els.ordersPagination.classList.remove("hidden");
    els.ordersPageInfo.textContent = "第 " + page + " / " + tp + " 页 · 每页 " + per + " 条 · 共 " + total + " 条";
    if (els.ordersPrevPage) els.ordersPrevPage.disabled = page <= 1;
    if (els.ordersNextPage) els.ordersNextPage.disabled = page >= tp;
  }

  function showToast(msg, durationMs) {
    if (!els.toast) return;
    els.toast.textContent = msg;
    els.toast.classList.remove("hidden");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () {
      els.toast.classList.add("hidden");
    }, typeof durationMs === "number" && durationMs > 0 ? durationMs : 2200);
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
      if (els.statWaiting) {
        var w = Math.max(0, parseInt(els.statWaiting.textContent, 10) - 1);
        els.statWaiting.textContent = String(isNaN(w) ? 0 : w);
      }
      if (els.statCompleted) {
        var c = parseInt(els.statCompleted.textContent, 10) + 1;
        els.statCompleted.textContent = String(isNaN(c) ? 1 : c);
      }
      if (els.ordersMsg) els.ordersMsg.textContent = "订单 #" + id + " 已确认并同步 X-UI";
    } else {
      showToast((b2 && b2.message) || "确认失败 HTTP " + r2.status);
      if (els.ordersMsg) els.ordersMsg.textContent = (b2 && b2.message) || "HTTP " + r2.status;
    }
  }

  /**
   * 新接口带 total/total_pages；旧接口一次返回整表且无 total 时，在浏览器内按页切片（每页 perPage 条）。
   */
  function splitOrdersForView(d) {
    var raw = (d && d.orders) || [];
    var hasServerPaging = d && d.total != null && d.total_pages != null;
    if (hasServerPaging) {
      return {
        orders: raw,
        total: d.total,
        total_pages: d.total_pages,
        page: d.page != null ? d.page : ordersState.page,
        per_page: d.per_page != null ? d.per_page : ordersState.perPage,
        stats: d.stats,
        legacySlice: false,
      };
    }
    var per = ordersState.perPage;
    var total = raw.length;
    var total_pages = Math.max(1, Math.ceil(total / per) || 1);
    var page = Math.min(Math.max(1, ordersState.page), total_pages);
    ordersState.page = page;
    var start = (page - 1) * per;
    var slice = raw.slice(start, start + per);
    var stats = d.stats;
    if (!stats && raw.length) {
      var w = 0,
        c = 0;
      raw.forEach(function (o) {
        if (o.status === "waiting") w++;
        else if (o.status === "completed") c++;
      });
      stats = { waiting: w, completed: c };
    }
    return {
      orders: slice,
      total: total,
      total_pages: total_pages,
      page: page,
      per_page: per,
      stats: stats,
      legacySlice: true,
    };
  }

  async function onDeleteClick(tr, btn) {
    var id = Number(tr.dataset.orderDbId, 10);
    if (!id || btn.disabled) return;
    var emailCell = tr.querySelector('[data-col="email"]');
    var emailHint = emailCell ? emailCell.getAttribute("title") || emailCell.textContent.trim() : "";
    var msg = "确定删除订单 #" + id + "？此操作不可恢复。";
    if (emailHint && emailHint !== "—") {
      msg = "确定删除订单 #" + id + "（" + emailHint + "）？此操作不可恢复。";
    }
    if (!window.confirm(msg)) return;
    btn.disabled = true;
    var prev = btn.textContent;
    btn.textContent = "删除中…";

    // POST 避免部分反代丢弃 DELETE 导致 404
    var resp = await S.adminFetch("/api/admin/orders/" + id + "/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    var body;
    try {
      body = await resp.json();
    } catch (e) {
      body = null;
    }

    btn.disabled = false;
    btn.textContent = prev;

    if (!resp.ok || !body || !body.success) {
      var errMsg = (body && body.message) || "删除失败 HTTP " + resp.status;
      if (!body && resp.status === 404) {
        errMsg = "删除接口 404：请部署含 POST /api/admin/orders/<id>/delete 的最新后端，并重启服务。";
      }
      showToast(errMsg, 8000);
      if (els.ordersMsg) els.ordersMsg.textContent = errMsg;
      return;
    }

    showToast("已删除");
    var rowsOnPage = els.ordersBody ? els.ordersBody.querySelectorAll("tr.order-row").length : 0;
    if (rowsOnPage <= 1 && ordersState.page > 1) {
      ordersState.page--;
    }
    await loadOrdersPage();
  }

  async function loadOrdersPage(opts) {
    opts = opts || {};
    if (!els.ordersMsg) return;
    if (!S.getToken()) {
      els.ordersMsg.textContent = "请先填写管理令牌并点击「保存令牌」。";
      return;
    }
    if (opts.resetPage) {
      ordersState.page = 1;
    }

    els.ordersMsg.textContent = "加载中…";
    if (els.loadOrders) els.loadOrders.disabled = true;

    var q = "?page=" + encodeURIComponent(String(ordersState.page)) + "&per_page=" + encodeURIComponent(String(ordersState.perPage));
    var resp = await S.adminFetch("/api/admin/orders" + q, {});
    var body;
    try {
      body = await resp.json();
    } catch (e) {
      body = null;
    }

    if (els.loadOrders) els.loadOrders.disabled = false;

    if (!resp.ok) {
      var errLine = (body && body.message) || "HTTP " + resp.status;
      els.ordersMsg.textContent = errLine;
      els.ordersMsg.classList.remove("text-slate-400", "text-emerald-200/90");
      els.ordersMsg.classList.add("text-amber-200");
      if (els.ordersPagination) els.ordersPagination.classList.add("hidden");
      if (resp.status === 403) {
        showToast(
          "403：服务端未读取到 ADMIN_TOKEN。请在项目根目录 .env 中设置该项并重启进程；部署环境还需在 VPS 的 .env 配置并 systemctl restart。",
          12000
        );
      } else if (resp.status === 401) {
        showToast("401：令牌与服务器 ADMIN_TOKEN 不一致。", 5000);
      }
      return;
    }

    els.ordersMsg.classList.remove("text-amber-200");
    els.ordersMsg.classList.add("text-slate-400");

    var d = body.data || {};
    var view = splitOrdersForView(d);
    var orders = view.orders;
    updateStatsFromApi(view.stats);
    renderPagination({
      total: view.total,
      total_pages: view.total_pages,
      page: view.page,
      per_page: view.per_page,
    });

    if (view.total === 0) {
      els.ordersMsg.textContent = "暂无订单";
    } else {
      els.ordersMsg.textContent =
        "本页 " +
        orders.length +
        " 条（全库 " +
        view.total +
        " 条）" +
        (view.legacySlice ? " · 兼容模式：后端未分页，由浏览器切片" : "");
    }

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

    els.loadOrders.onclick = function () {
      loadOrdersPage({ resetPage: true });
    };

    if (els.ordersPrevPage) {
      els.ordersPrevPage.onclick = function () {
        if (ordersState.page <= 1) return;
        ordersState.page--;
        loadOrdersPage();
      };
    }
    if (els.ordersNextPage) {
      els.ordersNextPage.onclick = function () {
        if (ordersState.page >= ordersState.totalPages) return;
        ordersState.page++;
        loadOrdersPage();
      };
    }

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

    if (S.getToken()) loadOrdersPage({ resetPage: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
