"use strict";

// Causal DAG of one realization. Nodes: initial state, steps and goal. Edges carry
// the facts one node produces and another consumes. Links from the initial state
// are kept apart so the drawing can show them on request.

const INITIAL_SEQUENCE = 0;
const NODE_WIDTH = 188;
const NODE_HEIGHT = 56;
const LAYER_GAP = 52;
const ROW_GAP = 16;
const MARGIN = 14;
const SVG_NAMESPACE = "http://www.w3.org/2000/svg";

function goalSequence(plan) {
  return plan.steps.length + 1;
}

function groupLinks(links) {
  const edgesByPair = new Map();
  for (const link of links) {
    const key = `${link.producer_sequence}->${link.consumer_sequence}`;
    if (!edgesByPair.has(key)) {
      edgesByPair.set(key, {from: link.producer_sequence, to: link.consumer_sequence, facts: []});
    }
    edgesByPair.get(key).facts.push(link.fact_id);
  }
  return Array.from(edgesByPair.values());
}

function goalEdges(plan) {
  const certificate = plan.planning_certificate;
  const goals = new Set(certificate.goal_facts);
  return certificate.transitions
    .map((transition) => ({
      from: transition.sequence,
      to: goalSequence(plan),
      facts: transition.added_facts.filter((fact) => goals.has(fact)),
    }))
    .filter((edge) => edge.facts.length > 0);
}

function buildNodes(realization, initialEdges) {
  const plan = realization.plan;
  const certificate = plan.planning_certificate;
  const givenCountByStep = new Map(initialEdges.map((edge) => [edge.to, edge.facts.length]));
  const steps = plan.steps.map((step) => ({
    id: step.sequence,
    kind: "step",
    title: step.technique_id,
    subtitle: step.template_id,
    givenFactCount: givenCountByStep.get(step.sequence) || 0,
    sortKey: realization.source_step_order[step.sequence - 1],
    step,
  }));
  return [
    {id: INITIAL_SEQUENCE, kind: "initial", sortKey: -1, title: "Initial state", subtitle: `${certificate.initial_facts.length} given facts`},
    ...steps,
    {id: goalSequence(plan), kind: "goal", sortKey: steps.length, title: "Goal", subtitle: certificate.goal_facts.join(", ")},
  ];
}

function assignLayers(nodes, edges) {
  const layerById = new Map(nodes.map((node) => [node.id, 0]));
  const sortedIds = nodes.map((node) => node.id).sort((left, right) => left - right);
  for (const nodeId of sortedIds) {
    for (const edge of edges.filter((candidate) => candidate.to === nodeId)) {
      layerById.set(nodeId, Math.max(layerById.get(nodeId), layerById.get(edge.from) + 1));
    }
  }
  return layerById;
}

function orderLayers(nodes, edges, layerById) {
  const layerCount = Math.max(...layerById.values()) + 1;
  const layers = Array.from({length: layerCount}, () => []);
  for (const node of [...nodes].sort((left, right) => left.sortKey - right.sortKey)) {
    layers[layerById.get(node.id)].push(node);
  }
  const rowById = new Map();
  for (const layer of layers) {
    const barycenter = (node) => {
      const parents = edges.filter((edge) => edge.to === node.id && rowById.has(edge.from));
      if (parents.length === 0) {
        return node.sortKey;
      }
      return parents.reduce((sum, edge) => sum + rowById.get(edge.from), 0) / parents.length;
    };
    layer.sort((left, right) => barycenter(left) - barycenter(right) || left.sortKey - right.sortKey);
    layer.forEach((node, row) => rowById.set(node.id, row));
  }
  return layers;
}

function placeLayers(layers) {
  const tallest = Math.max(...layers.map((layer) => layer.length));
  const columnHeight = tallest * (NODE_HEIGHT + ROW_GAP) - ROW_GAP;
  layers.forEach((layer, layerIndex) => {
    const layerHeight = layer.length * (NODE_HEIGHT + ROW_GAP) - ROW_GAP;
    const offset = (columnHeight - layerHeight) / 2;
    layer.forEach((node, row) => {
      node.layer = layerIndex;
      node.x = MARGIN + layerIndex * (NODE_WIDTH + LAYER_GAP);
      node.y = MARGIN + offset + row * (NODE_HEIGHT + ROW_GAP);
    });
  });
  return {
    width: MARGIN * 2 + layers.length * (NODE_WIDTH + LAYER_GAP) - LAYER_GAP,
    height: MARGIN * 2 + columnHeight,
  };
}

function buildCausalGraphModel(realization) {
  const plan = realization.plan;
  const allLinks = groupLinks(plan.planning_certificate.causal_links);
  const initialEdges = allLinks.filter((edge) => edge.from === INITIAL_SEQUENCE);
  const stepEdges = [...allLinks.filter((edge) => edge.from !== INITIAL_SEQUENCE), ...goalEdges(plan)];
  const nodes = buildNodes(realization, initialEdges);
  const layerById = assignLayers(nodes, [...initialEdges, ...stepEdges]);
  const size = placeLayers(orderLayers(nodes, stepEdges, layerById));
  return {nodes, edges: stepEdges, initialEdges, ...size};
}

function svgElement(tag, attributes = {}) {
  const element = document.createElementNS(SVG_NAMESPACE, tag);
  for (const [name, value] of Object.entries(attributes)) {
    element.setAttribute(name, String(value));
  }
  return element;
}

function edgePath(fromNode, toNode) {
  const startX = fromNode.x + NODE_WIDTH;
  const startY = fromNode.y + NODE_HEIGHT / 2;
  const endX = toNode.x;
  const endY = toNode.y + NODE_HEIGHT / 2;
  const bend = Math.max((endX - startX) / 2, 24);
  return `M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`;
}

function drawEdge(edge, nodeById, className) {
  const path = svgElement("path", {
    d: edgePath(nodeById.get(edge.from), nodeById.get(edge.to)),
    class: className,
    "marker-end": "url(#graph-arrow)",
    "data-from": edge.from,
    "data-to": edge.to,
  });
  const title = svgElement("title");
  title.textContent = edge.facts.join("\n");
  path.append(title);
  return path;
}

function shortened(text, limit) {
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
}


function orderBadge(position) {
  const badge = svgElement("g", {class: "graph-order"});
  badge.append(svgElement("circle", {cx: NODE_WIDTH - 15, cy: 15, r: 10}));
  const label = svgElement("text", {x: NODE_WIDTH - 15, y: 19, "text-anchor": "middle"});
  label.textContent = String(position);
  badge.append(label);
  return badge;
}

function nodeTitle(node) {
  const title = svgElement("text", {x: 12, y: 24, class: "graph-node-title"});
  title.textContent = node.title;
  if (node.givenFactCount > 0) {
    const given = svgElement("tspan", {class: "graph-node-given", dx: 6});
    given.textContent = `+${node.givenFactCount} given`;
    title.append(given);
  }
  return title;
}

function drawNode(node, onSelect) {
  const group = svgElement("g", {
    class: `graph-node graph-node-${node.kind}`,
    transform: `translate(${node.x} ${node.y})`,
    tabindex: 0,
    role: "button",
    "data-id": node.id,
    "aria-label": `${node.title}, ${node.subtitle}`,
  });
  const tooltip = svgElement("title");
  tooltip.textContent = `${node.title}\n${node.subtitle}`;
  const subtitle = svgElement("text", {x: 12, y: 42, class: "graph-node-subtitle"});
  subtitle.textContent = shortened(node.subtitle, 23);
  group.append(tooltip, svgElement("rect", {width: NODE_WIDTH, height: NODE_HEIGHT, rx: 7}), nodeTitle(node), subtitle);
  if (node.kind === "step") {
    group.append(orderBadge(node.id));
  }
  group.addEventListener("click", () => onSelect(node.id));
  group.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(node.id);
    }
  });
  return group;
}

function arrowMarkers() {
  const definitions = svgElement("defs");
  for (const [id, className] of [["graph-arrow", "graph-arrow"], ["graph-arrow-related", "graph-arrow is-related"]]) {
    const marker = svgElement("marker", {
      id, viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 5, markerHeight: 5, orient: "auto",
    });
    marker.append(svgElement("path", {d: "M 0 0 L 10 5 L 0 10 z", class: className}));
    definitions.append(marker);
  }
  return definitions;
}

const MINIMUM_SCALE = 0.72;

function fitToWidth(svg, model, availableWidth) {
  const scale = Math.min(1, Math.max(MINIMUM_SCALE, availableWidth / model.width));
  svg.setAttribute("width", Math.round(model.width * scale));
  svg.setAttribute("height", Math.round(model.height * scale));
}

function renderCausalGraph(svg, model, options) {
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));
  svg.replaceChildren(arrowMarkers());
  svg.setAttribute("viewBox", `0 0 ${model.width} ${model.height}`);
  fitToWidth(svg, model, options.availableWidth);
  if (options.showInitialLinks) {
    svg.append(...model.initialEdges.map((edge) => drawEdge(edge, nodeById, "graph-edge graph-edge-initial")));
  }
  svg.append(...model.edges.map((edge) => drawEdge(edge, nodeById, "graph-edge")));
  svg.append(...model.nodes.map((node) => drawNode(node, options.onSelect)));
}

function highlightSelection(svg, nodeId) {
  for (const node of svg.querySelectorAll(".graph-node")) {
    node.classList.toggle("is-selected", Number(node.dataset.id) === nodeId);
  }
  for (const edge of svg.querySelectorAll(".graph-edge")) {
    const touches = Number(edge.dataset.from) === nodeId || Number(edge.dataset.to) === nodeId;
    edge.classList.toggle("is-related", touches);
    edge.setAttribute("marker-end", touches ? "url(#graph-arrow-related)" : "url(#graph-arrow)");
  }
}

if (typeof module !== "undefined") {
  module.exports = {buildCausalGraphModel};
}
