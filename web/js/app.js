// App shell: a History API router. Each view exports
//   mount(root, params, query) -> optional cleanup function
// and owns everything inside root until the route changes.

import { h, icon } from "./dom.js";
import * as box from "./views/box.js";
import * as recipe from "./views/recipe.js";
import * as cook from "./views/cook.js";

const ROUTES = [
  [/^\/$/, box],
  [/^\/r\/([a-z0-9-]+)\/?$/, recipe],
  [/^\/cook\/([a-z0-9-]+)\/?$/, cook],
];

const root = document.getElementById("app");
let cleanup = null;

export function navigate(url, { replace = false } = {}) {
  if (replace) history.replaceState(null, "", url);
  else history.pushState(null, "", url);
  render();
}

async function render() {
  if (cleanup) { try { cleanup(); } catch (e) { console.error(e); } }
  cleanup = null;
  document.body.className = "";
  const path = location.pathname;
  const match = ROUTES.map(([re, view]) => [path.match(re), view]).find(([m]) => m);
  root.replaceChildren();
  if (!match) {
    root.append(notFound());
    return;
  }
  const [m, view] = match;
  try {
    cleanup = (await view.mount(root, m.slice(1).map(decodeURIComponent),
      new URLSearchParams(location.search))) || null;
  } catch (err) {
    console.error(err);
    root.replaceChildren(failed(err));
  }
}

function notFound() {
  return h("main", { class: "wrap empty" },
    h("h2", {}, "Nothing here"),
    h("p", {}, h("a", { href: "/" }, "Back to recipes")));
}

function failed(err) {
  return h("main", { class: "wrap empty" },
    h("h2", {}, err.status === 404 ? "Recipe not found" : "Something went wrong"),
    err.status === 404 ? null : h("p", {}, err.message),
    h("p", {}, h("a", { href: "/" }, icon("back", 16), " Recipes")));
}

// Internal links navigate without a page load.
document.addEventListener("click", (event) => {
  const a = event.target.closest("a[href]");
  if (!a || a.target || a.hasAttribute("download") || event.defaultPrevented) return;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  event.preventDefault();
  if (url.pathname + url.search !== location.pathname + location.search) navigate(url.pathname + url.search);
});

window.addEventListener("popstate", render);
render();
