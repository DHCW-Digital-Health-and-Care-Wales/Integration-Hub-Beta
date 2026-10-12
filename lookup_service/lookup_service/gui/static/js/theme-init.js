// Applied as an external, render-blocking script (not inline) so it runs under the page's
// CSP (default-src 'self') and still lands before first paint to avoid a theme flash.
(function () {
  try {
    var t = localStorage.getItem("ih-theme") || "dark";
    document.documentElement.setAttribute("data-theme", t);
    document.documentElement.classList.add("ih-loading");
  } catch (e) {
    /* localStorage unavailable (e.g. private browsing); fall back to the default dark theme. */
  }
})();
