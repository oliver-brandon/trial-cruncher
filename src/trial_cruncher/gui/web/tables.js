/* Batch and inspector views. All scientific values come from the Python models. */
(() => {
  let bridge, currentState, view = "sessions", selected = null, detailTab = "Session metrics";
  let offset = 0, choiceOffset = 0, sortColumn = -1, descending = false, request = 0, detailRequest = 0;
  const size = 100;
  const widths = new Map();
  let batchSnapshot = "", detailSnapshot = "", filterSnapshot = "";
  let lastBatchRevision, lastDetailRevision;
  const $ = id => document.getElementById(id);
  const node = (tag, text, className) => {
    const el = document.createElement(tag);
    if (text !== undefined && text !== null) el.textContent = String(text);
    if (className) el.className = className;
    return el;
  };
  const call = (name, data, done = () => {}) => bridge.action(name, JSON.stringify(data), done);
  const parse = value => { try { return JSON.parse(value); } catch { return {}; } };
  function table(headers, rows, onSort, onSelect, columns = headers.map((_, i) => i), numeric = [], scope = `batch:${view}`) {
    const table = node("table"), head = node("thead"), hr = node("tr");
    table.classList.add("resizable-table");
    const colgroup = node("colgroup");
    const columnWidths = headers.map((label, column) =>
      widths.get(`${scope}:${columns[column]}`) ||
        (/file|metric/i.test(label) ? 210 : /reason|detail/i.test(label) ? 330 :
          Math.max(110, Math.min(240, label.length * 8 + 36)))
    );
    const applyWidths = () => {
      columnWidths.forEach((width, i) => { colgroup.children[i].style.width = `${width}px`; });
      table.style.width = `${columnWidths.reduce((sum, width) => sum + width, 0)}px`;
    };
    const container = scope.startsWith("inspector:") ? $("inspector-content") : $("batch-table");
    const extra = Math.max(0, (container?.clientWidth || 0) -
      columnWidths.reduce((sum, width) => sum + width, 0));
    if (extra && columnWidths.length && !widths.has(`${scope}:${columns[columns.length - 1]}`)) {
      columnWidths[columnWidths.length - 1] += extra;
    }
    headers.forEach(() => colgroup.append(node("col")));
    table.append(colgroup);
    applyWidths();
    headers.forEach((label, column) => {
      const th = node("th", label);
      if (numeric[column]) th.classList.add("numeric");
      if (onSort) {
        const direction = sortColumn === columns[column] ? (descending ? "descending" : "ascending") : "none";
        th.setAttribute("aria-sort", direction);
        if (direction !== "none") th.append(node("span", descending ? " ▼" : " ▲"));
      }
      if (onSort) { th.tabIndex = 0; th.onclick = () => onSort(columns[column]); th.onkeydown = e => { if (e.key === "Enter") onSort(columns[column]); }; }
      hr.append(th);
    });
    head.append(hr); table.append(head);
    hr.querySelectorAll("th").forEach((th, column) => {
      const grip = node("span"); grip.className = "column-grip";
      grip.onpointerdown = event => {
        event.stopPropagation(); event.preventDefault();
        const start = event.clientX, width = th.getBoundingClientRect().width;
        grip.setPointerCapture(event.pointerId);
        grip.onpointermove = move => {
          const w = Math.max(60, Math.round(width + move.clientX - start));
          widths.set(`${scope}:${columns[column]}`, w);
          columnWidths[column] = w;
          applyWidths();
        };
        grip.onpointerup = () => { grip.onpointermove = null; };
      };
      grip.onclick = event => event.stopPropagation();
      th.append(grip);
    });
    const body = node("tbody");
    rows.forEach(row => {
      const tr = node("tr"); const cells = Array.isArray(row) ? row : row.cells;
      if (row.path) {
        tr.dataset.path = row.path;
        tr.tabIndex = 0;
        if (row.path === selected) tr.classList.add("selected");
        tr.setAttribute("aria-selected", row.path === selected ? "true" : "false");
        tr.onclick = () => onSelect(row.path);
        tr.onkeydown = e => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(row.path); }
          if (e.key === "ArrowDown" && tr.nextElementSibling) { e.preventDefault(); const next = tr.nextElementSibling; next.focus(); onSelect(next.dataset.path); }
          if (e.key === "ArrowUp" && tr.previousElementSibling) { e.preventDefault(); const previous = tr.previousElementSibling; previous.focus(); onSelect(previous.dataset.path); }
        };
      }
      cells.forEach((value, i) => {
        const td = node("td", value === null || value === undefined ? "—" : value);
        td.title = value == null ? "" : String(value);
        if (numeric[i]) td.classList.add("numeric");
        if (/status|quality/i.test(headers[i])) {
          const state = String(value).toLowerCase();
          if (state === "available") td.classList.add("status-available");
          else if (/warning|pending/.test(state)) td.classList.add("status-warning");
          else if (/failed|error/.test(state)) td.classList.add("status-error");
          else if (/withheld|unavailable|re-import/.test(state)) td.classList.add("status-unavailable");
        }
        if (row.pending_phase && i === 0) {
          const badge = node("span", " • Phase change pending", "pending-phase");
          badge.title = `Imported phase: ${row.imported_phase || "Unassigned"}. Pending phase: ${row.assigned_phase || "Unassigned"}. Re-import to apply.`;
          td.append(badge);
        }
        if (row.path && bridge.batchTooltip) {
          td.onmouseenter = () => bridge.batchTooltip(view === "phase" ? "phases" : view, row.path, columns[i], value => { td.title = value; });
        }
        tr.append(td);
      });
      body.append(tr);
    });
    table.append(body); return table;
  }
  function pager(total, start, change) {
    const box = node("div", undefined, "pager");
    if (total <= size) { box.hidden = true; return box; }
    box.setAttribute("aria-label", "Table pages");
    const prev = node("button", "Previous"), next = node("button", "Next");
    prev.disabled = start === 0; next.disabled = start + size >= total;
    prev.onclick = () => change(Math.max(0, start - size));
    next.onclick = () => change(start + size);
    box.append(prev, node("span", total ? `${start + 1}–${Math.min(start + size, total)} of ${total}` : "0 results"), next);
    return box;
  }
  function showBatch() {
    const seq = ++request;
    bridge.batch(view === "phase" ? "phases" : view, offset, size, raw => {
      if (seq !== request) return;
      const data = parse(raw), box = $("batch-table");
      if (!data.headers) return;
      if (offset >= data.total && offset) { offset = 0; showBatch(); return; }
      sortColumn = data.sort_column;
      descending = data.sort_descending;
      const previousSelection = selected;
      selected = data.selected || null;
      if (previousSelection !== selected) { choiceOffset = 0; showDetail(); }
      const batchData = {...data};
      delete batchData.selected;
      delete batchData.selected_position;
      const snapshot = JSON.stringify([view, offset, batchData, sortColumn, descending]);
      box.querySelectorAll("tr[data-path]").forEach(row => {
        row.classList.toggle("selected", row.dataset.path === selected);
        row.setAttribute("aria-selected", row.dataset.path === selected ? "true" : "false");
      });
      if (snapshot === batchSnapshot) return;
      batchSnapshot = snapshot;
      if (!data.batch_total) {
        const empty = node("div", undefined, "empty-state");
        empty.append(node("span", "Add Med-PC recordings to begin. "));
        const add = node("button", "Add files…");
        add.onclick = () => call("choose_files", {});
        empty.append(add); box.replaceChildren(empty);
        $("batch-count").textContent = "Showing 0 of 0 files.";
        return;
      }
      const scrollX = box.scrollLeft, scrollY = box.scrollTop;
      const focused = document.activeElement?.closest("tr")?.dataset.path;
      box.replaceChildren(table(data.headers, data.rows, col => {
        descending = sortColumn === col ? !descending : false; sortColumn = col; offset = 0;
        call("sort", {view, column: col, descending}, showBatch);
      }, path => {
        selected = path; choiceOffset = 0;
        document.querySelectorAll("#batch-table tr[data-path]").forEach(row => {
          row.classList.toggle("selected", row.dataset.path === path);
          row.setAttribute("aria-selected", row.dataset.path === path ? "true" : "false");
        });
        call("select", {path}, showDetail);
      }, data.columns, data.numeric), pager(data.total, offset, n => { offset = n; showBatch(); }));
      box.scrollLeft = scrollX; box.scrollTop = scrollY;
      if (focused) [...box.querySelectorAll("tr[data-path]")].find(row => row.dataset.path === focused)?.focus({preventScroll: true});
      $("batch-count").textContent = `Showing ${data.total} of ${data.batch_total ?? data.total} files. Import and export use the full batch.`;
    });
  }
  const tabs = ["Session details", "Session metrics", "Phase metrics", "Analysis metadata", "Decoded choices", "Warnings and checks", "Source text"];
  function showDetail() {
    const seq = ++detailRequest;
    bridge.detailSection(detailTab, choiceOffset, size, raw => {
      if (seq !== detailRequest) return;
      const data = parse(raw); if (!("content" in data)) return;
      document.querySelectorAll("#inspector-tabs [data-detail]").forEach(button => {
        button.classList.toggle("active", button.dataset.detail === detailTab);
      });
      const box = $("inspector-content");
      const snapshot = JSON.stringify([detailTab, choiceOffset, data]);
      if (snapshot === detailSnapshot) return;
      detailSnapshot = snapshot;
      const scroll = box.scrollTop, wasOpen = box.querySelector("details")?.open || false;
      box.replaceChildren();
      const summaryElement = $("inspector-summary");
      if (summaryElement) summaryElement.textContent = data.summary;
      else box.append(node("div", data.summary, "inspector-summary"));
      const content = data.content;
      if (detailTab === "Session metrics" || detailTab === "Phase metrics") {
        box.append(node("p", content.note));
        if (detailTab === "Session metrics") {
          const cards = node("div", undefined, "metric-cards");
          for (const row of content.table.rows.filter(row => ["Recorded choices", "Correct choices", "Incorrect choices", "Proportion correct", "Trials/min (Med-PC)"].includes(row[0]))) {
            const card = node("div", undefined, "metric-card");
            card.dataset.metric = row[0].toLowerCase().replace(/[^a-z]+/g, "-");
            card.append(node("span", row[0]), node("strong", row[1]));
            cards.append(card);
          }
          box.append(cards);
        }
        box.append(table(content.table.headers, content.table.rows, null, null, undefined, undefined, `inspector:${detailTab}`));
        const details = node("details"), summary = node("summary", "Diagnostics"), pre = node("pre", content.diagnostics);
        details.open = wasOpen; details.append(summary, pre); box.append(details);
      } else if (detailTab === "Decoded choices") {
        box.append(table(content.headers, content.rows, null, null, undefined, undefined, `inspector:${detailTab}`));
        box.append(pager(content.total, choiceOffset, n => { choiceOffset = n; showDetail(); }));
      } else {
        box.append(node("pre", content || "No information available."));
      }
      box.scrollTop = scroll;
    });
  }

  let initialized = false, timer, lastNativeTab, pendingSearch = null;
  function setup() {
    if (initialized) return; initialized = true;
    tabs.forEach(name => {
      const button = node("button", name); button.dataset.detail = name;
      button.onclick = () => { detailTab = name; choiceOffset = 0; showDetail(); };
      $("inspector-tabs").append(button);
    });
    document.querySelectorAll("[data-batch]").forEach(button => button.onclick = () => {
      view = button.dataset.batch; offset = 0; sortColumn = -1; clearTimeout(timer); pendingSearch = null; filterSnapshot = "";
      document.querySelectorAll("[data-batch]").forEach(b => b.classList.toggle("active", b === button));
      call("batch_view", {view}, () => { renderFilters(); showBatch(); showDetail(); });
    });
    document.querySelector('[data-batch="sessions"]').classList.add("active");
  }
  function renderFilters() {
    const box = $("batch-filters");
    const values = currentState.filter_values?.[view] || {};
    const old = {};
    for (const [key, value] of Object.entries(values)) old[key] = key === "search" ? value : JSON.stringify(value);
    box.replaceChildren();
    const input = node("input"); input.type = "search"; input.id = "batch-search"; input.dataset.filter = "search";
    input.setAttribute("aria-label", "Search batch recordings");
    input.placeholder = "Search file, subject, date, or warning…"; input.value = pendingSearch !== null ? pendingSearch : old.search || "";
    input.oninput = () => {
      pendingSearch = input.value;
      clearTimeout(timer);
      timer = setTimeout(() => { applyFilters(); pendingSearch = null; }, 180);
    };
    box.append(input);
    const fields = view === "sessions" ? ["program", "quality"] : ["phase", "status", "condition", "cohort", "inclusion", "layout"];
    for (const field of fields) {
      const select = node("select"); select.id = `batch-${field}`; select.dataset.filter = field;
      select.setAttribute("aria-label", field === "layout" ? "Phase results column layout" : "Filter by " + field);
      for (const item of currentState.filters?.[field] || []) {
        const option = node("option", item.label); option.value = JSON.stringify(item.value); select.append(option);
      }
      if (old[field] !== undefined && [...select.options].some(o => o.value === old[field])) select.value = old[field];
      select.onchange = applyFilters; box.append(select);
    }
    const reset = node("button", "Reset filters"); reset.onclick = () => {
      clearTimeout(timer); pendingSearch = null;
      box.querySelectorAll("input").forEach(el => el.value = "");
      box.querySelectorAll("select").forEach(el => el.selectedIndex = 0);
      applyFilters();
    }; box.append(reset);
  }
  function applyFilters() {
    const data = {view};
    $("batch-filters").querySelectorAll("input,select").forEach(el => {
      data[el.dataset.filter] = el.tagName === "SELECT" ? JSON.parse(el.value || "null") : el.value;
    });
    offset = 0; call("filter", data, showBatch);
  }
  window.Explorer = {refresh(b, state) {
    bridge = b; currentState = state; setup();
    const active = document.activeElement;
    if (state.inspector_tab && state.inspector_tab !== lastNativeTab) {
      lastNativeTab = state.inspector_tab;
      if (tabs.includes(lastNativeTab)) detailTab = lastNativeTab;
    }
    const filters = JSON.stringify([view, state.filters, state.filter_values?.[view]]);
    if (filters !== filterSnapshot && !$("batch-filters").contains(active)) { filterSnapshot = filters; renderFilters(); }
    if (state.batch_revision === undefined || state.batch_revision !== lastBatchRevision) {
      lastBatchRevision = state.batch_revision;
      showBatch();
    }
    if (state.detail_revision === undefined || state.detail_revision !== lastDetailRevision) {
      lastDetailRevision = state.detail_revision;
      showDetail();
    }
  }};
})();
