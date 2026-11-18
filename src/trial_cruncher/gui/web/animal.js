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
    const cohort = select("Cohort", initial.cohorts, plan.cohort);
    const design = select("Design", ["between-subjects", "within-subjects"], plan.design);
    const conditions = checklist("Conditions", initial.conditions, plan.conditions);
    const phases = checklist("Phases", initial.phases, plan.phases);
    if (!initial.cohorts.length || !initial.conditions.length) {
      note.textContent += " Assign a cohort and condition in Session metadata.";
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
    const tabs = make("nav"), scroller = make("div"); scroller.className = "animal-scroll";
    const table = make("table"); scroller.append(table);
    const paging = make("footer"), count = make("span");
    const previous = make("button", "Previous"), next = make("button", "Next");
    paging.append(count, previous, next); preview.append(tabs, scroller, paging);
    preview.hidden = true;
    const sheets = [["pooled_metrics.csv", "Pooled metrics"], ["condition_comparison.csv", "Condition comparison"],
      ["animal_metrics.csv", "Animal metrics"], ["analysis_audit.csv", "Analysis audit"]];
    let selected = sheets[0][0], offset = 0, timer, drawGeneration = 0;
    async function draw() {
      const generation = ++drawGeneration;
      const pageOffset = offset;
      try {
        const data = await request("animalPage", selected, pageOffset, 100);
        if (!dialog.open || generation !== drawGeneration) return;
        table.replaceChildren();
        const head = table.createTHead().insertRow();
        data.headers.forEach(value => head.append(make("th", value.replaceAll("_", " "))));
        const body = table.createTBody();
        data.rows.forEach(row => { const tr = body.insertRow(); row.forEach(value => tr.append(make("td", value))); });
        count.textContent = data.total ? `${offset + 1}–${Math.min(offset + 100, data.total)} of ${data.total}` : "No rows";
        previous.disabled = offset === 0; next.disabled = offset + 100 >= data.total;
        [...tabs.children].forEach((button, i) => button.classList.toggle("active", sheets[i][0] === selected));
      } catch (error) { if (dialog.open && generation === drawGeneration) message.textContent = error.message; }
    }
    sheets.forEach(([key, label]) => {
      const button = make("button", label); button.onclick = () => { selected = key; offset = 0; draw(); };
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
          message.textContent = "Analysis ready. Exports include these tables.";
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
    apply.onclick = () => submit({cohort: cohort.value, design: design.value, conditions: conditions(), phases: phases()});
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
