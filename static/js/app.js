/* CHECKMATE ARENA — perilaku antarmuka umum (sidebar mobile). */

(function () {
  "use strict";

  var body = document.body;
  var toggles = document.querySelectorAll("[data-sidebar-toggle]");

  function setOpen(open) {
    body.classList.toggle("sidebar-open", open);
    toggles.forEach(function (btn) {
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  toggles.forEach(function (btn) {
    btn.addEventListener("click", function () {
      setOpen(!body.classList.contains("sidebar-open"));
    });
  });

  document.querySelectorAll("[data-sidebar-close]").forEach(function (el) {
    el.addEventListener("click", function () {
      setOpen(false);
    });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      setOpen(false);
    }
  });

  window.matchMedia("(min-width: 901px)").addEventListener("change", function (event) {
    if (event.matches) {
      setOpen(false);
    }
  });
})();