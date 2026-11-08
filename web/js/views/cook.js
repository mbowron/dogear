// Cook mode: the ingredients, every step, and the running timers on one
// screen, under a timeline of the whole cook. Progress is saved in
// localStorage so a reload or a locked screen picks up where you left off.
//
// Built around a list of dishes so a meal (several recipes on one plate
// time) can use the same screen; today a cook has one dish.

import { h, fill, icon, inline } from "../dom.js";
import { api } from "../api.js";
import { clock, countdown, until, durationLabel, human, MIN } from "../time.js";
import { readPlan, timedSteps, packRows, applianceLabel } from "../plan.js";
import { unlock, ring, silence, stayAwake } from "../alarm.js";
import { setTitle } from "./common.js";
import { navigate } from "../app.js";

const SESSION_VERSION = 2;
const DUE_SOON_MS = 30 * 1000;
const STALE_MS = 12 * 3600 * 1000;
const PANEL_KEY = "dogear.cook.ingredients";
const SVG_NS = "http://www.w3.org/2000/svg";

// Each dish in a cook owns one color, used everywhere that dish appears.
const TIMER_PRESETS = [1, 3, 5, 10, 15, 20, 30, 45];

const DISH_COLORS = [
  { c: "#C95F40", ink: "#FFFFFF" },   // terracotta
  { c: "#E9AA42", ink: "#1A1D19" },   // mustard
  { c: "#7C9A86", ink: "#10261F" },   // sage, lifted for the dark band
  { c: "#B9851F", ink: "#FFFFFF" },
];

export function sessionKey(slug) { return `dogear.cook.${slug}`; }

export function savedSession(slug) {
  try {
    const s = JSON.parse(localStorage.getItem(sessionKey(slug)));
    if (s && s.v === SESSION_VERSION && s.plate > Date.now() - STALE_MS) return s;
  } catch { /* none */ }
  return null;
}

export async function mount(root, [slug], query) {
  const hasPlan = query.has("plate") || query.get("start") === "now";
  let session = query.get("restart") ? null : savedSession(slug);
  if (session && hasPlan && !query.get("resume")) session = null;

  const data = await api.recipe(slug, session ? session.servings : query.get("servings"));
  const recipe = data.recipe;
  if (!recipe) { navigate(`/r/${slug}`, { replace: true }); return; }
  setTitle(recipe.title);

  if (!session) {
    const plan = readPlan(recipe, query);
    session = { v: SESSION_VERSION, slug, plate: plan.plate.getTime(), servings: data.view.servings, steps: {}, have: {} };
  }
  session.have = session.have || {};
  session.timers = session.timers || [];
  const save = () => { try { localStorage.setItem(sessionKey(slug), JSON.stringify(session)); } catch { /* full */ } };
  save();
  history.replaceState(null, "", `/cook/${slug}`);
  document.body.className = "";
  stayAwake(true);

  // -- the cook: dishes, their steps on one clock, their ingredients ----------
  const plate = new Date(session.plate);
  const dishes = [{ recipe, view: data.view }].map((d, i) => ({
    index: i, title: d.recipe.title, color: DISH_COLORS[i % DISH_COLORS.length],
    ingredients: d.view.ingredients.map((ing, j) => ({ ...ing, key: `${i}:${j}` })),
    steps: timedSteps(d.recipe, plate),
  }));
  const steps = dishes
    .flatMap((d) => d.steps.map((s) => ({ ...s, id: `${d.index}:${s.number}`, dish: d })))
    .sort((a, b) => a.start - b.start || a.dish.index - b.dish.index || a.number - b.number);
  for (const s of steps) s.uses = ingredientsUsed(s, s.dish.ingredients);

  let panelOpen = loadPanelPref();
  let lastCurrent = null;

  // -- step state -------------------------------------------------------------
  const st = (s) => session.steps[s.id] || { status: "pending" };
  const alt = (s) => (st(s).alt != null ? s.fallbacks[st(s).alt] : null);
  const timerOf = (s) => {
    const a = alt(s);
    return a ? a.durationMinS || a.durationS || s.timerS : s.timerS;
  };
  // Short hands-on steps are simply done; everything else gets a timer.
  const needsTimer = (s) => Boolean(timerOf(s)) && (s.mode !== "active" || timerOf(s) >= 120);
  const appOf = (s) => applianceLabel(alt(s) ? alt(s).appliance : s.appliance);
  const durOf = (s) => (alt(s) ? durationLabel(alt(s)) : durationLabel(s));
  const set = (s, patch) => { session.steps[s.id] = { ...st(s), ...patch }; commit(); };

  function start(s) {
    unlock();
    const t = needsTimer(s) ? timerOf(s) : null;
    if (t) set(s, { status: "running", startedAt: Date.now(), endsAt: Date.now() + t * 1000 });
    else set(s, { status: "done", doneAt: Date.now() });
  }
  const done = (s) => set(s, { status: "done", doneAt: Date.now() });
  function undo(s) {
    const a = st(s).alt;
    session.steps[s.id] = a != null ? { status: "pending", alt: a } : { status: "pending" };
    commit();
  }
  function addMinute(s) {
    const cur = st(s);
    set(s, { endsAt: Math.max(cur.endsAt || Date.now(), Date.now()) + MIN * 1000 });
  }
  const useAlt = (s, i) => set(s, { alt: st(s).alt === i ? null : i });
  function commit() {
    save();
    if (!anyRinging()) silence();
    render();
  }

  // -- your own timers (not tied to a step) --------------------------------------
  function addTimer(name, seconds) {
    unlock();
    const t = Date.now();
    session.timers.push({ id: `t${t}`, name, startedAt: t, endsAt: t + seconds * 1000 });
    commit();
  }
  const timerById = (id) => session.timers.find((x) => x.id === id);
  function extendTimer(id) {
    const x = timerById(id);
    if (x) x.endsAt = Math.max(x.endsAt, Date.now()) + MIN * 1000;
    commit();
  }
  function removeTimer(id) {
    session.timers = session.timers.filter((x) => x.id !== id);
    commit();
  }

  // -- what is happening ------------------------------------------------------
  const now = () => Date.now();
  const isRinging = (s) => st(s).status === "running" && st(s).endsAt && st(s).endsAt <= now();
  const ringingSteps = () => steps.filter(isRinging);
  const ringingTimers = () => session.timers.filter((x) => x.endsAt <= now());
  const anyRinging = () => ringingSteps().length > 0 || ringingTimers().length > 0;

  /** The one step that needs you most, and why. */
  function current() {
    const t = now();
    const ringing = ringingSteps();
    if (ringing.length) return { step: ringing[0], kind: "ring" };
    const active = steps.find((s) => st(s).status === "running" && s.mode === "active" && !isRinging(s));
    if (active) return { step: active, kind: "active" };
    const waiting = steps.filter((s) => st(s).status === "pending");
    if (!waiting.length) return null;
    const due = waiting.find((s) => s.start.getTime() <= t + DUE_SOON_MS);
    return due ? { step: due, kind: "due" } : { step: waiting[0], kind: "next" };
  }

  function lateMs() {
    const first = steps.find((s) => st(s).status === "pending");
    return first ? Math.max(0, now() - first.start.getTime()) : 0;
  }

  // -- rendering ----------------------------------------------------------------
  const page = h("div", { class: "cook" });
  root.append(page);
  let signature = "";

  function sig() {
    const cur = current();
    const late = lateMs() > MIN * 1000 ? Math.floor(lateMs() / MIN / 1000) : 0;
    const ringing = [...ringingSteps().map((s) => s.id), ...ringingTimers().map((x) => x.id)];
    return [cur && cur.step.id, cur && cur.kind, ringing.join(","), late].join("|");
  }

  function render() {
    signature = sig();
    const cur = current();
    const ingPanel = ingredientsPanel(cur);
    fill(page,
      header(),
      timeline(cur),
      h("div", { class: "ck-body" },
        ingPanel,
        panelOpen ? h("div", { class: "ck-scrim", onclick: () => togglePanel(false) }) : null,
        stepList(cur),
        timersPanel(cur)));
    tick(true);
    const id = cur ? cur.step.id : "plate";
    if (id !== lastCurrent) {
      lastCurrent = id;
      requestAnimationFrame(() => page.querySelector(`[data-step="${id}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" }));
    }
  }

  function header() {
    const late = lateMs() > MIN * 1000;
    const shown = new Date(plate.getTime() + (late ? lateMs() : 0));
    return h("header", { class: "ck-head" },
      h("a", { class: "ck-x", href: `/r/${slug}`, "aria-label": "Leave cook mode" }, icon("close", 20, { stroke: 2.2 })),
      h("button", { type: "button", class: "ck-tog", "aria-pressed": String(panelOpen), "aria-label": "Ingredients", onclick: () => togglePanel() },
        listIcon(), h("span", { class: "lbl" }, "Ingredients")),
      h("div", { class: "ck-title" }, dishes.map((d, i) => [i ? h("span", { class: "plus" }, " + ") : null, d.title])),
      h("div", { class: "ck-clock num", dataset: { clock: "1" } }, clock(new Date())),
      h("div", { class: `ck-plate${late ? " late" : ""}` },
        h("div", { class: "k" }, late ? `${human(lateMs() / 1000)} late` : `Plate ${clock(plate, { ampm: false })}`),
        h("div", { class: "v num", dataset: late ? {} : { until: plate.getTime() } },
          late ? clock(shown) : until(Math.max(0, (plate - now()) / 1000)))));
  }

  function timeline(cur) {
    const t0 = Math.min(...steps.map((s) => s.start.getTime()));
    const t1 = plate.getTime();
    const span = Math.max(t1 - t0, MIN * 1000);
    const pct = (t) => `${Math.max(0, Math.min(100, ((t - t0) / span) * 100))}%`;
    const stepMin = [5, 10, 15, 30, 60, 120, 240].find((m) => span / (m * 60000) <= 8) || 480;
    const ticks = [];
    for (let t = Math.ceil(t0 / (stepMin * 60000)) * stepMin * 60000; t < t1 - stepMin * 30000; t += stepMin * 60000) ticks.push(t);
    const laneW = dishes.length > 1 ? "112px" : "0px";

    const lanes = dishes.map((d) => {
      const mine = steps.filter((s) => s.dish === d && s.end > s.start);
      const rows = packRows(mine, (s) => [s.start.getTime() / 1000, s.end.getTime() / 1000]);
      return h("div", { class: "ck-lane" },
        dishes.length > 1 ? h("div", { class: "name" }, h("span", { class: "dot", style: { width: "10px", height: "10px", "border-radius": "5px", background: d.color.c } }), h("span", {}, d.title)) : null,
        h("div", { class: "track", style: { height: `${rows.length * 32 - 6}px` } },
          rows.flatMap((row, r) => row.map((s) => {
            const w = ((s.end - s.start) / span) * 100;
            const state = cur && cur.step === s ? "cur" : st(s).status === "done" ? "done" : "";
            return h("button", {
              type: "button", class: `ck-blk ${state}`,
              style: { left: pct(s.start.getTime()), width: `calc(${w}% - 2px)`, top: `${r * 32}px`, "--dish": d.color.c, "--dish-ink": d.color.ink },
              title: `${clock(s.start)} · ${s.lead}`, "aria-label": `${clock(s.start)}, ${s.lead}`,
              onclick: () => page.querySelector(`[data-step="${s.id}"]`)?.scrollIntoView({ block: "start", behavior: "smooth" }),
            }, w > 7 ? shortName(s.lead) : "");
          }))));
    });

    return h("section", { class: "ck-line", style: { "--lane-w": laneW }, "aria-label": "Timeline" },
      h("div", { class: "ticks num", "aria-hidden": "true" },
        ticks.map((t) => h("span", { style: { left: pct(t) } }, clock(new Date(t), { ampm: false }))),
        h("span", { style: { left: "100%" } }, "Plate")),
      h("div", { class: "lanes" }, lanes,
        h("div", { class: "ck-needle", "aria-hidden": "true", dataset: { t0, span } },
          h("div", { class: "bar" }), h("div", { class: "lbl num" }, clock(new Date(), { ampm: false })))));
  }

  function ingredientsPanel(cur) {
    const using = new Set(cur ? cur.step.uses : []);
    const groups = [];
    for (const d of dishes) {
      let group = null;
      for (const ing of d.ingredients) {
        const title = [dishes.length > 1 ? d.title : null, ing.group].filter(Boolean).join(" · ") || (dishes.length > 1 ? d.title : "");
        if (!group || group.title !== title) { group = { title, dish: d, items: [] }; groups.push(group); }
        group.items.push(ing);
      }
    }
    return h("aside", { class: "ck-ing ck-scroll", hidden: !panelOpen, "aria-label": "Ingredients" },
      groups.map((g) => h("section", { class: "ck-grp", style: { "--dish": g.dish.color.c } },
        g.title ? h("h3", {}, dishes.length > 1 ? h("span", { class: "dot" }) : null, g.title) : null,
        g.items.map((ing) => h("button", {
          type: "button", class: `ck-item${using.has(ing.key) ? " use" : ""}`, "aria-pressed": String(Boolean(session.have[ing.key])),
          onclick: () => { session.have[ing.key] = !session.have[ing.key]; save(); render(); },
        },
          h("span", { class: "bx", "aria-hidden": "true" }, icon("check", 11, { stroke: 3.6 })),
          h("span", { class: "amt num" }, ing.amount),
          h("span", { class: "nm" }, ing.name, ing.note ? h("span", { class: "note" }, ` (${ing.note})`) : null))))));
  }

  function stepList(cur) {
    const nextPending = steps.find((s) => st(s).status === "pending" && (!cur || s !== cur.step));
    const allDone = steps.every((s) => st(s).status === "done");
    const items = [];
    for (const s of steps) items.push(stepRow(s, cur, nextPending));
    items.push(allDone ? finishRow() : h("li", { class: "ck-plate-row", "data-step": "plate" },
      h("span", { class: "when num" }, clock(plate)), h("span", { class: "serif" }, "Plate")));
    return h("ol", { class: "ck-steps ck-scroll", "aria-label": "Steps" }, items);
  }

  function stepRow(s, cur, nextPending) {
    const state = st(s);
    const isCur = Boolean(cur && cur.step === s);
    const isDone = state.status === "done";
    const app = appOf(s);
    const meta = [dishes.length > 1 ? s.dish.title : null, durOf(s), s.mode === "active" ? "hands-on" : "hands-off", app].filter(Boolean).join(" · ");
    return h("li", {
      class: `ck-step${isCur ? " cur" : ""}${isDone && !isCur ? " done" : ""}`,
      "data-step": s.id, style: { "--dish": s.dish.color.c },
      "aria-current": isCur ? "step" : null,
    },
      h("button", {
        type: "button", class: "ck", "aria-pressed": String(isDone),
        "aria-label": `${isDone ? "Mark not done" : "Mark done"}: ${s.lead}`,
        onclick: () => (isDone ? undo(s) : done(s)),
      }, icon("check", 15, { stroke: 3.2 })),
      h("div", { class: "when num" },
        h("span", {}, clock(s.start, { ampm: false })),
        s === nextPending && s.start.getTime() > now() ? h("span", { class: "soon", dataset: { until: s.start.getTime() } }, until(Math.max(0, (s.start - now()) / 1000))) : null),
      h("div", { class: "main" },
        h("div", { class: "meta" },
          isCur ? h("span", { class: "ck-now" }, cur.kind === "next" ? "Next" : "Now") : null,
          dishes.length > 1 ? h("span", { class: "dot" }) : null,
          meta),
        h("div", { class: "txt" }, h("span", { class: "lead" }, inline(s.lead)), s.body ? " " : null, inline(s.body)),
        isCur && state.status === "pending" ? s.fallbacks.map((f, i) => h("div", { class: "alt" }, icon("swap", 16),
          state.alt === i
            ? [`Using ${applianceLabel(f.appliance)}`, h("button", { type: "button", class: "linkbtn", onclick: () => useAlt(s, i) }, `Back to ${applianceLabel(s.appliance)}`)]
            : [`Or ${applianceLabel(f.appliance)}${f.durationS ? ` · ${durationLabel(f)}` : ""}`, h("button", { type: "button", class: "linkbtn", onclick: () => useAlt(s, i) }, "Use it")])) : null,
        isCur && !panelOpen && s.uses.length ? h("div", { class: "ck-chips" }, s.uses.map((key) => {
          const ing = s.dish.ingredients.find((x) => x.key === key);
          return h("span", { class: "ck-chip" }, ing.amount ? h("b", { class: "num" }, ing.amount) : null, ing.name);
        })) : null,
        isCur ? actionBar(cur) : null));
  }

  function actionBar(cur) {
    const s = cur.step;
    const state = st(s);
    let big, small, label, act;
    if (cur.kind === "ring") {
      big = "Time’s up"; small = `${s.lead.replace(/\.$/, "")} is done`; label = "Done"; act = () => done(s);
    } else if (cur.kind === "active") {
      big = h("span", { dataset: { end: state.endsAt, suffix: " left" } }, `${countdown((state.endsAt - now()) / 1000)} left`);
      small = `Done by ${clock(new Date(state.endsAt))}`; label = "Done"; act = () => done(s);
    } else {
      const timed = needsTimer(s);
      if (cur.kind === "next") {
        big = h("span", { dataset: { until: s.start.getTime() } }, until(Math.max(0, (s.start - now()) / 1000)));
        small = `Starts at ${clock(s.start)}`;
      } else {
        big = timed ? countdown(timerOf(s)) : "";
        small = timed ? `${s.mode === "active" ? "Timer" : "Runs on its own"} once you start` : "";
      }
      label = timed ? "Start" : "Done";
      act = () => start(s);
    }
    return h("div", { class: "ck-act" },
      h("div", { class: "grow" }, big ? h("div", { class: "big num" }, big) : null, small ? h("div", { class: "small num" }, small) : null),
      h("button", { type: "button", class: "btn btn-pri", onclick: act }, label));
  }

  function timersPanel(cur) {
    const fromSteps = steps
      .filter((s) => st(s).status === "running" && st(s).endsAt && !(cur && cur.step === s))
      .map((s) => ({
        key: s.id, name: s.lead.replace(/\.$/, ""), color: s.dish.color.c, ...pick(st(s)),
        more: () => addMinute(s), end: () => done(s), endLabel: "Done", ringing: isRinging(s),
      }));
    const mine = session.timers.map((x) => ({
      key: x.id, name: x.name, color: "#173E32", ...pick(x),
      more: () => extendTimer(x.id), end: () => removeTimer(x.id), endLabel: "Stop", ringing: x.endsAt <= now(),
    }));
    const all = [...fromSteps, ...mine].sort((a, b) => a.endsAt - b.endsAt);
    return h("aside", { class: "ck-timers ck-scroll", "aria-label": "Timers" },
      all.map(timerTile),
      h("button", { type: "button", class: "ck-new", onclick: timerDialog }, icon("plus", 18, { stroke: 2.4 }), "Timer"));
  }
  const pick = ({ startedAt, endsAt }) => ({ startedAt, endsAt });

  function timerTile(t) {
    return h("div", { class: `ck-tmr${t.ringing ? " ring" : ""}` },
      ringSvg(t.color, t.startedAt, t.endsAt),
      h("div", { class: "info" },
        h("div", { class: "name" }, t.name),
        h("div", { class: "left num", dataset: { end: t.endsAt, done: "Time’s up" } }, t.ringing ? "Time’s up" : countdown((t.endsAt - now()) / 1000)),
        h("div", { class: "sub num" }, `Ends ${clock(new Date(t.endsAt))}`)),
      h("div", { class: "acts" },
        h("button", { type: "button", onclick: t.more }, "+1 min"),
        t.ringing || t.endLabel === "Stop"
          ? h("button", { type: "button", class: t.ringing ? "solid" : "", onclick: t.end }, t.ringing ? "Done" : t.endLabel)
          : null));
  }

  function timerDialog() {
    let minutes = 5;
    const name = h("input", { id: "tmr-name", type: "text", placeholder: "Name", autocomplete: "off", enterkeyhint: "go" });
    const minIn = h("input", { id: "tmr-min", type: "number", inputmode: "numeric", min: 0, max: 600, value: minutes, "aria-label": "Minutes" });
    const secIn = h("input", { id: "tmr-sec", type: "number", inputmode: "numeric", min: 0, max: 59, value: 0, "aria-label": "Seconds" });
    const presets = TIMER_PRESETS.map((m) => h("button", {
      type: "button", "aria-pressed": String(m === minutes),
      onclick: () => { minIn.value = m; secIn.value = 0; syncPresets(); },
    }, `${m}`));
    function syncPresets() {
      const m = Number(minIn.value), sec = Number(secIn.value) || 0;
      TIMER_PRESETS.forEach((p, i) => presets[i].setAttribute("aria-pressed", String(!sec && p === m)));
    }
    minIn.addEventListener("input", syncPresets);
    secIn.addEventListener("input", syncPresets);

    const close = () => { document.removeEventListener("keydown", onKey); backdrop.remove(); };
    const onKey = (e) => { if (e.key === "Escape") close(); };
    document.addEventListener("keydown", onKey);
    const backdrop = h("div", { class: "dialog-backdrop", onclick: (e) => { if (e.target === backdrop) close(); } },
      h("form", {
        class: "dialog ck-dlg", role: "dialog", "aria-modal": "true", "aria-labelledby": "tmr-h",
        onsubmit: (e) => {
          e.preventDefault();
          const secs = Math.max(0, Number(minIn.value) || 0) * MIN + Math.max(0, Math.min(59, Number(secIn.value) || 0));
          if (!secs) { minIn.focus(); return; }
          addTimer(name.value.trim() || `${human(secs)} timer`, secs);
          close();
        },
      },
        h("h2", { id: "tmr-h" }, "New timer"),
        h("label", { for: "tmr-name", class: "sr-only" }, "Name"), name,
        h("div", { class: "ck-presets", role: "group", "aria-label": "Minutes" }, presets),
        h("div", { class: "ck-dur num" }, minIn, h("span", {}, "min"), secIn, h("span", {}, "sec")),
        h("div", { class: "row" },
          h("button", { type: "button", class: "btn btn-sec", onclick: close }, "Cancel"),
          h("button", { type: "submit", class: "btn btn-pri" }, "Start"))));
    document.body.append(backdrop);
    name.focus();
  }

  function finishRow() {
    return h("li", { class: "ck-step cur", "data-step": "plate", style: { "--dish": "var(--sage)" } },
      h("div", { class: "main" },
        h("div", { class: "txt" }, h("span", { class: "lead" }, "Plate it.")),
        h("div", { class: "ck-act" },
          h("div", { class: "grow" }),
          h("button", { type: "button", class: "btn btn-sec", onclick: finish }, "Close"),
          h("button", { type: "button", class: "btn btn-pri", onclick: logDialog }, "Log this cook"))));
  }

  // -- the clock ------------------------------------------------------------------
  function tick(skipCheck = false) {
    if (!skipCheck && sig() !== signature) { render(); return; }
    const t = now();
    for (const el of page.querySelectorAll("[data-end]")) {
      const left = (Number(el.dataset.end) - t) / 1000;
      el.textContent = left <= 0 && el.dataset.done ? el.dataset.done : countdown(left) + (el.dataset.suffix || "");
    }
    for (const el of page.querySelectorAll("[data-until]")) el.textContent = until(Math.max(0, (Number(el.dataset.until) - t) / 1000));
    for (const el of page.querySelectorAll("[data-ring]")) {
      const [from, to] = el.dataset.ring.split(",").map(Number);
      el.setAttribute("stroke-dashoffset", String(RING_C * Math.max(0, Math.min(1, (to - t) / (to - from)))));
    }
    const c = page.querySelector("[data-clock]");
    if (c) c.textContent = clock(new Date(t));
    const needle = page.querySelector(".ck-needle");
    if (needle) {
      const t0 = Number(needle.dataset.t0), span = Number(needle.dataset.span);
      const left = `${Math.max(0, Math.min(100, ((t - t0) / span) * 100))}%`;
      needle.style.display = t < t0 || t > t0 + span ? "none" : "";
      for (const el of needle.children) el.style.left = left;
      needle.lastChild.textContent = clock(new Date(t), { ampm: false });
    }
    const ringingNow = [...ringingSteps().map((s) => s.lead), ...ringingTimers().map((x) => x.name)];
    if (ringingNow.length) ring(ringingNow.join(" · "));
  }

  // -- panel, finishing ------------------------------------------------------------
  function togglePanel(open = !panelOpen) {
    panelOpen = open;
    try { localStorage.setItem(PANEL_KEY, open ? "1" : "0"); } catch { /* private mode */ }
    render();
  }

  function finish() {
    try { localStorage.removeItem(sessionKey(slug)); } catch { /* ignore */ }
    navigate(`/r/${slug}`);
  }

  function logDialog() {
    const note = h("textarea", { id: "log-note", placeholder: "Note", rows: 3 });
    const close = () => backdrop.remove();
    const backdrop = h("div", { class: "dialog-backdrop", onclick: (e) => { if (e.target === backdrop) close(); } },
      h("form", {
        class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "log-h",
        onsubmit: async (e) => {
          e.preventDefault();
          await api.logCook(slug, { servings: session.servings, note: note.value });
          close();
          finish();
        },
      },
        h("h2", { id: "log-h" }, "Log this cook"),
        h("label", { for: "log-note", class: "sr-only" }, "Note"), note,
        h("div", { class: "row" },
          h("button", { type: "button", class: "btn btn-sec", onclick: close }, "Cancel"),
          h("button", { type: "submit", class: "btn btn-pri" }, "Save"))));
    document.body.append(backdrop);
    note.focus();
  }

  render();
  const timer = setInterval(() => tick(), 250);
  const onVisible = () => { if (!document.hidden) tick(); };
  document.addEventListener("visibilitychange", onVisible);

  return () => {
    clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisible);
    stayAwake(false);
    silence();
    document.querySelector(".dialog-backdrop")?.remove();
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RING_C = 163.36; // circumference for r = 26

function ringSvg(color, from, to) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("width", "52"); svg.setAttribute("height", "52");
  svg.setAttribute("viewBox", "0 0 64 64"); svg.setAttribute("aria-hidden", "true");
  const base = { cx: 32, cy: 32, r: 26, fill: "none", "stroke-width": 6 };
  const track = document.createElementNS(SVG_NS, "circle");
  for (const [k, v] of Object.entries({ ...base, stroke: "#EFE6D2" })) track.setAttribute(k, v);
  const arc = document.createElementNS(SVG_NS, "circle");
  const left = Math.max(0, Math.min(1, (to - Date.now()) / (to - from)));
  for (const [k, v] of Object.entries({
    ...base, stroke: color, "stroke-linecap": "round", "stroke-dasharray": RING_C,
    "stroke-dashoffset": RING_C * left, transform: "rotate(-90 32 32)", "data-ring": `${from},${to}`,
  })) arc.setAttribute(k, v);
  svg.append(track, arc);
  return svg;
}

function listIcon() {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("width", "18"); svg.setAttribute("height", "18"); svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true"); svg.setAttribute("fill", "none"); svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2"); svg.setAttribute("stroke-linecap", "round");
  const p = document.createElementNS(SVG_NS, "path");
  p.setAttribute("d", "M9 6h11M9 12h11M9 18h11M4.5 6h.01M4.5 12h.01M4.5 18h.01");
  svg.append(p);
  return svg;
}

function loadPanelPref() {
  try {
    const v = localStorage.getItem(PANEL_KEY);
    if (v !== null) return v === "1";
  } catch { /* private mode */ }
  return window.matchMedia("(min-width: 900px)").matches;
}

/** "Heat the oven to 400°F." -> "Heat the oven" for a timeline block. */
function shortName(lead) {
  const text = lead.replace(/[.*_`]/g, "").trim();
  const words = text.split(/\s+/);
  return words.length <= 3 ? text : words.slice(0, 3).join(" ");
}

const SKIP = new Set(["fresh", "large", "small", "medium", "whole", "ground", "dried", "chopped", "sliced", "minced", "unsalted", "salted", "extra", "virgin", "kosher", "black", "white", "dry", "light", "dark", "boneless", "skinless", "the", "and", "for"]);

/**
 * Which ingredients a step mentions, so the panel can light them up.
 * A full name match wins; otherwise the head noun ("potatoes") is used,
 * unless several ingredients share it ("salt") and none is named in full.
 */
function ingredientsUsed(step, ingredients) {
  const text = ` ${`${step.lead} ${step.body || ""}`.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ")} `;
  const has = (w) => w && text.includes(` ${w} `);
  const variants = (w) => [w, w.endsWith("es") ? w.slice(0, -2) : null, w.endsWith("s") ? w.slice(0, -1) : `${w}s`];
  const full = [];
  const byHead = new Map();
  for (const ing of ingredients) {
    const words = (ing.item || ing.name || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").split(/\s+/).filter(Boolean);
    if (!words.length) continue;
    if (words.length > 1 && has(words.join(" "))) { full.push(ing.key); continue; }
    const head = words[words.length - 1];
    if (SKIP.has(head) || head.length < 3) continue;
    if (variants(head).some(has)) {
      if (!byHead.has(head)) byHead.set(head, []);
      byHead.get(head).push(ing.key);
    }
  }
  const out = new Set(full);
  const noteHits = (key) => {
    const ing = ingredients.find((x) => x.key === key);
    const words = (ing.note || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").split(/\s+/)
      .filter((w) => w.length > 3 && !SKIP.has(w));
    return words.some((w) => variants(w).some(has));
  };
  for (const keys of byHead.values()) {
    if (keys.some((k) => out.has(k))) continue;
    if (keys.length === 1) { out.add(keys[0]); continue; }
    // "salt" with kosher and sea salt: the one "for the onions" wins in the onion step.
    const hinted = keys.filter(noteHits);
    if (hinted.length) hinted.forEach((k) => out.add(k));
  }
  return [...out];
}
