// One recipe: servings, plate time, ingredients, every step, notes, cook log.

import { h, fill, icon, inline, blocks } from "../dom.js";
import { api } from "../api.js";
import { clock, human, countdown, durationLabel, hhmm, nextAt, isTomorrow, shortDate } from "../time.js";
import { readPlan, planQuery, timedSteps, startOf, packRows, HEAT, applianceLabel } from "../plan.js";
import { unlock, ring, silence } from "../alarm.js";
import { courseInfo, topbar, setTitle } from "./common.js";
import { savedSession } from "./cook.js";

export async function mount(root, [slug], query) {
  let data = await api.recipe(slug, query.get("servings"));
  const recipe = data.recipe;
  setTitle(recipe ? recipe.title : slug);

  if (!recipe) {
    root.append(topbar(), h("main", { class: "wrap recipe" },
      h("div", { class: "hero" }, h("h1", {}, slug)),
      issuesAlert(data.issues, `${slug}.md`)));
    return;
  }

  const plan = readPlan(recipe, query);
  plan.servings = data.view.servings;
  let startNow = query.get("start") === "now";
  const doneSteps = new Set();
  const timers = new Map(); // step number -> { endsAt, total, left (when paused) }

  // -- regions that re-render --------------------------------------------
  const planBox = h("section", { class: "panel plan", "aria-labelledby": "plan-h" });
  const ingBox = h("section", { class: "ingredients", "aria-labelledby": "ing-h" });
  const stepBox = h("section", { class: "steps", "aria-labelledby": "steps-h" });
  const logBox = h("section", { class: "panel log", "aria-labelledby": "log-h" });
  const resuming = Boolean(savedSession(slug));
  const cookLink = h("a", { class: "btn btn-pri btn-lg" }, icon("play", 20), resuming ? "Resume cooking" : "Start cooking");
  const restartLink = resuming ? h("a", { class: "btn btn-sec btn-lg" }, "Start over") : null;

  function syncUrl() {
    const q = planQuery({ ...plan, startNow }, recipe);
    history.replaceState(null, "", `/r/${slug}${q ? `?${q}` : ""}`);
    cookLink.href = resuming ? `/cook/${slug}` : `/cook/${slug}?${q}`;
    if (restartLink) restartLink.href = `/cook/${slug}?${q}&restart=1`;
  }

  function setPlate(date, now = false) {
    plan.plate = date;
    startNow = now;
    syncUrl();
    renderPlan();
    renderSteps();
  }

  // -- plan: plate time and the timeline strip -----------------------------
  function renderPlan() {
    const start = startOf(recipe, plan.plate);
    const late = start.getTime() < Date.now() - 60000;
    const input = h("input", {
      type: "time", id: "plate", value: hhmm(plan.plate), step: 300, tabindex: "-1",
      onchange: (e) => { if (e.target.value) setPlate(nextAt(e.target.value)); },
    });
    const pick = h("button", {
      type: "button", class: "plate-btn num", "aria-label": `Plate at ${clock(plan.plate)}, change`,
      onclick: () => { try { input.showPicker(); } catch { input.focus(); } },
    }, clock(plan.plate));
    const shift = (min) => setPlate(new Date(plan.plate.getTime() + min * 60000));
    fill(planBox, 
      h("div", { class: "plan-row" },
        h("div", {},
          h("label", { id: "plan-h", class: "eyebrow", for: "plate" }, "Plate at"),
          h("div", { class: "plate-time" }, pick, input,
            isTomorrow(plan.plate) ? h("span", { class: "day" }, "tomorrow") : null)),
        h("div", { class: "stepper", role: "group", "aria-label": "Plate time" },
          h("button", { type: "button", "aria-label": "15 minutes earlier", onclick: () => shift(-15) }, icon("minus", 18, { stroke: 2.4 })),
          h("button", { type: "button", "aria-label": "15 minutes later", onclick: () => shift(15) }, icon("plus", 18, { stroke: 2.4 })))),
      h("div", { class: "start" },
        h("span", { class: late ? "late" : "" }, "Start ", h("b", { class: "num" }, clock(start)), late ? " (passed)" : ""),
        startNow ? null : h("button", {
          type: "button", class: "linkbtn",
          onclick: () => setPlate(new Date(Date.now() + recipe.timing.totalS * 1000), true),
        }, "Start now")),
      recipe.timing.totalS ? strip(start) : null);
  }

  function strip(start) {
    const total = recipe.timing.totalS;
    const items = recipe.steps.map((s, i) => ({ step: s, ...recipe.timing.steps[i] }))
      .filter((x) => x.endS > x.startS);
    const rows = packRows(items);
    return h("div", { class: "strip" },
      rows.map((row) => h("div", { class: "strip-row" }, row.map((x) => {
        const kind = x.step.appliance && HEAT.has(x.step.appliance.kind) ? "heat" : x.mode === "active" ? "on" : "off";
        return h("button", {
          type: "button", class: `bar ${kind}`,
          style: { left: `${((x.startS + total) / total) * 100}%`, width: `${((x.endS - x.startS) / total) * 100}%` },
          title: `${clock(new Date(plan.plate.getTime() + x.startS * 1000))} · ${x.step.lead}`,
          "aria-label": `Step ${x.number}: ${x.step.lead}`,
          onclick: () => document.getElementById(`step-${x.number}`)?.scrollIntoView({ behavior: "smooth", block: "center" }),
        }, String(x.number));
      }))),
      h("div", { class: "strip-scale num" },
        h("span", {}, clock(start)),
        h("b", {}, clock(plan.plate))));
  }

  // -- ingredients ---------------------------------------------------------
  async function setServings(n) {
    plan.servings = n;
    data = await api.recipe(slug, n);
    plan.servings = data.view.servings;
    syncUrl();
    renderIngredients();
  }

  function renderIngredients() {
    const v = data.view;
    const max = recipe.yield.max;
    const n = plan.servings;
    const step = n < 2 ? 0.5 : 1;
    let group;
    const rows = [];
    v.ingredients.forEach((ing) => {
      if (ing.group !== group) {
        group = ing.group;
        if (group) rows.push(h("h3", { class: "ing-group" }, group));
      }
      rows.push(h("div", { class: "ing" },
        h("div", { class: "amt num" }, ing.amount),
        h("div", { class: "name" }, ing.name,
          ing.optional ? h("span", { class: "opt" }, " optional") : null,
          ing.note ? h("span", { class: "note" }, ing.note) : null),
        ing.pantry ? h("span", { class: "pantry" }, "pantry") : null));
    });
    fill(ingBox, 
      h("div", { class: "sec-head" },
        h("h2", { id: "ing-h" }, "Ingredients"),
        h("div", { class: "stepper", role: "group", "aria-label": "Servings" },
          h("button", { type: "button", "aria-label": "Fewer", disabled: n <= 0.5, onclick: () => setServings(Math.max(0.5, n - step)) }, icon("minus", 18, { stroke: 2.4 })),
          h("output", { class: "num", "aria-live": "polite" }, v.yieldLabel),
          h("button", { type: "button", "aria-label": "More", disabled: n >= max, onclick: () => setServings(Math.min(max, Math.floor(n) + 1)) }, icon("plus", 18, { stroke: 2.4 })))),
      rows);
  }

  // -- steps ---------------------------------------------------------------
  function renderSteps() {
    const timed = timedSteps(recipe, plan.plate);
    let group;
    const items = [];
    timed.forEach((s) => {
      if (s.group !== group) {
        group = s.group;
        if (group) items.push(h("h3", { class: "group" }, group));
      }
      const done = doneSteps.has(s.number);
      const app = applianceLabel(s.appliance);
      items.push(h("div", { class: `step${done ? " done" : ""}`, id: `step-${s.number}` },
        h("button", {
          type: "button", class: "ck", "aria-pressed": String(done), "aria-label": `Step ${s.number} done`,
          onclick: () => { done ? doneSteps.delete(s.number) : doneSteps.add(s.number); renderSteps(); },
        }, icon("check", 16, { stroke: 3.2 })),
        h("div", { class: "stxt" },
          h("div", { class: "when num" }, `${clock(s.start)} · Step ${s.number}`),
          h("div", { class: "text" }, h("b", {}, inline(s.lead)), s.body ? " " : null, inline(s.body)),
          s.durationS || app ? h("div", { class: "metas" },
            s.durationS ? h("span", { class: `meta ${s.mode === "active" ? "m-on" : "m-off"}` },
              `${durationLabel(s)} · ${s.mode === "active" ? "hands-on" : "hands-off"}`) : null,
            app ? h("span", { class: "meta m-app" }, app) : null) : null,
          s.fallbacks.map((f) => h("div", { class: "fallback" }, icon("swap", 16),
            `Or ${applianceLabel(f.appliance).replace(/^./, (c) => c.toLowerCase())}${f.durationS ? ` · ${durationLabel(f)}` : ""}`)),
          s.timerS && (s.mode !== "active" || s.timerS >= 120) ? timerButton(s) : null)));
    });
    fill(stepBox, h("div", { class: "sec-head" }, h("h2", { id: "steps-h" }, "Steps")), items);
  }

  function timerButton(s) {
    const btn = h("button", { type: "button", class: "timer-btn num", dataset: { step: s.number } });
    paintTimer(btn, s);
    btn.addEventListener("click", () => {
      unlock();
      const t = timers.get(s.number);
      if (!t) timers.set(s.number, { endsAt: Date.now() + s.timerS * 1000, total: s.timerS });
      else if (t.endsAt && t.endsAt <= Date.now()) { timers.delete(s.number); silenceIfQuiet(); }
      else if (t.endsAt) { t.left = (t.endsAt - Date.now()) / 1000; t.endsAt = null; }
      else { t.endsAt = Date.now() + t.left * 1000; t.left = null; }
      paintTimer(btn, s);
    });
    return btn;
  }

  function paintTimer(btn, s) {
    const t = timers.get(s.number);
    let label, cls = "timer-btn num";
    if (!t) label = `${countdown(s.timerS)} timer`;
    else if (t.endsAt === null) label = `${countdown(t.left)} paused`;
    else {
      const left = (t.endsAt - Date.now()) / 1000;
      if (left <= 0) { label = "Time’s up"; cls += " ringing"; }
      else { label = countdown(left); cls += " running"; }
    }
    btn.className = cls;
    btn.replaceChildren(icon(t && t.endsAt ? "pause" : "timer", 18), label);
    btn.setAttribute("aria-label", t ? `Step ${s.number} timer, ${label}` : `Start ${human(s.timerS)} timer for step ${s.number}`);
  }

  function silenceIfQuiet() {
    const anyRinging = [...timers.values()].some((t) => t.endsAt && t.endsAt <= Date.now());
    if (!anyRinging) silence();
  }

  const tick = setInterval(() => {
    if (!timers.size) return;
    for (const btn of stepBox.querySelectorAll(".timer-btn")) {
      const n = Number(btn.dataset.step);
      const s = recipe.steps[n - 1];
      const t = timers.get(n);
      paintTimer(btn, s);
      if (t && t.endsAt && t.endsAt <= Date.now()) ring(`Step ${n}: ${s.lead}`);
    }
  }, 500);

  // -- cook log ------------------------------------------------------------
  function renderLog() {
    const hist = data.history;
    const note = h("textarea", { id: "cook-note", placeholder: "Note", rows: 3 });
    fill(logBox, 
      h("h2", { id: "log-h" }, "Cook log"),
      h("div", { class: "rating", role: "group", "aria-label": "Rating" },
        [1, 2, 3, 4, 5].map((n) => h("button", {
          type: "button", class: "star", "aria-pressed": String(n <= hist.rating), "aria-label": `${n} of 5`,
          onclick: async () => { data.history = await api.rate(slug, hist.rating === n ? 0 : n); renderLog(); },
        }, icon("star", 28, { filled: n <= hist.rating, stroke: 1.4 })))),
      hist.cooks.length ? h("ul", { class: "cooks" }, hist.cooks.map((c) =>
        h("li", {},
          h("span", { class: "date" }, shortDate(c.date)),
          h("span", { class: "txt" }, c.note || (c.servings ? `${c.servings} ${recipe.yield.noun}` : "")),
          h("button", {
            type: "button", class: "iconbtn", "aria-label": `Delete ${shortDate(c.date)}`,
            onclick: async () => { await api.deleteCook(c.id); data = await api.recipe(slug, plan.servings); renderLog(); },
          }, icon("close", 16))))) : null,
      h("form", {
        onsubmit: async (e) => {
          e.preventDefault();
          data.history = await api.logCook(slug, { servings: plan.servings, note: note.value });
          renderLog();
        },
      },
        h("label", { for: "cook-note", class: "sr-only" }, "Note"),
        note,
        h("div", { class: "row" }, h("button", { type: "submit", class: "btn btn-gold" }, "Cooked it today"))));
  }

  // -- layout --------------------------------------------------------------
  const course = courseInfo(recipe.course);
  const eyebrow = [course.label, recipe.category].filter(Boolean).join(" · ");
  const stats = [["Total", recipe.timing.totalS], ["Hands-on", recipe.timing.activeS], ["Can wait", recipe.holdS]]
    .filter(([, v]) => v);

  root.append(topbar(), h("main", { class: "wrap recipe" },
    h("div", { class: "recipe-grid" },
      h("div", { class: "hero" },
        h("div", { class: `hero-inner${recipe.image ? " has-photo" : ""}` },
          h("div", { class: "hero-text" },
            h("p", { class: "eyebrow" }, eyebrow),
            h("h1", {}, recipe.title),
            recipe.summary ? h("p", { class: "summary" }, inline(recipe.summary)) : null,
            recipe.tags.length ? h("div", { class: "tags" }, recipe.tags.map((t) => h("span", { class: "tag" }, t))) : null,
            stats.length ? h("dl", { class: "stats" }, stats.map(([k, v]) =>
              h("div", { class: "stat" }, h("dt", {}, k), h("dd", {}, human(v))))) : null,
            h("div", { class: "actions" }, cookLink, restartLink)),
          recipe.image ? h("div", { class: "photo" },
            h("img", { src: imageUrl(recipe.image), alt: "" }),
            h("div", { class: "dogear-corner", "aria-hidden": "true" })) : null),
        recipe.review ? reviewAlert(data.issues) : data.issues.length ? issuesAlert(data.issues, `${slug}.md`) : null),
      h("div", { class: "recipe-aside" }, planBox, ingBox),
      h("div", { class: "recipe-main" },
        stepBox,
        recipe.notes ? h("section", { class: "panel notes", "aria-labelledby": "notes-h" },
          h("h2", { id: "notes-h" }, "Notes"), h("div", { class: "prose" }, blocks(recipe.notes))) : null,
        recipe.description ? h("section", { class: "panel notes" }, h("div", { class: "prose" }, blocks(recipe.description))) : null,
        logBox))));

  syncUrl();
  renderPlan();
  renderIngredients();
  renderSteps();
  renderLog();

  return () => { clearInterval(tick); silence(); };
}

function imageUrl(image) {
  return /^https?:\/\//.test(image) ? image : `/api/images/${encodeURIComponent(image.replace(/^images\//, ""))}`;
}

function reviewAlert(issues) {
  return h("div", { class: "alert review", role: "note" },
    h("b", {}, "Needs review"),
    issues.length ? h("ul", {}, issues.map((i) => h("li", {}, i.line ? `Line ${i.line}: ` : "", i.message))) : null);
}

function issuesAlert(issues, file) {
  if (!issues.length) return null;
  return h("div", { class: "alert", role: "alert" },
    h("b", {}, file),
    h("ul", {}, issues.map((i) => h("li", {}, i.line ? `Line ${i.line}: ` : "", i.message))));
}
