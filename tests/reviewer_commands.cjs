"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const [mode, payloadPath] = process.argv.slice(2);
const payload = JSON.parse(fs.readFileSync(payloadPath, "utf8"));
const nodes = new Map();
const makeElement = () => ({
  value: "C0045", textContent: "", hidden: false, disabled: false,
  files: [{name: "untrusted ' ; $(touch injected).json", size: 2}],
  listeners: {}, classList: {add() {}, remove() {}, toggle() {}},
  addEventListener(name, callback) {this.listeners[name] = callback;},
  replaceChildren() {}, append() {}, setAttribute() {}, removeAttribute() {},
  querySelectorAll() {return [];}, checkValidity() {return true;},
});
const document = {
  querySelector(selector) {
    if (!nodes.has(selector)) nodes.set(selector, makeElement());
    return nodes.get(selector);
  },
  querySelectorAll() {return [];},
  createElement: makeElement,
  dispatchEvent() {},
};
const context = vm.createContext({
  document, window: {location: {protocol: mode === "planning" ? "file:" : "http:"}},
  fetch: async () => ({ok: true, json: async () => payload}),
  CustomEvent: class {constructor(type, options) {this.type = type; this.detail = options.detail;}},
  payload,
});

async function main() {
  const filename = mode === "planning" ? "app.js" : "bundle.js";
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../web/realization-workbench", filename), "utf8"), context);
  if (mode === "planning") {
    vm.runInContext(`
      renderMetrics = renderSummary = renderSteps = renderRealizations = renderQueue = () => {};
      renderResult(payload);
    `, context);
  } else {
    await nodes.get("#bundle-form").listeners.submit({preventDefault() {}});
  }
  const selector = mode === "planning" ? "#recompute-command" : "#bundle-command";
  const command = nodes.get(selector).textContent;
  if (!command) throw new Error("The rendered command is empty");
  process.stdout.write(command);
}

main().catch((error) => {console.error(error); process.exitCode = 1;});
