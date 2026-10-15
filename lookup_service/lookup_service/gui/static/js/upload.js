// Upload page: read the chosen CSV's header row in the browser and let the user click columns to set
// the key. Purely a convenience - the form works without JavaScript.
(function () {
  "use strict";

  const fileInput = document.getElementById("file-input");
  const keyInput = document.getElementById("key-columns");
  const preview = document.getElementById("header-preview");
  const columnsEl = document.getElementById("header-columns");
  if (!fileInput || !keyInput || !preview || !columnsEl) {
    return;
  }

  function parseHeader(line) {
    // Minimal CSV field split that honours double quotes; enough for a header row.
    const fields = [];
    let current = "";
    let quoted = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (quoted) {
        if (ch === '"' && line[i + 1] === '"') { current += '"'; i += 1; }
        else if (ch === '"') { quoted = false; }
        else { current += ch; }
      } else if (ch === '"') { quoted = true; }
      else if (ch === ",") { fields.push(current.trim()); current = ""; }
      else { current += ch; }
    }
    fields.push(current.trim());
    return fields.filter((field) => field.length > 0);
  }

  function selectedKeys() {
    return keyInput.value.split(",").map((s) => s.trim()).filter((s) => s.length > 0);
  }

  function render(columns) {
    columnsEl.replaceChildren();
    const keys = selectedKeys();
    columns.forEach((column) => {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "badge badge--chip" + (keys.includes(column) ? " badge--key" : "");
      chip.textContent = column;
      chip.addEventListener("click", () => {
        const current = selectedKeys();
        const next = current.includes(column) ? current.filter((c) => c !== column) : current.concat([column]);
        keyInput.value = next.join(", ");
        render(columns);
      });
      columnsEl.appendChild(chip);
    });
    preview.hidden = columns.length === 0;
  }

  fileInput.addEventListener("change", () => {
    const file = fileInput.files && fileInput.files[0];
    if (!file) { render([]); return; }
    file.slice(0, 64 * 1024).text().then((text) => {
      const firstLine = text.replace(/^\uFEFF/, "").split(/\r?\n/)[0] || "";
      render(parseHeader(firstLine));
    });
  });
  keyInput.addEventListener("input", () => {
    const chips = Array.from(columnsEl.querySelectorAll("button")).map((b) => b.textContent || "");
    if (chips.length) { render(chips); }
  });
}());
