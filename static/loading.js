const statusLines = [
  "Connecting to hospital real-time telemetry...",
  "Loading clinical logistic regression & ensemble models...",
  "Calibrating rule-based clinical safety layer...",
  "Synchronizing patient census & telemetry dashboard...",
];

const statusText = document.getElementById("status-text");
const progressFill = document.getElementById("progress-fill");
const progressText = document.getElementById("progress-text");
const shell = document.getElementById("loader-shell");
const skipBtn = document.getElementById("skip-btn");

const totalDurationMs = 1800; // Snappy 1.8-second load
const statusIntervalMs = 450;
const start = performance.now();
let finished = false;

let statusIndex = 0;
const statusTimer = setInterval(() => {
  if (finished) return;
  statusIndex = (statusIndex + 1) % statusLines.length;
  if (statusText) statusText.textContent = statusLines[statusIndex];
}, statusIntervalMs);

function navigateToDashboard() {
  if (finished) return;
  finished = true;
  clearInterval(statusTimer);
  shell?.classList.add("fade-out");
  window.setTimeout(() => {
    window.location.href = "/dashboard";
  }, 350);
}

skipBtn?.addEventListener("click", () => {
  navigateToDashboard();
});

const frame = () => {
  if (finished) return;
  const elapsed = performance.now() - start;
  const progress = Math.min(1, elapsed / totalDurationMs);
  const pct = Math.round(progress * 100);
  if (progressFill) progressFill.style.width = `${pct}%`;
  if (progressText) progressText.textContent = `${pct}%`;

  if (elapsed < totalDurationMs) {
    requestAnimationFrame(frame);
  } else {
    navigateToDashboard();
  }
};

requestAnimationFrame(frame);

function logEvent(tag, data = {}) {
  try {
    const body = JSON.stringify({ tag, data });
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon("/api/log-event", blob);
    }
  } catch {
    // ignore
  }
}

logEvent("loading_screen_enter", { page: "loading" });
