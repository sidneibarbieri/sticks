// "Your STIX bundle" panel: calls the same admission service as scripts/emulate.py --bundle.
(() => {
  const $ = (selector) => document.querySelector(selector);
  const form = $("#bundle-form");
  const campaignInput = $("#bundle-campaign");
  const fileInput = $("#bundle-file");
  const fileName = $("#bundle-file-name");
  const button = $("#bundle-button");
  const message = $("#bundle-message");
  const workspace = $("#bundle-workspace");
  const maximumBytes = 128 * 1024 * 1024;
  let lastResult = null;
  let generation = 0;

  const hideBundleResult = () => {
    generation += 1;
    workspace.hidden = true;
  };

  const updateReady = () => {
    const file = fileInput.files[0];
    fileName.textContent = file ? `${file.name} · ${(file.size / 1048576).toFixed(1)} MiB` : "No file selected (up to 128 MiB)";
    button.disabled = !file || !campaignInput.checkValidity();
  };

  const metric = (label, value) => {
    const node = document.createElement("div");
    node.className = "metric";
    const labelNode = document.createElement("span");
    labelNode.className = "metric-label";
    labelNode.textContent = label;
    const valueNode = document.createElement("strong");
    valueNode.className = "metric-value";
    valueNode.textContent = String(value);
    node.append(labelNode, valueNode);
    return node;
  };

  const row = (technique, outcome, template) => {
    const tr = document.createElement("tr");
    for (const [text, className] of [[technique, "mono"], [outcome, outcome === "admitted" ? "outcome-admitted" : "outcome-unresolved"], [template, "mono"]]) {
      const cell = document.createElement("td");
      cell.textContent = text;
      if (className) cell.className = className;
      tr.append(cell);
    }
    return tr;
  };

  const render = (result, bundleName) => {
    lastResult = result;
    $("#bundle-result-title").textContent = `${result.campaign_id} · admission`;
    $("#bundle-metrics").replaceChildren(
      metric("Steps in plan", result.plan_step_count),
      metric("Admitted", result.admitted_steps.length),
      metric("Unresolved", result.unresolved_technique_ids.length),
      metric("Causal certificate", result.causal_certificate_valid === null ? "n/a" : result.causal_certificate_valid ? "valid" : "invalid"),
    );
    const rows = result.admitted_steps.map((step) => row(step.technique_id, "admitted", step.template_id));
    for (const technique of result.unresolved_technique_ids) rows.push(row(technique, "unresolved", "no admissible realization in the catalog"));
    $("#bundle-steps").replaceChildren(...rows);
    $("#bundle-command").textContent = `python3 scripts/emulate.py ${result.campaign_id} --bundle ${bundleName} --json-output ${result.campaign_id}.admission.json`;
    $("#bundle-hash").textContent = `Bundle SHA-256 ${result.bundle_sha256}`;
    $("#empty-state").hidden = true;
    $("#result-workspace").hidden = true;
    workspace.hidden = false;
  };

  campaignInput.addEventListener("input", () => { hideBundleResult(); updateReady(); });
  fileInput.addEventListener("change", () => { hideBundleResult(); updateReady(); message.textContent = ""; });
  $("#enumerate-button").addEventListener("click", hideBundleResult, true);
  $("#campaign-select").addEventListener("change", hideBundleResult, true);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = fileInput.files[0];
    if (!file) return;
    if (file.size > maximumBytes) {
      message.classList.add("is-error");
      message.textContent = "Rejected: the bundle exceeds 128 MiB.";
      return;
    }
    hideBundleResult();
    const revision = generation;
    button.disabled = true;
    message.classList.remove("is-error");
    message.textContent = `Admitting ${campaignInput.value} from ${file.name}…`;
    try {
      const response = await fetch(`/api/bundle-admission?campaign=${encodeURIComponent(campaignInput.value)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: file,
      });
      const payload = await response.json();
      if (revision !== generation) return;
      if (!response.ok) throw new Error(payload.detail || `HTTP ${response.status}`);
      render(payload, file.name);
      message.textContent = `Admitted ${payload.admitted_steps.length} of ${payload.plan_step_count} steps; ${payload.unresolved_technique_ids.length} unresolved. Operational status: not_run.`;
    } catch (error) {
      if (revision === generation) {
        message.classList.add("is-error");
        message.textContent = `Admission rejected: ${error.message}`;
      }
    } finally {
      updateReady();
    }
  });

  $("#bundle-download").addEventListener("click", () => {
    if (!lastResult) return;
    const blob = new Blob([`${JSON.stringify(lastResult, null, 2)}\n`], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${lastResult.campaign_id}.admission.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  });

  if (window.location.protocol === "file:") {
    form.querySelectorAll("input, button").forEach((control) => { control.disabled = true; });
    message.textContent = "Start the local workbench server to admit a bundle.";
    return;
  }
  updateReady();
})();
