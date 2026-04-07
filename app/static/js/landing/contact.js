(function () {
  "use strict";

  var CONTACTS = {
    telegram: "@your_telegram",
    wechat: "your_wechat_id",
    qq: "1234567890",
  };

  function getLoginUrl() {
    var m = document.querySelector('meta[name="app-login"]');
    var u = m && m.getAttribute("content");
    return u && String(u).trim() ? String(u).trim() : "/login";
  }

  var modal = document.getElementById("contact-modal");
  var planEl = document.getElementById("contact-modal-plan");
  var tgEl = document.getElementById("contact-val-telegram");
  var wxEl = document.getElementById("contact-val-wechat");
  var qqEl = document.getElementById("contact-val-qq");

  if (!modal || !planEl) return;

  if (tgEl) tgEl.textContent = CONTACTS.telegram;
  if (wxEl) wxEl.textContent = CONTACTS.wechat;
  if (qqEl) qqEl.textContent = CONTACTS.qq;

  function closeModal() {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    document.body.style.overflow = "";
  }

  function openContactModal(planLabel) {
    if (planEl) planEl.textContent = planLabel || "咨询与售后";
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    document.body.style.overflow = "hidden";
  }

  document.querySelectorAll("[data-buy-plan]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      window.location.href = getLoginUrl() + "#register";
    });
  });

  document.querySelectorAll("[data-open-contact]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var label = btn.getAttribute("data-contact-plan") || "咨询与售后";
      openContactModal(label);
    });
  });

  var closeBtn = document.getElementById("contact-modal-close");
  if (closeBtn) closeBtn.addEventListener("click", closeModal);

  modal.addEventListener("click", function (e) {
    if (e.target === modal) closeModal();
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !modal.classList.contains("hidden")) closeModal();
  });

  function flash(btn, ok) {
    var t = btn.textContent;
    btn.textContent = ok ? "已复制" : "失败";
    btn.disabled = true;
    setTimeout(function () {
      btn.textContent = t;
      btn.disabled = false;
    }, 1200);
  }

  function copyText(text, btn) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          flash(btn, true);
        },
        function () {
          fallbackCopy(text, btn);
        }
      );
    } else {
      fallbackCopy(text, btn);
    }
  }

  function fallbackCopy(text, btn) {
    try {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      flash(btn, true);
    } catch (e) {
      flash(btn, false);
    }
  }

  document.querySelectorAll("[data-copy-key]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var key = btn.getAttribute("data-copy-key");
      if (!key || !CONTACTS[key]) return;
      copyText(CONTACTS[key], btn);
    });
  });
})();
