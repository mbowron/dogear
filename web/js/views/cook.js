// Cook mode: what needs your hands now, running timers, what's next, and
// every step. Progress is saved in localStorage so a reload or a locked
// screen picks up where you left off.

import { h, fill, icon, inline } from "../dom.js";
import { api } from "../api.js";
import { clock, countdown, until, durationLabel, human, MIN } from "../time.js";
import { readPlan, timedSteps, packRows, applianceLabel } from "../plan.js";
import { unlock, ring, silence, stayAwake } from "../alarm.js";
import { setTitle } from "./common.js";
import { navigate } from "../app.js";

const DUE_SOON_MS = 30 * 1000;
const STALE_MS = 12 * 3600 * 1000;

export function sessionKey(slug) { return `dogear.cook.${slug}`; }

export function savedSession(slug) {
  try {
    const s = JSON.parse(localStorage.getItem(sessionKey(slug)));
    if (s && s.v === 1 && s.plate > Date.now() - STALE_MS) return s;
  } catch { /* none */ }
  return null;
}

export async function mount(root, [slug], query) {
  const hasPlan = query.has("plate") || query.get("start") === "now";
  let session = query.get("restart") ? null : savedSession(slug);
  if (session && hasPlan && !query.get("resume")) session = null;

  const servingsWanted = session ? session.servings : query.get("servings");
  const data = await api.recipe(slug, servingsWanted);
  const recipe = data.recipe;
  if (!recipe) { navigate(`/r/${slug}`, { replace: true }); return; }
  setTitle(recipe.title);

  if (!session) {
    const plan = readPlan(recipe, query);
    session = { v: 1, slug, plate: plan.plate.getTime(), servings: data.view.servings, steps: {} };
  }
  const save = () => { try { localStorage.setItem(sessionKey(slug), JSON.stringify(session)); } catch { /* full */ } };
  save();
  history.replaceState(null, "", `/cook/${slug}`);

  document.body.className = "night";
  stayAwake(true);

  const plate = new Date(session.plate);
  const steps = timedSteps(recipe, plate).map((s) => ({ ...s, id: s.number }));
  let open = null; // step number expanded in the list

  // -- state helpers --------------------------------------------------------
  const st = (s) => session.steps[s.number] || { status: "pending" };
  const alt = (s) => (st(s).alt != null ? s.fallbacks[st(s).alt] : null);
  const timerOf = (s) => {
    const a = alt(s);
    if (a) return a.durationMinS || a.durationS || s.timerS;
    return s.timerS;
  };
  // Short hands-on steps are just done; everything else gets a timer.
  const needsTimer = (s) => Boolean(timerOf(s)) && (s.mode !== "active" || timerOf(s) >= 120);
  const appOf = (s) => applianceLabel(alt(s) ? alt(s).appliance : s.appliance);
  const durOf = (s) => (alt(s) ? durationLabel(alt(s)) : durationLabel(s));

  function start(s) {
    unlock();
    const t = needsTimer(s) ? timerOf(s) : null;
    if (!t) {
      session.steps[s.number] = { ...st(s), status: "done", doneAt: Date.now() };
    } else {
      session.steps[s.number] = { ...st(s), status: "running", startedAt: Date.now(),
        endsAt: t ? Date.now() + t * 1000 : null };
    }
    commit();
  }
  function done(s) {
    session.steps[s.number] = { ...st(s), status: "done", doneAt: Date.now() };
    commit();
  }
  function undo(s) {
    const { alt: a } = st(s);
    session.steps[s.number] = a != null ? { status: "pending", alt: a } : { status: "pending" };
    commit();
  }
  function addMinute(s) {
    const cur = st(s);
    const base = Math.max(cur.endsAt || Date.now(), Date.now());
    session.steps[s.number] = { ...cur, endsAt: base + MIN * 1000 };
    commit();
  }
  function useAlt(s, index) {
    session.steps[s.number] = { ...st(s), alt: st(s).alt === index ? null : index };
    commit();
  }
  function commit() {
    save();
    if (!ringingSteps().length) silence();
    render();
  }

  // -- derived lists --------------------------------------------------------
  const now = () => Date.now();
  const ringingSteps = () => steps.filter((s) => st(s).status === "running" && st(s).endsAt && st(s).endsAt <= now());
  const pending = () => steps.filter((s) => st(s).status === "pending");
  function view() {
    const t = now();
    const ringing = ringingSteps();
    const runActive = steps.filter((s) => st(s).status === "running" && s.mode === "active" && !ringing.includes(s));
    const runPassive = steps.filter((s) => st(s).status === "running" && s.mode !== "active" && !ringing.includes(s));
    const waiting = pending();
    let due = waiting.filter((s) => s.start.getTime() <= t + DUE_SOON_MS);
    let next = [];
    if (!ringing.length && !runActive.length && !due.length && waiting.length) {
      const first = waiting[0].start.getTime();
      next = waiting.filter((s) => s.start.getTime() === first);
    }
    // Don't pile every overdue step into Now: the first two are enough.
    if (due.length > 2) due = due.slice(0, 2);
    const shown = new Set([...due, ...next].map((s) => s.number));
    const coming = waiting.filter((s) => !shown.has(s.number)).slice(0, 3);
    const lateMs = waiting.length ? Math.max(0, t - waiting[0].start.getTime()) : 0;
    return { ringing, runActive, runPassive, due, next, coming, lateMs, allDone: !waiting.length && !runActive.length && !runPassive.length && !ringing.length };
  }

  // -- rendering ------------------------------------------------------------
  const page = h("div", { class: "cook" });
  root.append(page);
  let signature = "";

  function render() {
    const v = view();
    signature = sig(v);
    const doneCount = steps.filter((s) => st(s).status === "done").length;
    const late = v.lateMs > MIN * 1000;
    const projected = new Date(plate.getTime() + (late ? v.lateMs : 0));

    const head = h("header", { class: "cook-head" },
      h("a", { class: "x", href: `/r/${slug}`, "aria-label": "Leave cook mode" }, icon("close", 20, { stroke: 2.2 })),
      h("div", { class: "title" },
        h("div", { class: "name" }, recipe.title),
        h("div", { class: "sub num" }, `${data.view.yieldLabel} · ${doneCount} of ${steps.length} done`)),
      h("div", { class: "now" }, h("div", { class: "t num", dataset: { clock: "1" } }, clock(new Date()))),
      h("div", { class: `plate-pill${late ? " late" : ""}` },
        h("div", { class: "k" }, late ? `${human(v.lateMs)} late` : "Plate at"),
        h("div", { class: "v num" }, clock(projected))));

    const nowCards = [
      ...v.ringing.map((s) => nowCard(s, "ring")),
      ...v.runActive.map((s) => nowCard(s, "active")),
      ...v.due.map((s) => nowCard(s, "due")),
      ...v.next.map((s) => nowCard(s, "next")),
    ];

    const main = h("div", { class: "cook-col main" },
      h("section", { "aria-labelledby": "now-h" },
        h("h2", { id: "now-h", class: "eyebrow" }, "Now"),
        nowCards.length ? nowCards : finished(v)),
      v.runPassive.length ? h("section", { "aria-labelledby": "run-h" },
        h("h2", { id: "run-h", class: "eyebrow" }, "Running"),
        h("div", { class: "timers" }, v.runPassive.map(timerCard))) : null,
      v.coming.length ? h("section", { class: "hide-phone", "aria-labelledby": "next-h" },
        h("h2", { id: "next-h", class: "eyebrow" }, "Coming up"),
        h("div", { class: "upnext" }, v.coming.map((s) => h("div", {},
          h("span", { class: "t num" }, clock(s.start)),
          h("span", { class: "l" }, s.lead),
          h("span", { class: "in num", dataset: { until: s.start.getTime() } }, until((s.start - now()) / 1000)))))) : null);

    const side = h("div", { class: "cook-col side" }, everyStep(v));

    const primary = nowCards.length ? primaryAction(v) : null;
    fill(page, head, stripEl(), h("div", { class: "cook-body" }, main, side),
      primary ? h("div", { class: "cook-foot" }, primary) : null);
    tick(true);
  }

  function sig(v) {
    const ids = (list) => list.map((s) => s.number).join(",");
    return [ids(v.ringing), ids(v.due), ids(v.next), ids(v.coming), v.lateMs > MIN * 1000 ? Math.floor(v.lateMs / MIN / 1000) : 0].join("|");
  }

  function nowCard(s, kind) {
    const state = st(s);
    const app = appOf(s);
    const dur = durOf(s);
    const cls = kind === "ring" ? "now-card ring" : kind === "next" ? "now-card next" : "now-card";
    let when;
    if (kind === "ring") when = "Time’s up";
    else if (kind === "next") when = `${clock(s.start)} · `;
    else when = `${clock(s.start)}–${clock(s.end)}`;

    const actions = [];
    let bigLine = null;
    if (kind === "ring") {
      actions.push(h("button", { type: "button", class: "btn btn-pri", onclick: () => done(s) }, icon("check", 20, { stroke: 2.8 }), "Done"));
      actions.push(h("button", { type: "button", class: "btn btn-sec", style: { "box-shadow": "inset 0 0 0 1.5px #1A1D19", color: "#1A1D19" }, onclick: () => addMinute(s) }, "+1 min"));
    } else if (kind === "active") {
      if (state.endsAt) bigLine = h("div", { class: "left" },
        h("div", { class: "big num", dataset: { end: state.endsAt } }, `${countdown((state.endsAt - now()) / 1000)} left`));
      actions.push(h("button", { type: "button", class: "btn btn-gold", onclick: () => done(s) }, icon("check", 20, { stroke: 2.8 }), "Done"));
    } else {
      const hasTime = needsTimer(s);
      actions.push(h("button", { type: "button", class: "btn btn-gold", onclick: () => start(s) },
        icon(hasTime ? "play" : "check", 20, { stroke: 2.8 }), hasTime ? "Start" : "Done"));
    }

    return h("div", { class: cls },
      h("div", { class: "top" },
        h("span", { class: "when num" }, when, kind === "next" ? h("span", { dataset: { until: s.start.getTime() } }, until((s.start - now()) / 1000)) : null),
        h("span", { class: "eyebrow", style: { color: "inherit", opacity: ".8" } }, `Step ${s.number}`)),
      h("div", { class: "lead" }, inline(s.lead)),
      s.body ? h("div", { class: "body" }, inline(s.body)) : null,
      dur || app ? h("div", { class: "pills" },
        dur ? h("span", { class: "pill" }, `${dur} · ${s.mode === "active" ? "hands-on" : "hands-off"}`) : null,
        app ? h("span", { class: "pill app" }, app) : null) : null,
      kind !== "ring" && kind !== "active" && state.status === "pending" ? s.fallbacks.map((f, i) =>
        h("div", { class: "alt" }, icon("swap", 16),
          st(s).alt === i
            ? [`Using ${applianceLabel(f.appliance)}`, h("button", { type: "button", class: "linkbtn", onclick: () => useAlt(s, i) }, `Back to ${applianceLabel(s.appliance)}`)]
            : [`Or ${applianceLabel(f.appliance)}${f.durationS ? ` · ${durationLabel(f)}` : ""}`,
               h("button", { type: "button", class: "linkbtn", onclick: () => useAlt(s, i) }, "Use it")])) : null,
      h("div", { class: "foot" }, bigLine || h("div", { class: "left" }), actions));
  }

  function timerCard(s) {
    const state = st(s);
    const label = s.lead.replace(/\.$/, "");
    if (!state.endsAt) {
      return h("div", { class: "tcard" },
        h("div", { class: "t1" }, h("span", { class: "label" }, label)),
        h("div", { class: "ends" }, `Since ${clock(new Date(state.startedAt))}`),
        h("div", { class: "tb" }, h("button", { type: "button", class: "solid", onclick: () => done(s) }, "Done")));
    }
    const total = state.endsAt - state.startedAt;
    return h("div", { class: "tcard" },
      h("div", { class: "t1" }, h("span", { class: "label" }, label),
        h("div", { class: "tb" },
          h("button", { type: "button", onclick: () => addMinute(s), "aria-label": `Add a minute to ${label}` }, "+1 min"),
          h("button", { type: "button", class: "solid", onclick: () => done(s) }, "Done"))),
      h("div", { class: "left num", dataset: { end: state.endsAt } }, countdown((state.endsAt - now()) / 1000)),
      h("div", { class: "bar" }, h("span", { dataset: { from: state.startedAt, to: state.endsAt }, style: { width: `${Math.min(100, ((now() - state.startedAt) / total) * 100)}%` } })),
      h("div", { class: "ends num" }, `Ends ${clock(new Date(state.endsAt))}`));
  }

  function finished(v) {
    if (!v.allDone) return h("div", { class: "idle" }, h("div", { class: "h" }, "Waiting on the timers"));
    return h("div", { class: "idle" },
      h("div", { class: "h" }, "Plate it"),
      h("div", { class: "row" },
        h("button", { type: "button", class: "btn btn-gold", onclick: logDialog }, "Log this cook"),
        h("button", { type: "button", class: "btn btn-sec", style: { color: "var(--cream)", "box-shadow": "inset 0 0 0 1.5px var(--cream)" }, onclick: finish }, "Close")));
  }

  function primaryAction(v) {
    const s = v.ringing[0] || v.runActive[0] || v.due[0] || v.next[0];
    if (!s) return null;
    const running = st(s).status === "running";
    const hasTime = needsTimer(s);
    return h("button", {
      type: "button", class: "btn btn-gold btn-lg", onclick: () => (running ? done(s) : start(s)),
    }, running ? `Done · step ${s.number}` : hasTime ? `Start step ${s.number}` : `Done · step ${s.number}`);
  }

  function everyStep(v) {
    const nowIds = new Set([...v.ringing, ...v.runActive, ...v.due].map((s) => s.number));
    return h("section", { class: "all", "aria-labelledby": "all-h" },
      h("div", { class: "h" }, h("h2", { id: "all-h" }, "Every step"),
        h("span", { class: "num" }, `${steps.filter((s) => st(s).status === "done").length} of ${steps.length}`)),
      h("ol", {}, steps.map((s) => {
        const state = st(s);
        const isDone = state.status === "done";
        const isNow = nowIds.has(s.number);
        const expanded = open === s.number;
        const meta = [durOf(s), s.mode === "active" ? "hands-on" : "hands-off", appOf(s)].filter(Boolean).join(" · ");
        let right = null;
        if (isDone) right = icon("check", 18, { stroke: 3, label: "Done" });
        else if (state.status === "running" && state.endsAt) right = h("span", { dataset: { end: state.endsAt } }, countdown((state.endsAt - now()) / 1000));
        else if (state.status === "running") right = "On";
        else if (isNow) right = "Now";
        return h("li", {},
          h("button", {
            type: "button", class: `srow${isDone ? " done" : ""}${isNow || expanded ? " cur" : ""}`,
            "aria-expanded": String(expanded),
            onclick: () => { open = expanded ? null : s.number; render(); },
          },
            h("span", { class: "t num" }, clock(s.start)),
            h("span", { class: "x" },
              h("span", { class: "ld" }, inline(s.lead)),
              h("span", { class: "md" }, meta),
              s.body ? h("span", { class: "bd" }, inline(s.body)) : null),
            h("span", { class: "r num" }, right)),
          expanded ? h("div", { style: { display: "flex", gap: "8px", padding: "0 10px 10px 86px", "flex-wrap": "wrap" } },
            state.status === "pending" ? h("button", { type: "button", class: "btn btn-gold btn-sm", onclick: () => { open = null; start(s); } }, "Start") : null,
            state.status === "running" ? h("button", { type: "button", class: "btn btn-gold btn-sm", onclick: () => { open = null; done(s); } }, "Done") : null,
            state.status !== "pending" ? h("button", { type: "button", class: "btn btn-sm", style: { background: "var(--night-4)", color: "var(--cream)" }, onclick: () => { open = null; undo(s); } }, "Undo") : null) : null);
      })),
      h("div", { class: "plate" }, h("span", { class: "t num" }, clock(plate)), "Plate"));
  }

  function stripEl() {
    const items = steps.filter((s) => s.end > s.start);
    if (!items.length) return null;
    const t0 = Math.min(...items.map((s) => s.start.getTime()));
    const t1 = plate.getTime();
    const span = Math.max(t1 - t0, MIN * 1000);
    const pct = (t) => `${Math.max(0, Math.min(100, ((t - t0) / span) * 100))}%`;
    const rows = packRows(items, (s) => [s.start.getTime() / 1000, s.end.getTime() / 1000]);
    const stepMin = [5, 10, 15, 30, 60, 120, 240].find((m) => span / (m * 60000) <= 8) || 480;
    const ticks = [];
    const first = Math.ceil(t0 / (stepMin * 60000)) * stepMin * 60000;
    for (let t = first; t <= t1; t += stepMin * 60000) ticks.push(t);
    return h("div", { class: "cook-strip", "aria-hidden": "true" },
      h("div", { class: "ticks num" }, ticks.map((t) => h("span", { style: { left: pct(t) } }, clock(new Date(t), { ampm: false })))),
      h("div", { class: "rows" },
        rows.map((row) => h("div", { class: "row" }, row.map((s) =>
          h("div", { class: `b ${s.mode === "active" ? "on" : "off"}${st(s).status === "done" ? " done" : ""}`, style: { left: pct(s.start.getTime()), width: `${((s.end - s.start) / span) * 100}%` } })))),
        h("div", { class: "nowline", dataset: { t0, span }, style: { left: pct(now()), display: now() < t0 || now() > t1 ? "none" : "block" } })));
  }

  // -- the clock -------------------------------------------------------------
  function tick(skipCheck = false) {
    const t = now();
    if (!skipCheck) {
      const v = view();
      if (sig(v) !== signature) { render(); return; }
    }
    for (const el of page.querySelectorAll("[data-end]")) {
      const left = (Number(el.dataset.end) - t) / 1000;
      el.textContent = el.classList.contains("big") ? `${countdown(left)} left` : countdown(left);
    }
    for (const el of page.querySelectorAll("[data-until]")) el.textContent = until(Math.max(0, (Number(el.dataset.until) - t) / 1000));
    for (const el of page.querySelectorAll("[data-from]")) {
      const from = Number(el.dataset.from), end = Number(el.dataset.to);
      el.style.width = `${Math.min(100, ((t - from) / (end - from)) * 100)}%`;
    }
    const c = page.querySelector("[data-clock]");
    if (c) c.textContent = clock(new Date(t));
    const line = page.querySelector(".nowline");
    if (line) {
      const t0 = Number(line.dataset.t0), span = Number(line.dataset.span);
      line.style.left = `${Math.max(0, Math.min(100, ((t - t0) / span) * 100))}%`;
      line.style.display = t < t0 || t > t0 + span ? "none" : "block";
    }
    const ringingNow = ringingSteps();
    if (ringingNow.length) ring(ringingNow.map((s) => s.lead).join(" · "));
  }

  // -- finishing ---------------------------------------------------------------
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
