// Timer alarms (sound, vibration, notification) and keeping the screen awake.
// Browsers only allow sound after a tap, so call unlock() from a click handler.

let ctx = null;
let ringing = null;

export function unlock() {
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === "suspended") ctx.resume();
  } catch { /* no audio */ }
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission().catch(() => {});
  }
}

function chime() {
  if (!ctx) return;
  const t0 = ctx.currentTime;
  [0, 0.18, 0.36].forEach((offset, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = i === 2 ? 1046.5 : 880;
    gain.gain.setValueAtTime(0.0001, t0 + offset);
    gain.gain.exponentialRampToValueAtTime(0.35, t0 + offset + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + offset + 0.16);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t0 + offset);
    osc.stop(t0 + offset + 0.18);
  });
}

/** Start ringing (idempotent). `title` is used for the notification. */
export function ring(title) {
  if (ringing) return;
  chime();
  if (navigator.vibrate) navigator.vibrate([300, 150, 300]);
  ringing = setInterval(() => {
    chime();
    if (navigator.vibrate) navigator.vibrate(300);
  }, 2000);
  if (document.hidden && "Notification" in window && Notification.permission === "granted") {
    try { new Notification("Dogear", { body: title, tag: "dogear-timer", renotify: true }); } catch { /* iOS */ }
  }
}

export function silence() {
  if (ringing) clearInterval(ringing);
  ringing = null;
}

// ---------------------------------------------------------------------------

let lock = null;
let wanted = false;

async function request() {
  if (!wanted || !("wakeLock" in navigator) || document.hidden) return;
  try {
    lock = await navigator.wakeLock.request("screen");
    lock.addEventListener("release", () => { lock = null; });
  } catch { /* denied or not over HTTPS */ }
}

document.addEventListener("visibilitychange", () => {
  if (!document.hidden && wanted && !lock) request();
});

export function stayAwake(on) {
  wanted = on;
  if (on) request();
  else if (lock) { lock.release().catch(() => {}); lock = null; }
}
