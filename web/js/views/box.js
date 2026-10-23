// The recipe box: search, course filter, and the list of recipes.

import { h, fill, icon } from "../dom.js";
import { api } from "../api.js";
import { human } from "../time.js";
import { COURSE, courseInfo, tile, topbar, stars, setTitle } from "./common.js";

const KEY = "dogear.box";

function loadPrefs() {
  try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch { return {}; }
}
function savePrefs(p) {
  try { sessionStorage.setItem(KEY, JSON.stringify(p)); } catch { /* private mode */ }
}

function sortKey(r) {
  return [r.lastCooked || "", r.added || "", r.title.toLowerCase()];
}

export async function mount(root) {
  setTitle("");
  const recipes = await api.recipes();
  recipes.sort((a, b) => {
    const [la, aa, ta] = sortKey(a);
    const [lb, ab, tb] = sortKey(b);
    return lb.localeCompare(la) || ab.localeCompare(aa) || ta.localeCompare(tb);
  });
  const prefs = { q: "", course: "all", ...loadPrefs() };

  const searchInput = h("input", {
    type: "search", id: "q", placeholder: "Search recipes or ingredients", value: prefs.q,
    autocomplete: "off", enterkeyhint: "search",
    oninput: (e) => { prefs.q = e.target.value; update(); },
  });
  const chipRow = h("div", { class: "chips", role: "group", "aria-label": "Filter" });
  const list = h("div", { class: "cards", role: "list" });

  const needReview = recipes.filter((r) => r.review || !r.ok).length;
  const courses = Object.keys(COURSE).filter((c) => recipes.some((r) => r.course === c));
  const chipDefs = [["all", "All"], ...courses.map((c) => [c, COURSE[c].plural])];
  if (needReview) chipDefs.push(["review", "Needs review"]);
  if (!chipDefs.some(([k]) => k === prefs.course)) prefs.course = "all";

  function update() {
    savePrefs(prefs);
    fill(chipRow, chipDefs.map(([key, label]) =>
      h("button", {
        type: "button", class: "chip", "aria-pressed": String(prefs.course === key),
        onclick: () => { prefs.course = key; update(); },
      }, key === "review" ? h("span", { class: "flag", "aria-hidden": "true" }) : null, label)));

    const words = prefs.q.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const shown = recipes.filter((r) => {
      if (prefs.course === "review" ? !(r.review || !r.ok) : prefs.course !== "all" && r.course !== prefs.course) return false;
      return words.every((w) => r.search.includes(w));
    });
    fill(list, shown.map(card));
    if (!shown.length) {
      list.append(h("p", { class: "empty", style: { "grid-column": "1 / -1" } },
        recipes.length ? "No matches" : ""));
    }
  }

  const body = recipes.length
    ? [
        h("div", { class: "box-head" },
          h("h1", {}, "Recipes"),
          h("div", { class: "search" },
            h("label", { for: "q", class: "sr-only" }, "Search recipes or ingredients"),
            icon("search", 20), searchInput)),
        chipRow,
        list,
      ]
    : [h("div", { class: "empty" },
        h("h2", {}, "No recipes yet"),
        h("p", {}, "Add ", h("code", {}, ".md"), " files to your recipes folder, then reload."))];

  root.append(topbar(), h("main", { class: "wrap box" }, body));
  if (recipes.length) update();
}

function card(r) {
  const meta = [];
  if (r.ok) {
    meta.push(courseInfo(r.course).label);
    if (r.totalS) meta.push(human(r.totalS));
    if (r.activeS && r.activeS !== r.totalS) meta.push(`${human(r.activeS)} hands-on`);
  } else {
    meta.push("Can't read this file");
  }
  return h("div", { class: `card${r.ok ? "" : " broken"}`, role: "listitem" },
    tile(r.course),
    h("div", { class: "body" },
      h("div", { class: "title" }, h("a", { href: `/r/${r.slug}` }, r.title)),
      h("div", { class: "sub" }, meta.join(" · "), r.rating ? stars(r.rating, 13) : null)),
    r.review || !r.ok ? h("span", { class: "flag", title: "Needs review", role: "img", "aria-label": "Needs review" }) : null);
}
