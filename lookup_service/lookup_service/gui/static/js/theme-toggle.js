// Theme toggle button, wired up here (external script) rather than inline, to satisfy the page's CSP.
(function () {
  var html = document.documentElement;
  var btn = document.getElementById("theme-toggle");
  var icon = document.getElementById("theme-icon");

  function apply(theme) {
    html.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("ih-theme", theme);
    } catch (e) {
      /* localStorage unavailable; theme still applies for this page view. */
    }
    if (icon) icon.className = theme === "dark" ? "bi bi-moon-stars-fill" : "bi bi-sun-fill";
  }

  apply(html.getAttribute("data-theme") || "dark");
  if (btn) {
    btn.addEventListener("click", function () {
      apply(html.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });
  }

  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      html.classList.remove("ih-loading");
    });
  });
})();
