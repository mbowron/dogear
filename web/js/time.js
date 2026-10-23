// Clock and duration formatting, shared by every view.

export const MIN = 60;
export const HOUR = 3600;

/** "6:30 PM" for a Date. */
export function clock(date, { ampm = true } = {}) {
  let h = date.getHours();
  const m = date.getMinutes();
  const suffix = h >= 12 ? "PM" : "AM";
  h = h % 12 || 12;
  const text = `${h}:${String(m).padStart(2, "0")}`;
  return ampm ? `${text} ${suffix}` : text;
}

/** "1 hr 5 min", "25 min", "45 sec". */
export function human(seconds) {
  seconds = Math.max(0, Math.round(seconds));
  if (seconds < MIN) return `${seconds} sec`;
  const totalMin = Math.round(seconds / MIN);
  const hrs = Math.floor(totalMin / 60);
  const mins = totalMin % 60;
  if (!hrs) return `${mins} min`;
  return mins ? `${hrs} hr ${mins} min` : `${hrs} hr`;
}

/** Countdown text: "4:05", "1:02:30". */
export function countdown(seconds) {
  const s = Math.max(0, Math.ceil(seconds));
  const hrs = Math.floor(s / HOUR);
  const mins = Math.floor((s % HOUR) / MIN);
  const secs = s % MIN;
  const ss = String(secs).padStart(2, "0");
  return hrs ? `${hrs}:${String(mins).padStart(2, "0")}:${ss}` : `${mins}:${ss}`;
}

/** "in 4 min", "in 0:40". */
export function until(seconds) {
  return seconds < MIN ? `in ${countdown(seconds)}` : `in ${human(seconds)}`;
}

/** "25 min" or "25–30 min" for a step's duration. */
export function durationLabel(step) {
  if (!step.durationS) return "";
  if (step.durationMinS && step.durationMinS !== step.durationS) {
    const lo = human(step.durationMinS);
    const hi = human(step.durationS);
    const [loN, loU] = splitUnit(lo);
    const [hiN, hiU] = splitUnit(hi);
    return loU && loU === hiU ? `${loN}–${hiN} ${hiU}` : `${lo}–${hi}`;
  }
  return human(step.durationS);
}

function splitUnit(text) {
  const m = text.match(/^(\d+) (min|hr|sec)$/);
  return m ? [m[1], m[2]] : [text, null];
}

/** "18:30" -> next Date at that time, today or tomorrow. */
export function nextAt(hhmm, from = new Date()) {
  const [h, m] = hhmm.split(":").map(Number);
  const d = new Date(from);
  d.setHours(h, m, 0, 0);
  if (d.getTime() < from.getTime() - 5 * MIN * 1000) d.setDate(d.getDate() + 1);
  return d;
}

export function hhmm(date) {
  return `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
}

/** Round a Date up to the next quarter hour. */
export function roundUp15(date) {
  const d = new Date(date);
  d.setSeconds(0, 0);
  const add = (15 - (d.getMinutes() % 15)) % 15;
  d.setMinutes(d.getMinutes() + add);
  return d;
}

export function isTomorrow(date, from = new Date()) {
  const a = new Date(from); a.setHours(0, 0, 0, 0);
  const b = new Date(date); b.setHours(0, 0, 0, 0);
  return b.getTime() - a.getTime() === 86400000;
}

/** "Oct 12" or "Oct 12, 2025" for an ISO date. */
export function shortDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  const date = new Date(y, m - 1, d);
  const sameYear = y === new Date().getFullYear();
  return date.toLocaleDateString(undefined, sameYear
    ? { month: "short", day: "numeric" }
    : { month: "short", day: "numeric", year: "numeric" });
}

export function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
