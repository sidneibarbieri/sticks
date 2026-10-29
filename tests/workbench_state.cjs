"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const nodes = new Map();
const tabNames = ["summary", "steps", "realizations", "queue", "json"];
const tabNodes = tabNames.map((name) => ({
  dataset: {tab: name}, attributes: new Map(), listeners: {}, tabIndex: 0,
  classList: {toggle() {}},
  setAttribute(name, value) {this.attributes.set(name, value);},
  addEventListener(name, callback) {this.listeners[name] = callback;},
  focus() {document.activeElement = this;},
}));
const panelNodes = tabNames.map((name) => ({
  id: `panel-${name}`, hidden: name !== "summary", classList: {toggle() {}},
}));
const document = {
  querySelector(selector) {
    if (!nodes.has(selector)) {
      nodes.set(selector, {
        hidden: false, value: "64", textContent: "", disabled: false,
        min: "1", max: "100000", previousElementSibling: {textContent: selector},
        attributes: new Map(),
        setAttribute(name, value) {this.attributes.set(name, value);},
        removeAttribute(name) {this.attributes.delete(name);},
        focus() {document.activeElement = this;},
        addEventListener() {},
      });
    }
    return nodes.get(selector);
  },
  querySelectorAll(selector) {
    return selector === ".tab" ? tabNodes : panelNodes;
  },
};
const context = vm.createContext({
  document, window: { location: { protocol: "file:" } }, assert,
});
const source = fs.readFileSync(
  path.join(__dirname, "../web/realization-workbench/app.js"), "utf8",
);
vm.runInContext(source, context);
const regression = vm.runInContext(`
  (async () => {
    selectTab("summary");
    assert.equal(elements.tabs.filter(tab => tab.tabIndex === 0).length, 1);
    const pressTabKey = (index, key) => {
      let prevented = false;
      elements.tabs[index].listeners.keydown({
        currentTarget: elements.tabs[index], key,
        preventDefault() {prevented = true;},
      });
      return prevented;
    };
    assert.equal(pressTabKey(0, "ArrowRight"), true);
    assert.equal(document.activeElement, elements.tabs[1]);
    assert.equal(elements.tabs[1].attributes.get("aria-selected"), "true");
    assert.equal(elements.panels[1].hidden, false);
    assert.equal(elements.panels[0].hidden, true);
    assert.equal(pressTabKey(1, "Home"), true);
    assert.equal(document.activeElement, elements.tabs[0]);
    assert.equal(pressTabKey(0, "ArrowLeft"), true);
    assert.equal(document.activeElement, elements.tabs[4]);
    assert.equal(pressTabKey(4, "ArrowRight"), true);
    assert.equal(document.activeElement, elements.tabs[0]);
    assert.equal(pressTabKey(0, "End"), true);
    assert.equal(document.activeElement, elements.tabs[4]);
    assert.equal(pressTabKey(4, "ArrowDown"), false);
    assert.equal(document.activeElement, elements.tabs[4]);
    assert.equal(elements.tabs.filter(tab => tab.tabIndex === 0).length, 1);
    const ready = {campaign_id: "C0010", enumeration_ready: true, semantic_fact_status: "conformant"};
    const unavailable = {campaign_id: "C0011", enumeration_ready: false, semantic_fact_status: "not_assessed"};
    state.inventory = {campaigns: [ready, unavailable]};
    elements.campaignSelect.value = ready.campaign_id;
    renderCampaignMeta();
    state.result = {campaign: ready};
    elements.resultWorkspace.hidden = false;
    elements.emptyState.hidden = true;
    elements.campaignSelect.value = unavailable.campaign_id;
    renderCampaignMeta();
    assert.equal(state.result, null);
    assert.equal(elements.resultWorkspace.hidden, true);
    assert.equal(elements.emptyState.hidden, false);
    assert.equal(elements.enumerateButton.disabled, true);

    elements.campaignSelect.value = ready.campaign_id;
    renderCampaignMeta();
    const limit = elements.maximumRealizations;
    limit.min = "1";
    limit.max = "256";
    limit.previousElementSibling = {textContent: "Maximum realizations"};
    for (const invalid of ["", "1.5", "0", "257", "64junk", "Infinity"]) {
      limit.value = invalid;
      assert.throws(() => numberValue(limit), /Maximum realizations/);
    }
    for (const valid of ["1", "64", "256"]) {
      limit.value = valid;
      assert.equal(numberValue(limit), Number(valid));
    }
    let invalidRequestCount = 0;
    fetchJson = async () => {invalidRequestCount += 1;};
    limit.value = "1.5";
    await enumerateCampaign();
    assert.equal(invalidRequestCount, 0);
    assert.match(elements.controlMessage.textContent, /Maximum realizations/);
    assert.equal(limit.attributes.get("aria-invalid"), "true");
    assert.equal(limit.attributes.get("aria-describedby"), "control-message");
    assert.equal(document.activeElement, limit);
    assert.equal(elements.enumerateButton.disabled, false);
    assert.equal(elements.resultWorkspace.hidden, true);
    limit.value = "64";
    let rejectRequest;
    fetchJson = () => new Promise((resolve, reject) => {rejectRequest = reject;});
    const pending = enumerateCampaign();
    assert.equal(limit.attributes.has("aria-invalid"), false);
    assert.equal(limit.attributes.has("aria-describedby"), false);
    elements.campaignSelect.value = unavailable.campaign_id;
    renderCampaignMeta();
    const currentMessage = elements.controlMessage.textContent;
    rejectRequest(new Error("obsolete request"));
    await pending;
    assert.equal(elements.controlMessage.textContent, currentMessage);
    assert.equal(elements.enumerateButton.textContent, "Enumerate realizations");
    assert.equal(elements.enumerateButton.disabled, true);

    elements.campaignSelect.value = ready.campaign_id;
    renderCampaignMeta();
    let resolveRequest;
    fetchJson = () => new Promise((resolve) => {resolveRequest = resolve;});
    let staleRendered = false;
    renderResult = () => {staleRendered = true;};
    const late = enumerateCampaign();
    elements.campaignSelect.value = unavailable.campaign_id;
    renderCampaignMeta();
    resolveRequest({campaign: ready});
    await late;
    assert.equal(state.result, null);
    assert.equal(staleRendered, false);
  })()
`, context);
regression.then(() => console.log("workbench state regression passed"))
  .catch((error) => {console.error(error); process.exitCode = 1;});
