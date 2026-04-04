/**
 * 订单管理页：localStorage 持久化 ADMIN_TOKEN；请求 /api/admin/orders* 时附加 X-Admin-Token。
 * 依赖 <meta name="api-base" content="{{ request.script_root or '' }}" />
 */
(function (global) {
  var LS_KEY = "admin_token";
  var LEGACY_SK = "vpn_saas_admin_token";

  function getScriptRoot() {
    var meta = document.querySelector('meta[name="api-base"]');
    var base = meta && meta.getAttribute("content") ? meta.getAttribute("content").trim() : "";
    return base.replace(/\/?$/, "");
  }

  function apiUrl(path) {
    var p = path.startsWith("/") ? path : "/" + path;
    var base = getScriptRoot();
    return base ? base + p : p;
  }

  function migrateLegacy() {
    try {
      var old = global.sessionStorage.getItem(LEGACY_SK);
      if (old && !global.localStorage.getItem(LS_KEY)) {
        global.localStorage.setItem(LS_KEY, old.trim());
        global.sessionStorage.removeItem(LEGACY_SK);
      }
    } catch (e) {}
  }

  migrateLegacy();

  function getToken() {
    try {
      return (global.localStorage.getItem(LS_KEY) || "").trim();
    } catch (e) {
      return "";
    }
  }

  function setToken(value) {
    var v = (value || "").trim();
    try {
      if (v) global.localStorage.setItem(LS_KEY, v);
      else global.localStorage.removeItem(LS_KEY);
    } catch (e) {}
    global.dispatchEvent(new CustomEvent("admin-token-saved", { detail: { hasToken: !!v } }));
  }

  function clearToken() {
    try {
      global.localStorage.removeItem(LS_KEY);
    } catch (e) {}
    global.dispatchEvent(new CustomEvent("admin-token-cleared"));
  }

  async function adminFetch(path, init) {
    init = init || {};
    var headers = new Headers(init.headers || {});
    var tok = getToken();
    if (tok) headers.set("X-Admin-Token", tok);
    var resp = await fetch(apiUrl(path), Object.assign({}, init, { headers: headers }));
    if (resp.status === 401) {
      clearToken();
      global.dispatchEvent(new CustomEvent("admin-token-invalid"));
      try {
        global.alert("登录失效，请重新输入管理员令牌");
      } catch (e) {}
    }
    return resp;
  }

  global.AdminTokenStore = {
    LS_KEY: LS_KEY,
    apiUrl: apiUrl,
    getToken: getToken,
    setToken: setToken,
    clearToken: clearToken,
    adminFetch: adminFetch,
  };
})(typeof window !== "undefined" ? window : globalThis);
