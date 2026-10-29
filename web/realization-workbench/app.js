"use strict";

const elements = {
  campaignSelect: document.querySelector("#campaign-select"),
  readyOnly: document.querySelector("#ready-only"),
  corpusStatus: document.querySelector("#campaign-corpus-status"),
  stepCount: document.querySelector("#campaign-step-count"),
  bindingStatus: document.querySelector("#campaign-binding-status"),
  semanticStatus: document.querySelector("#campaign-semantic-status"),
  maximumRealizations: document.querySelector("#maximum-realizations"),
  maximumSearchStates: document.querySelector("#maximum-search-states"),
  maximumCandidates: document.querySelector("#maximum-candidates"),
  desiredProcedureAssignments: document.querySelector("#desired-procedure-assignments"),
  desiredContracts: document.querySelector("#desired-contracts"),
  maximumTargets: document.querySelector("#maximum-targets"),
  enumerateButton: document.querySelector("#enumerate-button"),
  controlMessage: document.querySelector("#control-message"),
  inventoryLine: document.querySelector("#inventory-line"),
  emptyState: document.querySelector("#empty-state"),
  resultWorkspace: document.querySelector("#result-workspace"),
  resultCampaignId: document.querySelector("#result-campaign-id"),
  resultCampaignName: document.querySelector("#result-campaign-name"),
  resultStatus: document.querySelector("#result-status"),
  downloadButton: document.querySelector("#download-button"),
  metricStrip: document.querySelector("#metric-strip"),
  searchDetails: document.querySelector("#search-details"),
  blockerList: document.querySelector("#blocker-list"),
  limitationList: document.querySelector("#limitation-list"),
  stepsBody: document.querySelector("#steps-body"),
  realizationsBody: document.querySelector("#realizations-body"),
  queueProcedureDeficit: document.querySelector("#queue-procedure-deficit"),
  queueBehaviorDeficit: document.querySelector("#queue-behavior-deficit"),
  queueSelected: document.querySelector("#queue-selected"),
  queueDeferred: document.querySelector("#queue-deferred"),
  queueBody: document.querySelector("#queue-body"),
  jsonOutput: document.querySelector("#json-output"),
  tabs: Array.from(document.querySelectorAll(".tab")),
  panels: Array.from(document.querySelectorAll(".tab-panel")),
};

const state = {
  inventory: null,
  result: null,
  activeCampaignId: null,
  requestGeneration: 0,
};

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json();
  if (!response.ok) {
    const detail =
      typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    throw new Error(detail || `Request failed with status ${response.status}`);
  }
  return payload;
}

function selectedCampaign() {
  if (!state.inventory) {
    return null;
  }
  return (
    state.inventory.campaigns.find(
      (campaign) => campaign.campaign_id === elements.campaignSelect.value,
    ) || null
  );
}

function renderCampaignOptions() {
  const previousValue = elements.campaignSelect.value;
  const campaigns = state.inventory.campaigns.filter(
    (campaign) => !elements.readyOnly.checked || campaign.enumeration_ready,
  );
  elements.campaignSelect.replaceChildren();
  for (const campaign of campaigns) {
    const option = document.createElement("option");
    option.value = campaign.campaign_id;
    const readiness = campaign.enumeration_ready ? "ready" : "unavailable";
    option.textContent = `${campaign.campaign_id} - ${campaign.campaign_name} (${readiness})`;
    elements.campaignSelect.append(option);
  }
  const previousStillExists = campaigns.some(
    (campaign) => campaign.campaign_id === previousValue,
  );
  if (previousStillExists) {
    elements.campaignSelect.value = previousValue;
  }
  elements.campaignSelect.disabled = campaigns.length === 0;
  renderCampaignMeta();
}

function clearResult() {
  state.result = null;
  elements.resultWorkspace.hidden = true;
  elements.emptyState.hidden = false;
}

function renderCampaignMeta() {
  const campaign = selectedCampaign();
  const campaignId = campaign ? campaign.campaign_id : null;
  if (state.activeCampaignId !== campaignId) {
    state.activeCampaignId = campaignId;
    state.requestGeneration += 1;
    clearResult();
    elements.enumerateButton.textContent = "Enumerate realizations";
  }
  if (!campaign) {
    elements.corpusStatus.textContent = "Unavailable";
    elements.stepCount.textContent = "-";
    elements.bindingStatus.textContent = "-";
    elements.semanticStatus.textContent = "-";
    elements.enumerateButton.disabled = true;
    return;
  }
  elements.corpusStatus.textContent = campaign.corpus_status;
  elements.stepCount.textContent = campaign.step_count ?? "-";
  elements.bindingStatus.textContent = campaign.enumeration_ready ? "available" : "absent";
  elements.semanticStatus.textContent = campaign.semantic_fact_status.replaceAll("_", " ");
  elements.enumerateButton.disabled = !campaign.enumeration_ready;
  elements.controlMessage.textContent = campaign.enumeration_ready
    ? ""
    : campaign.availability_reason;
}

function fieldValidationError(input, message) {
  input.setAttribute("aria-invalid", "true");
  input.setAttribute("aria-describedby", "control-message");
  input.focus();
  return new Error(message);
}

function clearFieldErrors() {
  const boundInputs = [
    elements.maximumRealizations, elements.maximumSearchStates,
    elements.maximumCandidates, elements.desiredProcedureAssignments,
    elements.desiredContracts, elements.maximumTargets,
  ];
  for (const input of boundInputs) {
    input.removeAttribute("aria-invalid");
    input.removeAttribute("aria-describedby");
  }
}

function numberValue(input) {
  const label = input.previousElementSibling.textContent;
  const value = Number(input.value);
  if (input.value.trim() === "" || !Number.isSafeInteger(value)) {
    throw fieldValidationError(input, `${label} must be an integer`);
  }
  const minimum = Number(input.min);
  const maximum = Number(input.max);
  if (value < minimum || value > maximum) {
    throw fieldValidationError(input, `${label} must be between ${minimum} and ${maximum}`);
  }
  return value;
}

function requestPayload() {
  const campaign = selectedCampaign();
  if (!campaign) {
    throw new Error("Select a campaign");
  }
  return {
    campaign_id: campaign.campaign_id,
    maximum_realizations: numberValue(elements.maximumRealizations),
    maximum_search_states: numberValue(elements.maximumSearchStates),
    maximum_candidates_per_step: numberValue(elements.maximumCandidates),
    desired_procedure_assignments_per_step: numberValue(elements.desiredProcedureAssignments),
    desired_behavior_contracts_per_step: numberValue(elements.desiredContracts),
    maximum_generation_targets: numberValue(elements.maximumTargets),
  };
}

function appendMetric(label, value) {
  const metric = document.createElement("div");
  metric.className = "metric";
  const labelNode = document.createElement("span");
  labelNode.className = "metric-label";
  labelNode.textContent = label;
  const valueNode = document.createElement("strong");
  valueNode.className = "metric-value";
  valueNode.textContent = String(value);
  metric.append(labelNode, valueNode);
  elements.metricStrip.append(metric);
}

function renderMetrics(result) {
  elements.metricStrip.replaceChildren();
  appendMetric("Complete realizations", result.realization_count);
  appendMetric("Procedure assignments", result.procedure_assignment_variant_count);
  appendMetric("Behavior contracts", result.behavior_contract_variant_count);
  appendMetric("Causal orders", result.ordering_variant_count);
  appendMetric("Causal structures", result.causal_structure_variant_count);
  appendMetric("Schedule graphs", result.graph_variant_count);
  appendMetric("Search states", result.search_states_explored);
}

function appendDetail(label, value) {
  const row = document.createElement("div");
  const term = document.createElement("dt");
  term.textContent = label;
  const description = document.createElement("dd");
  description.textContent = String(value);
  row.append(term, description);
  elements.searchDetails.append(row);
}

function appendPlainRow(parent, label, value = null) {
  const row = document.createElement("div");
  row.className = "plain-row";
  const text = document.createElement("span");
  text.textContent = label;
  row.append(text);
  if (value !== null) {
    const count = document.createElement("strong");
    count.textContent = String(value);
    row.append(count);
  }
  parent.append(row);
}

function renderSummary(result) {
  elements.searchDetails.replaceChildren();
  appendDetail("Enumeration", result.enumeration_status);
  appendDetail("Search exhausted", result.search_exhausted);
  appendDetail("Truncation", result.truncation_reason || "none");
  appendDetail("Source steps", result.source_step_count);
  appendDetail("Maximum realized steps", result.maximal_realized_steps);
  appendDetail("Dead ends", result.dead_end_count);
  appendDetail("Result SHA-256", result.content_sha256);

  elements.blockerList.replaceChildren();
  if (result.blocker_counts.length === 0) {
    appendPlainRow(elements.blockerList, "No terminal blockers recorded");
  } else {
    for (const blocker of result.blocker_counts) {
      appendPlainRow(elements.blockerList, blocker.code, blocker.count);
    }
  }

  elements.limitationList.replaceChildren();
  for (const limitation of result.source_limitations) {
    appendPlainRow(elements.limitationList, limitation);
  }
  if (result.source_limitations.length === 0) {
    appendPlainRow(elements.limitationList, "No source limitation string recorded");
  }
}

function appendCell(row, value) {
  const cell = document.createElement("td");
  cell.textContent = String(value);
  row.append(cell);
}

function renderSteps(result) {
  elements.stepsBody.replaceChildren();
  for (const coverage of result.step_realization_coverage) {
    const row = document.createElement("tr");
    appendCell(row, coverage.source_step_index + 1);
    appendCell(row, coverage.technique_id);
    appendCell(row, coverage.candidate_count);
    appendCell(row, coverage.realized_procedure_assignment_count);
    appendCell(row, coverage.realized_behavior_contract_count);
    appendCell(row, coverage.realized_sequence_positions.join(", ") || "-");
    elements.stepsBody.append(row);
  }
}

function renderRealizations(result) {
  elements.realizationsBody.replaceChildren();
  for (const realization of result.realizations) {
    const row = document.createElement("tr");
    const templates = realization.plan.steps.map((step) => step.template_id).join(" -> ");
    const sourceOrder = realization.source_step_order.map((index) => index + 1).join(" -> ");
    appendCell(row, realization.rank);
    appendCell(row, realization.minimum_fidelity_ceiling);
    appendCell(row, realization.total_assumption_count);
    appendCell(row, sourceOrder);
    appendCell(row, templates);
    appendCell(row, realization.graph.edges.length);
    elements.realizationsBody.append(row);
  }
}

function renderQueue(queue) {
  elements.queueProcedureDeficit.textContent = String(
    queue.total_procedure_assignment_deficit,
  );
  elements.queueBehaviorDeficit.textContent = String(queue.total_behavior_contract_deficit);
  elements.queueSelected.textContent = String(queue.selected_target_count);
  elements.queueDeferred.textContent = String(
    queue.unselected_procedure_assignment_deficit,
  );
  elements.queueBody.replaceChildren();
  for (const target of queue.targets) {
    const context = target.context;
    const row = document.createElement("tr");
    appendCell(row, target.target_id || target.technique_id);
    appendCell(row, target.technique_id);
    appendCell(row, context ? context.execution_domain : "-");
    appendCell(
      row,
      context ? `${context.available_binding_kinds.length} available` : "-",
    );
    appendCell(row, context ? context.admissible_required_facts.length : 0);
    appendCell(row, context ? context.admissible_produced_facts.length : 0);
    elements.queueBody.append(row);
  }
}

function renderResult(response) {
  const result = response.result;
  state.result = response;
  elements.emptyState.hidden = true;
  elements.resultWorkspace.hidden = false;
  elements.resultCampaignId.textContent = response.campaign.campaign_id;
  elements.resultCampaignName.textContent = response.campaign.campaign_name;
  elements.resultStatus.textContent = result.operational_status;
  renderMetrics(result);
  renderSummary(result);
  renderSteps(result);
  renderRealizations(result);
  renderQueue(response.generation_queue);
  elements.jsonOutput.textContent = JSON.stringify(response, null, 2);
}

async function enumerateCampaign() {
  const requestGeneration = ++state.requestGeneration;
  clearResult();
  clearFieldErrors();
  elements.controlMessage.textContent = "";
  elements.enumerateButton.disabled = true;
  elements.enumerateButton.textContent = "Enumerating...";
  try {
    const response = await fetchJson("/api/enumerate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload()),
    });
    if (requestGeneration === state.requestGeneration) {
      renderResult(response);
    }
  } catch (error) {
    if (requestGeneration === state.requestGeneration) {
      elements.controlMessage.textContent = error.message;
    }
  } finally {
    if (requestGeneration === state.requestGeneration) {
      const campaign = selectedCampaign();
      elements.enumerateButton.disabled = !campaign || !campaign.enumeration_ready;
      elements.enumerateButton.textContent = "Enumerate realizations";
    }
  }
}

function selectTab(tabName) {
  for (const tab of elements.tabs) {
    const active = tab.dataset.tab === tabName;
    tab.classList.toggle("is-active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  }
  for (const panel of elements.panels) {
    const active = panel.id === `panel-${tabName}`;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  }
}

function handleTabKeydown(event) {
  const currentIndex = elements.tabs.indexOf(event.currentTarget);
  const tabCount = elements.tabs.length;
  const destinations = {
    ArrowLeft: (currentIndex + tabCount - 1) % tabCount,
    ArrowRight: (currentIndex + 1) % tabCount,
    Home: 0,
    End: tabCount - 1,
  };
  const nextIndex = destinations[event.key];
  if (nextIndex === undefined) {
    return;
  }
  event.preventDefault();
  const nextTab = elements.tabs[nextIndex];
  selectTab(nextTab.dataset.tab);
  nextTab.focus();
}

function downloadResult() {
  if (!state.result) {
    return;
  }
  const body = JSON.stringify(state.result, null, 2) + "\n";
  const blob = new Blob([body], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${state.result.campaign.campaign_id}.realization-space.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

const SERVER_COMMAND = "python scripts/run_realization_workbench.py";

function explainMissingServer(detail) {
  elements.inventoryLine.textContent = "The workbench server is not running.";
  elements.controlMessage.textContent =
    `From the artifact root, run: ${SERVER_COMMAND}, then open the address it prints.` +
    (detail ? ` (${detail})` : "");
}

async function initialize() {
  if (window.location.protocol === "file:") {
    explainMissingServer("");
    return;
  }
  try {
    state.inventory = await fetchJson("/api/campaigns");
    elements.inventoryLine.textContent =
      `${state.inventory.compiled_count} compiled plans; ` +
      `${state.inventory.enumeration_ready_count} with frozen binding catalogs.`;
    renderCampaignOptions();
  } catch (error) {
    explainMissingServer(error.message);
  }
}

elements.readyOnly.addEventListener("change", renderCampaignOptions);
elements.campaignSelect.addEventListener("change", renderCampaignMeta);
elements.enumerateButton.addEventListener("click", enumerateCampaign);
elements.downloadButton.addEventListener("click", downloadResult);
for (const tab of elements.tabs) {
  tab.addEventListener("click", () => selectTab(tab.dataset.tab));
  tab.addEventListener("keydown", handleTabKeydown);
}

initialize();
