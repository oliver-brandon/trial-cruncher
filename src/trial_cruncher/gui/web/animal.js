(() => {
  "use strict";
  const make = (tag, text) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const request = (method, ...args) => new Promise((resolve, reject) =>
    window.trialBridge[method](...args, raw => {
      try {
        const data = JSON.parse(raw);
        if (method !== "animalConfig" && data.error) throw new Error(data.error);
        resolve(data);
      } catch (error) { reject(error); }
    }));

  async function open() {
    if (document.getElementById("animal-dialog")) return;
    const initial = await request("animalConfig");
    if (document.getElementById("animal-dialog")) return;
    const dialog = make("dialog"); dialog.id = "animal-dialog";
    dialog.setAttribute("aria-label", "Animal analysis");
    const title = make("h2", "Animal analysis");
    const note = make("p", "Include one recording per animal, condition and phase in session metadata.");
    const form = make("div"); form.className = "animal-form";
    function select(label, values, selected) {
      const wrapper = make("label", label), input = make("select");
      input.add(new Option("Choose…", ""));
      values.forEach(value => input.add(new Option(value, value)));
      input.value = selected || "";
      wrapper.append(input); form.append(wrapper); return input;
    }
    function checklist(label, values, selected) {
      const box = make("fieldset"), legend = make("legend", label);
      box.append(legend);
      values.forEach(value => {
        const row = make("label"), check = make("input");
        check.type = "checkbox"; check.value = value;
        check.checked = (selected || []).includes(value);
        row.append(check, document.createTextNode(value)); box.append(row);
      });
      form.append(box);
      return () => [...box.querySelectorAll("input:checked")].map(input => input.value);
    }
    const plan = initial.plan || {};
    const design = select("Design", ["between-subjects", "within-subjects"], plan.design);
    const conditions = checklist("Conditions", initial.conditions, plan.conditions);
    const phases = checklist("Phases", initial.phases, plan.phases);
    if (!initial.conditions.length) {
      note.textContent += " Assign a condition in Session metadata.";
    }
    if (!initial.phases.length) {
      note.textContent += " Assign phases and import the recordings to load phase results.";
    }
    const shortcut = make("button", "Edit session metadata…");
    shortcut.onclick = () => { dialog.close(); document.dispatchEvent(new Event("animal-edit-metadata")); };
    const message = make("p"); message.setAttribute("role", "alert");
    const controls = make("footer"), cancel = make("button", "Close");
    const disable = make("button", "Disable analysis"), apply = make("button", "Apply and preview");
    apply.className = "primary";
    controls.append(cancel, disable, apply);
    const preview = make("section"); preview.className = "animal-preview";
    const sorting = make("details"); sorting.className = "animal-sorting";
    const sortLabel = make("summary", "Sort rules");
    const sortRules = make("div");
    const addSort = make("button", "Add sort rule");
    const resetSort = make("button", "Reset sorting");
    sorting.append(sortLabel, sortRules, addSort, resetSort);
    const tabs = make("nav"), scroller = make("div"); scroller.className = "animal-scroll";
    const table = make("table"); scroller.append(table);
    const paging = make("footer"), count = make("span");
    const previous = make("button", "Previous"), next = make("button", "Next");
    paging.append(count, previous, next); preview.append(tabs, sorting, scroller, paging);
    preview.hidden = true;
    const sheets = [["pooled_metrics.csv", "Pooled metrics"], ["condition_comparison.csv", "Condition comparison"],
      ["animal_metrics.csv", "Animal metrics"], ["analysis_audit.csv", "Analysis audit"]];
    let selected = sheets[0][0], offset = 0, timer, drawGeneration = 0;
    let currentRules = [], currentHeaders = [];
    async function saveSort(rules) {
      const tableName = selected;
      // Accept the next edit only once the controls show the saved rule set.
      preview.inert = true;
      try {
        if (rules === null) await request("animalResetSort", tableName);
        else await request("animalSort", tableName, JSON.stringify(rules));
        offset = 0;
        await draw();
      } catch (error) {
        message.textContent = error.message;
      } finally {
        preview.inert = false;
      }
    }
    function moveRule(index, step) {
      const reordered = currentRules.slice();
      const [rule] = reordered.splice(index, 1);
      reordered.splice(index + step, 0, rule);
      saveSort(reordered);
    }
    function drawRules() {
      sortRules.replaceChildren();
      const selectedKeys = new Set(currentRules.map(rule => rule.column));
      currentRules.forEach((rule, i) => {
        const row = make("div");
        row.append(make("span", String(i + 1) + "."));
        const select = make("select");
        select.setAttribute("aria-label", "Sort column");
        for (const [key, label] of currentHeaders) {
          if (!selectedKeys.has(key) || key === rule.column) select.add(new Option(label, key));
        }
        if (!currentHeaders.some(([key]) => key === rule.column)) {
          select.add(new Option(rule.column + " (outside current scope)", rule.column));
        }
        select.value = rule.column;
        const direction = make("select");
        direction.setAttribute("aria-label", "Sort direction");
        direction.add(new Option("Ascending", "asc"));
        direction.add(new Option("Descending", "desc"));
        direction.value = rule.descending ? "desc" : "asc";
        function changeRule() {
          const updated = currentRules.slice();
          updated[i] = {column: select.value, descending: direction.value === "desc"};
          saveSort(updated);
        }
        select.onchange = changeRule;
        direction.onchange = changeRule;
        const up = make("button", "↑"), down = make("button", "↓");
        up.title = "Move rule up"; down.title = "Move rule down";
        up.disabled = i === 0; down.disabled = i === currentRules.length - 1;
        up.onclick = () => moveRule(i, -1);
        down.onclick = () => moveRule(i, 1);
        const remove = make("button", "Remove");
        remove.onclick = () => saveSort(currentRules.filter((_, index) => index !== i));
        row.append(select, direction, up, down, remove);
        sortRules.append(row);
      });
      addSort.disabled = currentHeaders.every(([key]) => selectedKeys.has(key));
    }
    addSort.onclick = () => {
      const candidate = currentHeaders.find(([key]) => !currentRules.some(rule => rule.column === key));
      if (candidate) saveSort([...currentRules, {column: candidate[0], descending: false}]);
    };
    resetSort.onclick = () => saveSort(null);
    async function draw() {
      const generation = ++drawGeneration;
      const pageOffset = offset;
      try {
        const data = await request("animalPage", selected, pageOffset, 100);
        if (!dialog.open || generation !== drawGeneration) return;
        table.replaceChildren();
        const head = table.createTHead().insertRow();
        currentRules = data.sort_rules;
        currentHeaders = data.headers.map((key, i) => [key, data.display_headers[i]]);
        drawRules();
        sorting.inert = false;
        table.inert = false;
        data.display_headers.forEach((label, i) => {
          const th = make("th"), button = make("button", label);
          const rule = currentRules.find(item => item.column === data.headers[i]);
          if (rule) {
            const priority = currentRules.indexOf(rule) + 1;
            button.dataset.rank = (rule.descending ? "▼" : "▲") + priority;
            button.setAttribute("aria-label", label + ", priority " + priority +
              (rule.descending ? ", descending" : ", ascending"));
            if (priority === 1) th.setAttribute("aria-sort", rule.descending ? "descending" : "ascending");
          }
          button.title = "Sort by this column. Use Sort rules to set tie-breakers.";
          button.onclick = () => saveSort([{column: data.headers[i], descending: rule ? !rule.descending : false}]);
          th.append(button); head.append(th);
        });
        const body = table.createTBody();
        data.rows.forEach((row, rowIndex) => {
          const tr = body.insertRow();
          row.forEach((value, columnIndex) => {
            const cell = tr.insertCell();
            const evidence = data.cell_details[rowIndex][columnIndex];
            if (evidence) {
              const details = make("details");
              details.append(make("summary", value), make("div", evidence));
              cell.append(details);
            } else {
              cell.textContent = value;
            }
          });
        });
        count.textContent = data.total ? `${offset + 1}–${Math.min(offset + 100, data.total)} of ${data.total}` : "No rows";
        previous.disabled = offset === 0; next.disabled = offset + 100 >= data.total;
        [...tabs.children].forEach((button, i) => button.classList.toggle("active", sheets[i][0] === selected));
      } catch (error) { if (dialog.open && generation === drawGeneration) message.textContent = error.message; }
    }
    sheets.forEach(([key, label]) => {
      const button = make("button", label); button.onclick = () => {
        selected = key;
        offset = 0;
        sorting.inert = true;
        table.inert = true;
        draw();
      };
      tabs.append(button);
    });
    previous.onclick = () => { offset = Math.max(0, offset - 100); draw(); };
    next.onclick = () => { offset += 100; draw(); };
    function setWorking(working) {
      apply.disabled = working;
      disable.disabled = working;
      shortcut.disabled = working;
      for (const control of form.querySelectorAll("select,input")) control.disabled = working;
    }
    async function wait() {
      try {
        const state = await request("animalConfig");
        if (!dialog.open) return;
        if (state.busy) {
          timer = setTimeout(wait, 150);
          return;
        }
        setWorking(false);
        if (state.error) message.textContent = state.error;
        else if (state.ready) {
          message.textContent = `${state.selected_count} of ${state.audit_count} recordings selected for this analysis.`;
          if (state.selected_count < state.audit_count) {
            message.textContent += " Open Analysis audit for recording values and selection reasons.";
          }
          preview.hidden = false;
          await draw();
        }
      } catch (error) {
        setWorking(false);
        message.textContent = error.message;
      }
    }
    async function submit(value) {
      setWorking(true);
      ++drawGeneration;
      preview.hidden = true;
      try {
        await request("animalApply", JSON.stringify(value));
        if (value === null) { dialog.close(); return; }
        message.textContent = "Building animal analysis…";
        await wait();
      } catch (error) {
        setWorking(false);
        message.textContent = error.message;
      }
    }
    apply.onclick = () => submit({design: design.value, conditions: conditions(), phases: phases()});
    disable.onclick = () => submit(null);
    cancel.onclick = () => dialog.close();
    dialog.addEventListener("close", () => {
      clearTimeout(timer);
      ++drawGeneration;
      request("animalDismiss").catch(() => {});
      dialog.remove();
    }, {once: true});
    dialog.append(title, note, form, shortcut, message, controls, preview);
    document.body.append(dialog); dialog.showModal();
    if (initial.error) message.textContent = initial.error;
    form.onchange = () => {
      if (!preview.hidden) {
        preview.hidden = true;
        message.textContent = "Apply and preview to use the edited configuration.";
      }
    };
    if (initial.ready) { preview.hidden = false; await draw(); }
    else if (initial.busy) { setWorking(true); await wait(); }
  }
  window.animal = {open};
})();
