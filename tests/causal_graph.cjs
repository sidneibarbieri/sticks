"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const {buildCausalGraphModel} = require("../web/realization-workbench/causal-graph.js");

const response = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const placementByStructure = new Map();
for (const realization of response.result.realizations) {
  const model = buildCausalGraphModel(realization);
  const plan = realization.plan;
  const certificate = plan.planning_certificate;
  const goalId = plan.steps.length + 1;
  const nodeById = new Map(model.nodes.map((node) => [node.id, node]));

  assert.equal(model.nodes.length, plan.steps.length + 2);
  const stepLinks = model.edges.filter((edge) => edge.to !== goalId);
  const linkedFacts = [...model.initialEdges, ...stepLinks].flatMap((edge) => edge.facts);
  assert.equal(linkedFacts.length, certificate.causal_links.length, "every causal link is drawn once");
  for (const edge of [...model.initialEdges, ...model.edges]) {
    assert.ok(nodeById.get(edge.from).layer < nodeById.get(edge.to).layer, "edges point forward");
  }
  const goalFacts = model.edges.filter((edge) => edge.to === goalId).flatMap((edge) => edge.facts);
  assert.deepEqual([...new Set(goalFacts)].sort(), [...certificate.goal_facts].sort());

  const placement = JSON.stringify(model.nodes.map((node) => [node.sortKey, node.x, node.y]).sort());
  const structure = realization.graph.causal_structure_sha256;
  if (placementByStructure.has(structure)) {
    assert.equal(placement, placementByStructure.get(structure), "layout is stable across execution orders");
  }
  placementByStructure.set(structure, placement);
}
console.log(`checked ${response.result.realizations.length} realizations`);
