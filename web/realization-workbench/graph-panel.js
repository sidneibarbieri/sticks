"use strict";

// "Causal graph" tab. A causal structure is the DAG of steps and the facts that
// link them; each realization is one execution order compatible with it.
(() => {
  const structureSelect = document.querySelector("#graph-structure-select");
  const orderSelect = document.querySelector("#graph-order-select");
  const initialToggle = document.querySelector("#graph-initial-links");
  const summary = document.querySelector("#graph-summary");
  const svg = document.querySelector("#causal-graph");
  const details = document.querySelector("#graph-details");
  const scrollHint = document.querySelector("#graph-scroll-hint");
  let structures = [];
  let model = null;
  let selectedSortKey = null;

  function groupByStructure(realizations) {
    const groups = new Map();
    for (const realization of realizations) {
      const key = realization.graph.causal_structure_sha256;
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key).push(realization);
    }
    return Array.from(groups.values());
  }

  function option(value, label) {
    const element = document.createElement("option");
    element.value = String(value);
    element.textContent = label;
    return element;
  }

  function textBlock(tag, className, text) {
    const element = document.createElement(tag);
    element.className = className;
    element.textContent = text;
    return element;
  }

  function factList(facts) {
    const list = document.createElement("ul");
    list.className = "fact-list";
    for (const fact of facts.length > 0 ? facts : ["none"]) {
      list.append(textBlock("li", "", fact));
    }
    return list;
  }

  function detailSection(label, content) {
    const section = document.createElement("div");
    section.append(textBlock("p", "section-label", label), content);
    return section;
  }

  function counterpartLabel(nodeIds) {
    const steps = nodeIds.filter((nodeId) => model.nodes.find((node) => node.id === nodeId).kind === "step");
    const others = nodeIds.filter((nodeId) => !steps.includes(nodeId))
      .map((nodeId) => model.nodes.find((node) => node.id === nodeId).title.toLowerCase());
    const stepLabel = steps.length === 0 ? [] : [`step${steps.length === 1 ? "" : "s"} ${steps.sort((left, right) => left - right).join(", ")}`];
    return [...others, ...stepLabel].join("; ");
  }

  function linkedFacts(edges, direction, nodeId) {
    const near = direction === "in" ? "to" : "from";
    const far = direction === "in" ? "from" : "to";
    const arrow = direction === "in" ? "←" : "→";
    const counterpartsByFact = new Map();
    for (const edge of edges.filter((candidate) => candidate[near] === nodeId)) {
      for (const fact of edge.facts) {
        counterpartsByFact.set(fact, [...(counterpartsByFact.get(fact) || []), edge[far]]);
      }
    }
    return Array.from(counterpartsByFact, ([fact, nodeIds]) => `${fact} ${arrow} ${counterpartLabel(nodeIds)}`);
  }

  function describeStep(node) {
    const allEdges = [...model.initialEdges, ...model.edges];
    return [
      textBlock("p", "graph-details-title", `Step ${node.id} · ${node.title}`),
      textBlock("p", "graph-details-subtitle", node.subtitle),
      detailSection("Consumes", factList(linkedFacts(allEdges, "in", node.id))),
      detailSection("Enables", factList(linkedFacts(allEdges, "out", node.id))),
      detailSection("Fidelity ceiling · assumptions",
        textBlock("p", "", `${node.step.fidelity_ceiling} · ${node.step.assumption_count}`)),
    ];
  }

  function describeBoundary(node) {
    const certificate = structures[Number(structureSelect.value)][0].plan.planning_certificate;
    const facts = node.kind === "initial" ? certificate.initial_facts : linkedFacts(model.edges, "in", node.id);
    return [
      textBlock("p", "graph-details-title", node.title),
      detailSection(node.kind === "initial" ? "Given facts" : "Reached by", factList(facts)),
    ];
  }

  function describeNode(nodeId) {
    const node = model.nodes.find((candidate) => candidate.id === nodeId);
    selectedSortKey = node.sortKey;
    details.replaceChildren(...(node.kind === "step" ? describeStep(node) : describeBoundary(node)));
    highlightSelection(svg, nodeId);
  }

  function draw() {
    const realization = structures[Number(structureSelect.value)][Number(orderSelect.value)];
    model = buildCausalGraphModel(realization);
    renderCausalGraph(svg, model, {
      showInitialLinks: initialToggle.checked,
      onSelect: describeNode,
      availableWidth: svg.parentElement.clientWidth - 24,
    });
    scrollHint.hidden = Number(svg.getAttribute("width")) <= svg.parentElement.clientWidth - 20;
    const selected = model.nodes.find((node) => node.sortKey === selectedSortKey)
      || model.nodes.find((node) => node.kind === "goal");
    describeNode(selected.id);
  }

  function showStructure(structureIndex) {
    const orders = structures[structureIndex];
    orderSelect.replaceChildren(...orders.map((realization, index) =>
      option(index, `Order ${index + 1} of ${orders.length} · source steps ${realization.source_step_order.map((step) => step + 1).join(" ")}`)));
    summary.textContent =
      `${structures.length} causal structure${structures.length === 1 ? "" : "s"} · ` +
      `${orders.length} valid execution order${orders.length === 1 ? "" : "s"} for this structure. ` +
      "Numbers on the steps give the selected order.";
    selectedSortKey = null;
    draw();
  }

  function populate(response) {
    structures = groupByStructure(response.result.realizations);
    structureSelect.replaceChildren(...structures.map((group, index) =>
      option(index, `Structure ${index + 1} · ${group[0].graph.causal_structure_sha256.slice(0, 10)}`)));
    structureSelect.disabled = structures.length < 2;
    orderSelect.disabled = structures.length === 0;
    if (structures.length > 0) {
      showStructure(0);
    } else {
      svg.replaceChildren();
      summary.textContent = "The search returned no realization to draw.";
      details.replaceChildren();
    }
  }

  let lastCanvasWidth = 0;
  new ResizeObserver(([entry]) => {
    const width = Math.round(entry.contentRect.width);
    if (model !== null && width > 0 && width !== lastCanvasWidth) {
      lastCanvasWidth = width;
      draw();
    }
  }).observe(svg.parentElement);

  structureSelect.addEventListener("change", () => showStructure(Number(structureSelect.value)));
  orderSelect.addEventListener("change", draw);
  initialToggle.addEventListener("change", draw);
  document.addEventListener("workbench:result", (event) => populate(event.detail));
})();
