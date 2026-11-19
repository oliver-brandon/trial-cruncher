// Edit a staged copy. Python validates the complete transaction before committing it.
(() => {
  "use strict";
  const PAGE_SIZE = 50;
  const fields = {
    phase: "Phase", condition: "Condition / treatment", included: "Inclusion", inclusion_reason: "Reason"
  };

  function element(tag, text) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function request(bridge, method, ...args) {
    return new Promise((resolve, reject) => bridge[method](...args, (raw) => {
      try {
        const value = JSON.parse(raw);
        if (value.error) throw new Error(value.error);
        resolve(value);
      } catch (error) { reject(error); }
    }));
  }

  function editor(key, value, change) {
    let input;
    if (key === "included") {
      input = element("select");
      for (const [label, code] of [["Not reviewed", ""], ["Include", "yes"], ["Exclude", "no"]]) {
        input.add(new Option(label, code));
      }
      input.value = value === true ? "yes" : value === false ? "no" : "";
      input.onchange = () => change(input.value === "" ? null : input.value === "yes");
    } else {
      input = element(key === "inclusion_reason" ? "textarea" : "input");
      if (key === "phase") input.setAttribute("list", "phase-suggestions");
      input.value = value ?? "";
      input.placeholder = key === "phase" ? "Select or type a label" : "Unassigned";
      input.oninput = () => change(input.value.trim() || null);
    }
    input.setAttribute("aria-label", fields[key]);
    input.dataset.field = key;
    return input;
  }

  async function open(kind, bridge) {
    if (document.getElementById("assignments")) return;
    const phase = kind === "phase";
    const dialog = element("dialog");
    dialog.id = "assignments";
    dialog.setAttribute("aria-labelledby", "assignment-title");
    const heading = element("h2", phase ? "Assign phases" : "Session metadata");
    heading.id = "assignment-title";
    const hint = element("p", phase
      ? "Assign one phase per recording. Import Med-PC again to apply your changes."
      : "Save applies metadata immediately. Each excluded recording requires a reason.");
    const search = element("input");
    search.type = "search"; search.placeholder = "Find a recording by path";
    search.setAttribute("aria-label", search.placeholder);
    const bulk = element("div"); bulk.className = "assignment-tools";
    const field = element("select");
    field.setAttribute("aria-label", "Field to apply");
    const columns = phase ? ["phase"] : Object.keys(fields).filter(k => k !== "phase");
    for (const key of columns) field.add(new Option(fields[key], key));
    const entry = element("span"); entry.className = "assignment-entry";
    const apply = element("button", "Apply to selected");
    const all = element("button", "Apply to all files");
    bulk.append(field, entry, apply, all);
    const wrap = element("div"); wrap.className = "assignment-scroll";
    const table = element("table"), head = table.createTHead().insertRow();
    const selectAll = element("input"); selectAll.type = "checkbox";
    selectAll.setAttribute("aria-label", "Select all matching recordings");
    const mark = element("th"); mark.append(selectAll); head.append(mark);
    for (const title of ["Source file", ...columns.map(k => fields[k])]) head.append(element("th", title));
    const body = table.createTBody(); wrap.append(table);
    const footer = element("footer"), count = element("span");
    const prev = element("button", "Previous"), next = element("button", "Next");
    const cancel = element("button", "Cancel"), save = element("button", "Save assignments");
    save.className = "primary"; save.disabled = true;
    footer.append(count, prev, next, cancel, save);
    const message = element("p"); message.setAttribute("role", "alert");
    const hints = element("datalist"); hints.id = "phase-suggestions";
    for (const label of ["Acquisition", "Reversal"]) hints.append(new Option(label, label));
    dialog.append(heading, hint, search, bulk, wrap, message, footer, hints);
    document.body.append(dialog);
    const closed = new Promise(resolve => dialog.addEventListener("close", () => {
      dialog.remove(); resolve();
    }, {once: true}));
    dialog.showModal();
    cancel.onclick = () => dialog.close();
    const rows = [], selected = new Set(), dirty = new Map();
    let filtered = [], page = 0, anchor = null, bulkValue = null, bulkReason = null;

    const current = row => dirty.has(row.id) ? dirty.get(row.id) : row[kind];
    function change(row, key, value) {
      const updated = phase ? value ?? "" : {...current(row), [key]: value};
      if (JSON.stringify(updated) === JSON.stringify(row[kind])) dirty.delete(row.id);
      else dirty.set(row.id, updated);
      save.disabled = dirty.size === 0;
      message.textContent = "";
    }
    function selection() {
      apply.disabled = !selected.size;
      apply.textContent = selected.size ? 'Apply to selected (' + selected.size + ')' : 'Apply to selected';
      selectAll.checked = filtered.length > 0 && filtered.every(row => selected.has(row.id));
      selectAll.indeterminate = !selectAll.checked && filtered.some(row => selected.has(row.id));
    }
    function draw() {
      body.replaceChildren();
      const start = page * PAGE_SIZE;
      filtered.slice(start, start + PAGE_SIZE).forEach((row, i) => {
        const tr = body.insertRow();
        const box = element("input"); box.type = "checkbox"; box.checked = selected.has(row.id);
        box.setAttribute("aria-label", "Select " + row.id);
        const index = start + i;
        const toggle = (checked, range) => {
          const from = range && anchor !== null ? Math.min(anchor, index) : index;
          const to = range && anchor !== null ? Math.max(anchor, index) : index;
          for (const item of filtered.slice(from, to + 1)) {
            if (checked) selected.add(item.id); else selected.delete(item.id);
          }
          anchor = index; draw();
          body.rows[i]?.querySelector("input")?.focus();
        };
        tr.setAttribute("aria-selected", String(box.checked));
        box.onclick = event => toggle(box.checked, event.shiftKey);
        tr.insertCell().append(box);
        const name = tr.insertCell(); name.textContent = row.id; name.title = row.id;
        name.onclick = event => toggle(!selected.has(row.id), event.shiftKey);
        for (const key of columns) {
          const value = phase ? current(row) : current(row)[key];
          tr.insertCell().append(editor(key, value, v => change(row, key, v)));
        }
      });
      prev.disabled = page === 0; next.disabled = start + PAGE_SIZE >= filtered.length;
      count.textContent = filtered.length ? (start + 1) + '–' + Math.min(start + PAGE_SIZE, filtered.length)
        + ' of ' + filtered.length + ' recordings' : 'No matching recordings';
      selection();
    }
    function filter() {
      filtered = rows.filter(row => row.id.toLowerCase().includes(search.value.toLowerCase()));
      page = 0; anchor = null; draw();
    }
    function chooseField() {
      bulkValue = null; bulkReason = null;
      entry.replaceChildren(editor(field.value, null, v => { bulkValue = v; }));
      if (field.value === "included") entry.append(editor("inclusion_reason", null, v => { bulkReason = v; }));
    }
    function applyTo(items) {
      for (const row of items) {
        change(row, field.value, bulkValue);
        if (field.value === "included") change(row, "inclusion_reason", bulkReason);
      }
      draw();
    }
    selectAll.onchange = () => {
      for (const row of filtered) {
        if (selectAll.checked) selected.add(row.id); else selected.delete(row.id);
      }
      draw();
    };
    search.oninput = filter;
    field.onchange = chooseField;
    apply.onclick = () => applyTo(rows.filter(row => selected.has(row.id)));
    all.onclick = () => applyTo(rows);
    prev.onclick = () => { page--; draw(); };
    next.onclick = () => { page++; draw(); };
    save.onclick = async () => {
      const invalid = dialog.querySelector(":invalid");
      if (invalid) {
        invalid.reportValidity(); return;
      }
      save.disabled = true;
      const changes = rows.filter(row => dirty.has(row.id)).map(row => ({
        id: row.id, before: row[kind], value: dirty.get(row.id)
      }));
      try {
        await request(bridge, "saveAssignments", JSON.stringify({kind, changes}));
        dialog.close();
      } catch (err) { message.textContent = err.message; save.disabled = false; }
    };
    chooseField();
    try {
      let pageData;
      do {
        pageData = await request(bridge, "assignmentPage", rows.length, 250);
        if (!dialog.open) return;
        rows.push(...pageData.rows);
      } while (rows.length < pageData.total && pageData.rows.length);
      filter();
      search.focus();
    } catch (error) { dialog.close(); throw error; }
    return closed;
  }
  window.TrialAssignments = {open};
})();
