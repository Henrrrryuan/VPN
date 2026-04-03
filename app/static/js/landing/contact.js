(function () {
  "use strict";

  var CONTACTS = {
    telegram: "@your_telegram",
    wechat: "your_wechat_id",
    qq: "1234567890",
  };

  var PLAN_LABEL = {
    basic: "Basic",
    pro: "Pro",
    premium: "Premium",
  };

  var modal = document.getElementById("contact-modal");
  var planEl = document.getElementById("contact-modal-plan");
  var tgEl = document.getElementById("contact-val-telegram");
  var wxEl = document.getElementById("contact-val-wechat");
  var qqEl = document.getElementById("contact-val-qq");

  if (!modal || !planEl) return;

  if (tgEl) tgEl.textContent = CONTACTS.telegram;
  if (wxEl) wxEl.textContent = CONTACTS.wechat;
  if (qqEl) qqEl.textContent = CONTACTS.qq;

  function openModal(plan) {
    planEl.textContent = PLAN_LABEL[plan] || plan || "套餐";
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    document.body.style.overflow = "hidden";
  }

  function closeModal() {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
    document.body.style.overflow = "";
  }

  document.querySelectorAll("[data-buy-plan]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      openModal(btn.getAttribute("data-buy-plan") || "");
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
