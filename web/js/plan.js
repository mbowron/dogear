// Turning the server's relative timing (seconds before plate) into clock
// times, and the URL parameters that carry a plan between views.

import { MIN, nextAt, roundUp15, hhmm } from "./time.js";

/**
 * A plan is { servings, plate: Date }. URL form: ?servings=6&plate=18:30
 * or ?servings=6&start=now. Without either, plate defaults to the soonest
 * quarter hour the recipe can make.
 */
export function readPlan(recipe, params = new URLSearchParams(location.search)) {
  const total = recipe.timing.totalS;
  const servings = Number(params.get("servings")) || recipe.yield.count;
  let plate;
  if (params.get("start") === "now") plate = new Date(Date.now() + total * 1000);
  else if (/^\d{1,2}:\d{2}$/.test(params.get("plate") || "")) plate = nextAt(params.get("plate"));
  else plate = defaultPlate(total);
  return { servings, plate };
}

export function defaultPlate(totalS) {
  return roundUp15(new Date(Date.now() + totalS * 1000));
}

export function planQuery({ servings, plate, startNow = false }, recipe) {
  const q = new URLSearchParams();
  if (servings && servings !== recipe.yield.count) q.set("servings", String(servings));
  if (startNow) q.set("start", "now");
  else q.set("plate", hhmm(plate));
  return q.toString();
}

/** Each step with absolute start/end Dates for a plate time. */
export function timedSteps(recipe, plate) {
  const p = plate.getTime();
  return recipe.steps.map((step, i) => {
    const t = recipe.timing.steps[i];
    return { ...step, start: new Date(p + t.startS * 1000), end: new Date(p + t.endS * 1000) };
  });
}

export function startOf(recipe, plate) {
  return new Date(plate.getTime() - recipe.timing.totalS * 1000);
}

/** Pack bars into rows so overlapping steps sit on separate lines. */
export function packRows(items, key = (x) => [x.startS, x.endS]) {
  const rows = [];
  for (const item of items) {
    const [s, e] = key(item);
    let row = rows.find((r) => r.end <= s);
    if (!row) { row = { end: -Infinity, items: [] }; rows.push(row); }
    row.items.push(item);
    row.end = Math.max(e, s + MIN / 2);
  }
  return rows.map((r) => r.items);
}

export const HEAT = new Set(["oven", "toaster-oven", "air-fryer", "grill", "smoker"]);

export function applianceLabel(app) {
  if (!app) return "";
  const name = app.name.charAt(0).toUpperCase() + app.name.slice(1);
  const parts = [name];
  if (app.count > 1) parts.push(`×${app.count}`);
  if (app.broil) parts.push("broil");
  else if (app.temp) parts.push(`${app.temp}°${app.tempUnit || "F"}`);
  return parts.join(" ");
}
