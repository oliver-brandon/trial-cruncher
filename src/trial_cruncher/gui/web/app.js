/* Desktop workflow and Qt WebChannel integration. */
(() => {
  "use strict";

  const actions = {
    "add-files": "choose_files", "add-folder": "choose_folder",
    "animal-analysis": "animal_analysis", "export-csv": "export_csv",
    "detailed-excel": "export_detailed_excel", "detailed-csv": "export_detailed_csv",
    "export-excel": "export_excel", "open-project": "open_project",
    "save-project": "save_project", "save-project-as": "save_project_as",
    "check-sources": "check_sources", import: "import", cancel: "cancel", clear: "clear"
  };
  const $ = (selector) => document.querySelector(selector);
  const mode = $("#view-mode");
  const workspace = $("#workspace");
  let bridge;
  let hydrated = false;
  let splitTimer;
  let currentPage = "import";
  let refreshAgain = false;
  let preferencesLoaded = false;
  let renderedMessages = -1;
  let messageRequest = 0;
  let refreshPending = false;

  function parse(value) {
    try { return JSON.parse(value); }
    catch (_) { return {error: "The application returned an invalid response."}; }
  }
  function report(message) {
    $("#status").textContent = message;
  }
  function call(name, payload = {}) {
    if (!bridge) return Promise.reject(new Error("The application is still starting."));
    return new Promise((resolve, reject) => {
      bridge.action(name, JSON.stringify(payload), (raw) => {
        const response = parse(raw);
        if (response.error) { report(response.error); reject(new Error(response.error)); }
        else resolve(response);
      });
    });
  }
  function page(name) {
    currentPage = name;
    document.querySelectorAll("[data-workflow]").forEach((button) => {
      const active = button.dataset.workflow === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-current", active ? "page" : "false");
    });
    document.querySelectorAll("[data-workflow-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.workflowPanel !== name;
    });
    if (name !== "import") $("#file-options").hidden = true;
  }
  function layout(save = true) {
    const value = mode.value;
    $("#batch-panel").hidden = value === "Detail only";
    $("#detail-panel").hidden = value === "Batch only";
    $("#splitter").hidden = value !== "Split view";
    workspace.dataset.layout = value;
    if (save && bridge) call("set_preferences", {mode: {"Split view": "split", "Batch only": "batch", "Detail only": "detail"}[value]}).catch((error) => report(error.message));
  }
  async function showMessages(revision) {
    const panel = $("#messages-panel"), list = $("#messages-list");
    if (panel.hidden || revision === renderedMessages) return;
    renderedMessages = revision;
    const request = ++messageRequest;
    const fragment = document.createDocumentFragment();
    let offset = 0;
    while (true) {
      const page = await new Promise(resolve => bridge.messages(offset, 250, raw => resolve(parse(raw))));
      if (request !== messageRequest || panel.hidden) return;
      if (!page.rows) { report(page.error); return; }
      for (const text of page.rows) {
        const item = document.createElement("li");
        item.textContent = text;
        fragment.append(item);
      }
      offset += page.rows.length;
      if (!page.rows.length || offset >= page.total) break;
    }
    list.replaceChildren(fragment);
  }
  function update(next) {
    hydrated = true;
    document.querySelectorAll("[data-workflow]").forEach((button) => { button.disabled = false; });
    ["messages", "edit-files", "export-results"].forEach((name) => {
      document.querySelector(`[data-action="${name}"]`).disabled = false;
    });
    report(next.status || "Ready");
    const status = (next.status || "").toLowerCase().replace(/\b0 (failed|with warnings)\b/g, "");
    const dot = document.querySelector(".status-dot");
    dot.className = "status-dot";
    if (/failed|error/.test(status)) dot.classList.add("error");
    else if (/warning|cancelled|missing|changed/.test(status)) dot.classList.add("warning");
    else if (/complete|saved/.test(status)) dot.classList.add("success");
    $("#project-label").textContent = next.project || "Project: unsaved";
    $("#export-status").textContent = next.export_status || "";
    const progress = $("#progress");
    progress.hidden = !next.progress?.visible;
    if (next.progress?.maximum > 0) {
      progress.max = next.progress.maximum;
      progress.value = next.progress.value;
    } else progress.removeAttribute("value");
    $("#messages-button").textContent = `Messages (${next.message_count})`;
    showMessages(next.message_revision);
    if (document.activeElement !== $("#extensions")) $("#extensions").value = next.extensions || "";
    $("#recursive").checked = !!next.recursive;
    $("#extensions").disabled = !!next.busy;
    $("#recursive").disabled = !!next.busy;
    document.querySelector('[data-action="file-options"]').disabled = !!next.busy;
    document.querySelectorAll("[data-action]").forEach((button) => {
      const action = button.dataset.action;
      if (["cancel", "messages", "file-options", "edit-files", "export-results"].includes(action)) return;
      const key = action === "phase" ? "assign_phases" : action === "metadata" ? "assign_metadata" : actions[action];
      if (key) button.disabled = next.enabled?.[key] === false;
    });
    const cancel = document.querySelector('[data-action="cancel"]');
    cancel.hidden = !next.can_cancel;
    cancel.disabled = next.enabled?.cancel === false;
    if (next.workflow && next.workflow !== currentPage) page(next.workflow);
    if (!preferencesLoaded && next.ui_preferences) {
      preferencesLoaded = true;
      mode.value = {"split": "Split view", "batch": "Batch only", "detail": "Detail only"}[next.ui_preferences.mode] || "Split view";
      if (!mode.value) mode.value = "Split view";
      const ratio = Number(next.ui_preferences.split);
      workspace.style.setProperty("--split", `${(Number.isFinite(ratio) ? Math.max(.2, Math.min(.8, ratio)) : .34) * 100}%`);
      layout(false);
    }
    if (window.Explorer) window.Explorer.refresh(bridge, next);
    if (!window.trialReady) {
      window.trialReady = true;
      document.dispatchEvent(new Event("trial-ready"));
    }
  }
  function refresh() {
    if (refreshPending) { refreshAgain = true; return; }
    refreshPending = true;
    setTimeout(() => {
      bridge.state((raw) => { refreshPending = false; const value = parse(raw); if (value.error) report(value.error); else update(value); if (refreshAgain) { refreshAgain = false; refresh(); } });
    }, 30);
  }
  document.querySelectorAll("[data-action], [data-workflow]").forEach((button) => { button.disabled = true; });
  $("#extensions").disabled = true;
  $("#recursive").disabled = true;
  document.querySelectorAll("[data-workflow]").forEach((button) =>
    button.addEventListener("click", () => { page(button.dataset.workflow); call("set_workflow", {workflow: button.dataset.workflow}).catch((error) => report(error.message)); }));
  document.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", async () => {
    const action = button.dataset.action;
    if (!hydrated) return;
    try {
      if (action === "file-options") $("#file-options").hidden = !$("#file-options").hidden;
      else if (action === "messages") {
        $("#messages-panel").hidden = !$("#messages-panel").hidden;
        renderedMessages = -1;
        messageRequest++;
      }
      else if (action === "edit-files") { page("import"); await call("set_workflow", {workflow: "import"}); }
      else if (action === "export-results") { page("export"); await call("set_workflow", {workflow: "export"}); }
      else if (action === "phase" || action === "metadata") await window.TrialAssignments.open(action, bridge);
      else if (action === "animal-analysis") await window.animal.open();
      else if (actions[action]) await call(actions[action]);
      refresh();
    } catch (error) { report(error.message); }
  }));
  document.addEventListener("animal-edit-metadata", () => window.TrialAssignments.open("metadata", bridge).catch((error) => report(error.message)));
  async function options() {
    try { await call("options", {extensions: $("#extensions").value, recursive: $("#recursive").checked}); }
    catch (_) { refresh(); }
  }
  $("#extensions").addEventListener("change", options);
  $("#recursive").addEventListener("change", options);
  $("#inspect-recording").addEventListener("click", () => {
    mode.value = "Split view";
    layout();
    window.Explorer?.inspect();
    $("#inspector-tabs button.active")?.focus();
  });
  mode.addEventListener("change", () => layout());
  if (!mode.value) mode.value = "Split view";
  layout();
  page("import");

  const splitter = $("#splitter");
  function resize(y) {
    const bounds = workspace.getBoundingClientRect();
    const ratio = Math.max(.2, Math.min(.8, (y - bounds.top) / bounds.height));
    workspace.style.setProperty("--split", `${ratio * 100}%`);
    clearTimeout(splitTimer);
    splitTimer = setTimeout(() => {
      if (bridge) call("set_preferences", {split: ratio}).catch((error) => report(error.message));
    }, 300);
  }
  splitter.addEventListener("pointerdown", (event) => { splitter.setPointerCapture(event.pointerId); resize(event.clientY); });
  splitter.addEventListener("pointermove", (event) => { if (splitter.hasPointerCapture(event.pointerId)) resize(event.clientY); });
  splitter.addEventListener("keydown", (event) => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    resize(splitter.getBoundingClientRect().top + (event.key === "ArrowUp" ? -20 : 20));
  });

  if (typeof QWebChannel === "undefined" || typeof qt === "undefined") {
    report("Could not connect to the desktop application.");
    return;
  }
  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.trialBridge;
    window.trialBridge = bridge;
    bridge.changed.connect(refresh);
    refresh();
  });
})();
