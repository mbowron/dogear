// Tiny DOM helpers. Everything is built with createElement and text nodes,
// never innerHTML, so recipe text can't inject markup.

const SVG_NS = "http://www.w3.org/2000/svg";

/**
 * h("button", { class: "btn", onclick: fn, "aria-label": "Close" }, "text", child)
 * Attributes: class, style (string or object), on* handlers, boolean false/null skips.
 * Children: strings, numbers, nodes, arrays, null/false (skipped).
 */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

function setAttrs(el, attrs) {
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === false || value === null || value === undefined) continue;
    if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (key === "style" && typeof value === "object") {
      for (const [p, v] of Object.entries(value)) el.style.setProperty(p, v);
    } else if (key === "dataset") {
      Object.assign(el.dataset, value);
    } else if (key === "value" && "value" in el) {
      el.value = value;
    } else {
      el.setAttribute(key, value === true ? "" : String(value));
    }
  }
}

/** Replace an element's children; accepts the same children as h(). */
export function fill(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

export function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

// ---------------------------------------------------------------------------
// Icons: 24x24 stroke paths drawn to match the brand mockups.
// ---------------------------------------------------------------------------

const PATHS = {
  back: ["m15 5-7 7 7 7"],
  close: ["M6 6l12 12M18 6 6 18"],
  plus: ["M12 5v14M5 12h14"],
  minus: ["M5 12h14"],
  check: ["m5 12.5 4.5 4.5L19 7.5"],
  search: ["M16 16l4 4", { circle: [11, 11, 6.5] }],
  timer: ["M12 9v4l2.5 2M9.5 2.5h5", { circle: [12, 13, 8] }],
  swap: ["M7 7h11l-3-3M17 17H6l3 3"],
  chevron: ["m6 9 6 6 6-6"],
  pause: [{ fill: "M6 5h4v14H6zM14 5h4v14h-4z" }],
  play: [{ fill: "M8 5.5v13a1 1 0 0 0 1.5.9l10.4-6.5a1 1 0 0 0 0-1.8L9.5 4.6A1 1 0 0 0 8 5.5z" }],
  star: ["m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"],
  // course tiles
  main: ["M16.5 13H22M8 11.5c1-.6 2.4-.6 3.5.3", { circle: [10, 13, 6.5] }],
  bowl: ["M3 12h18a9 8 0 0 1-18 0zM9 8.5c0-1.6 1.2-1.8 1.2-3.5M13.5 8.5c0-1.6 1.2-1.8 1.2-3.5"],
  bread: ["M5 11.5A3.6 3.6 0 0 1 7 5h10a3.6 3.6 0 0 1 2 6.5V19a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1zM9.5 9l-1.5 2.5M13 9l-1.5 2.5M16.5 9 15 11.5"],
  jar: ["M7 3.5h10V7H7zM6 12.5h12", { rect: [6, 7, 12, 14, 2.5] }],
  glass: ["M6 6h12l-1.6 14a1 1 0 0 1-1 .9H8.6a1 1 0 0 1-1-.9zM6.6 11h10.8M14 6l2-3.5"],
  cake: ["M4 20h16M5 20v-7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v7M5 15c2 1.5 4 1.5 7 0s5-1.5 7 0M12 11V7M12 4.5v.5"],
  leaf: ["M5 19c0-8 5-13 14-14 0 9-5 14-13 14zM5 19l7-7"],
  book: ["M6 3h9l4 4v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM15 3v4h4"],
};

export function icon(name, size = 20, { stroke = 2, filled = false, label } = {}) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "icon");
  if (label) {
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
  } else {
    svg.setAttribute("aria-hidden", "true");
  }
  for (const part of PATHS[name] || []) {
    let el;
    if (typeof part === "string") {
      el = document.createElementNS(SVG_NS, "path");
      el.setAttribute("d", part);
    } else if (part.circle) {
      el = document.createElementNS(SVG_NS, "circle");
      const [cx, cy, r] = part.circle;
      el.setAttribute("cx", cx); el.setAttribute("cy", cy); el.setAttribute("r", r);
    } else if (part.rect) {
      el = document.createElementNS(SVG_NS, "rect");
      const [x, y, w, hh, rx] = part.rect;
      el.setAttribute("x", x); el.setAttribute("y", y); el.setAttribute("width", w);
      el.setAttribute("height", hh); el.setAttribute("rx", rx);
    } else if (part.fill) {
      el = document.createElementNS(SVG_NS, "path");
      el.setAttribute("d", part.fill);
      el.setAttribute("fill", "currentColor");
      svg.append(el);
      continue;
    }
    el.setAttribute("fill", filled ? "currentColor" : "none");
    el.setAttribute("stroke", "currentColor");
    el.setAttribute("stroke-width", stroke);
    el.setAttribute("stroke-linecap", "round");
    el.setAttribute("stroke-linejoin", "round");
    svg.append(el);
  }
  return svg;
}

export function logo(size = 34) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("viewBox", "0 0 64 64");
  svg.setAttribute("aria-hidden", "true");
  const parts = [
    ["rect", { width: 64, height: 64, rx: 15, fill: "#173E32" }],
    ["path", { d: "M19 12h19l10 10v28a3 3 0 0 1-3 3H19a3 3 0 0 1-3-3V15a3 3 0 0 1 3-3z", fill: "#F7EEDB" }],
    ["path", { d: "M38 12v7a3 3 0 0 0 3 3h7z", fill: "#E9AA42" }],
    ["ellipse", { cx: 26, cy: 29, rx: 3.6, ry: 5.2, transform: "rotate(-45 26 29)", fill: "#173E32" }],
    ["path", { d: "M28.6 31.6 39 42M25 42l11-11M34.5 28.5l4-4M36.5 30.5l4-4M33 33.4l6.4-6.4", stroke: "#173E32", "stroke-width": 2.6, "stroke-linecap": "round", fill: "none" }],
  ];
  for (const [tag, attrs] of parts) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    svg.append(el);
  }
  return svg;
}

// ---------------------------------------------------------------------------
// A small, safe Markdown subset: paragraphs, "- " lists, **bold**, *italic*,
// `code` and [links](https://...).
// ---------------------------------------------------------------------------

const INLINE = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[[^\]]+\]\(https?:\/\/[^)\s]+\))/g;

export function inline(text) {
  const out = [];
  let last = 0;
  for (const m of String(text || "").matchAll(INLINE)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(h("b", {}, tok.slice(2, -2)));
    else if (tok.startsWith("`")) out.push(h("code", {}, tok.slice(1, -1)));
    else if (tok.startsWith("[")) {
      const [, label, href] = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      out.push(h("a", { href, target: "_blank", rel: "noopener noreferrer" }, label));
    } else out.push(h("i", {}, tok.slice(1, -1)));
    last = m.index + tok.length;
  }
  if (last < String(text || "").length) out.push(text.slice(last));
  return out;
}

export function blocks(text) {
  const nodes = [];
  let list = null;
  let para = [];
  const flush = () => {
    if (para.length) nodes.push(h("p", {}, inline(para.join(" "))));
    para = [];
  };
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trim();
    const item = line.match(/^[-*]\s+(.*)$/);
    if (item) {
      flush();
      if (!list) { list = h("ul"); nodes.push(list); }
      list.append(h("li", {}, inline(item[1])));
    } else if (!line) {
      flush();
      list = null;
    } else if (list && raw.startsWith("  ")) {
      list.lastChild.append(" ", ...inline(line));
    } else {
      list = null;
      para.push(line);
    }
  }
  flush();
  return nodes;
}
