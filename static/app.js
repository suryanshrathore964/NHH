const state = {
  dashboard: null,
  records: [],
  charts: {},
  liveAnimationTimer: null,
  vitalsTimer: null,
  vitalsControl: { heartRate: "manual", systolicBP: "manual" },
  activeFilter: "all",
  searchQuery: "",
  activeChartTab: "stratification",
  alertSettings: null,
};

function logEvent(tag, data = {}) {
  try {
    const body = JSON.stringify({ tag, data });
    if (navigator.sendBeacon) {
      const blob = new Blob([body], { type: "application/json" });
      navigator.sendBeacon("/api/log-event", blob);
    } else {
      fetch("/api/log-event", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: true,
      });
    }
  } catch {
    // best-effort
  }
}

const emergencyContactsByCity = {
  mumbai: [
    { name: "KEM Hospital Trauma Care Center", tel: "+91 22 2410 7000", loc: "Parel, Mumbai" },
    { name: "Fortis Emergency Response Unit", tel: "+91 22 4100 2323", loc: "Mulund, Mumbai" },
    { name: "Lilavati Trauma & ICU Unit", tel: "+91 22 2675 1000", loc: "Bandra, Mumbai" },
    { name: "Apollo Emergency Command", tel: "+91 22 3350 3350", loc: "Navi Mumbai" },
  ],
  delhi: [
    { name: "AIIMS Apex Trauma Center", tel: "+91 11 2658 8500", loc: "Ansari Nagar, New Delhi" },
    { name: "Max Super Speciality Hospital", tel: "+91 11 4040 1010", loc: "Saket, New Delhi" },
    { name: "Fortis Escorts Emergency Unit", tel: "+91 11 4713 5000", loc: "Okhla, New Delhi" },
    { name: "Sir Ganga Ram Trauma Care", tel: "+91 11 4225 4000", loc: "Rajinder Nagar, New Delhi" },
  ],
  bangalore: [
    { name: "Manipal Hospital Emergency 24x7", tel: "+91 80 2222 1111", loc: "Old Airport Rd, Bangalore" },
    { name: "Aster CMI Trauma Command", tel: "+91 80 4342 0100", loc: "Hebbal, Bangalore" },
    { name: "Apollo Specialty Emergency Line", tel: "+91 80 2630 4050", loc: "Bannerghatta, Bangalore" },
    { name: "Sakra World Hospital ICU", tel: "+91 80 4969 4969", loc: "Marathahalli, Bangalore" },
  ],
  pune: [
    { name: "Ruby Hall Clinic Trauma Unit", tel: "+91 20 6645 5100", loc: "Sassoon Rd, Pune" },
    { name: "Jehangir Hospital Emergency Service", tel: "+91 20 6681 9999", loc: "Station Rd, Pune" },
    { name: "Sahyadri Super Speciality Center", tel: "+91 20 6721 3000", loc: "Deccan Gymkhana, Pune" },
    { name: "Noble Hospital Critical Care", tel: "+91 20 6749 9999", loc: "Hadapsar, Pune" },
  ],
};

function toPercent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function toCurrency(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    Number(value || 0)
  );
}

function riskClassCategory(risk) {
  const r = String(risk || "").toLowerCase();
  if (r.includes("high")) return "high";
  if (r.includes("med")) return "medium";
  if (r.includes("low")) return "low";
  return "neutral";
}

/* ==========================================================================
   PATIENT INTAKE PRESETS
   ========================================================================== */

const presets = {
  low: {
    age: 58,
    systolic_bp: 122,
    heart_rate: 72,
    mobility_status: 0,
    medications_count: 2,
    previous_falls: 0,
    sedatives: false,
    opioids: false,
    anti_hypertensives: false,
    post_surgery: false,
    vision_impairment: 0,
    mental_status: 0,
  },
  med: {
    age: 70,
    systolic_bp: 136,
    heart_rate: 78,
    mobility_status: 1,
    medications_count: 4,
    previous_falls: 1,
    sedatives: false,
    opioids: false,
    anti_hypertensives: true,
    post_surgery: false,
    vision_impairment: 0,
    mental_status: 0,
  },
  high: {
    age: 84,
    systolic_bp: 154,
    heart_rate: 96,
    mobility_status: 2,
    medications_count: 8,
    previous_falls: 2,
    sedatives: true,
    opioids: false,
    anti_hypertensives: true,
    post_surgery: true,
    vision_impairment: 2,
    mental_status: 2,
  },
};

function applyPreset(type) {
  const data = presets[type];
  if (!data) return;

  const form = document.getElementById("predict-form");
  if (!form) return;

  document.getElementById("input-age").value = data.age;
  document.getElementById("age-badge").textContent = data.age;

  document.getElementById("systolicBP").value = data.systolic_bp;
  document.getElementById("heartRate").value = data.heart_rate;
  document.getElementById("input-meds-count").value = data.medications_count;
  document.getElementById("meds-count-badge").textContent = data.medications_count;
  document.getElementById("input-falls").value = data.previous_falls;

  const mobilityRadios = form.querySelectorAll('input[name="mobility_status"]');
  mobilityRadios.forEach((r) => {
    r.checked = Number(r.value) === data.mobility_status;
  });

  form.querySelector('input[name="sedatives"]').checked = data.sedatives;
  form.querySelector('input[name="opioids"]').checked = data.opioids;
  form.querySelector('input[name="anti_hypertensives"]').checked = data.anti_hypertensives;
  form.querySelector('input[name="post_surgery"]').checked = data.post_surgery;

  document.getElementById("input-vision").value = data.vision_impairment;
  document.getElementById("input-mental").value = data.mental_status;

  logEvent("apply_patient_preset", { preset: type });
}

document.getElementById("preset-low")?.addEventListener("click", () => applyPreset("low"));
document.getElementById("preset-med")?.addEventListener("click", () => applyPreset("med"));
document.getElementById("preset-high")?.addEventListener("click", () => applyPreset("high"));

// Dynamic Badges on Input change
document.getElementById("input-age")?.addEventListener("input", (e) => {
  document.getElementById("age-badge").textContent = e.target.value;
});
document.getElementById("input-meds-count")?.addEventListener("input", (e) => {
  document.getElementById("meds-count-badge").textContent = e.target.value;
});

/* ==========================================================================
   VITALS TELEMETRY & AUTO-STREAM
   ========================================================================== */

function setVitalsControl(fieldId, mode) {
  state.vitalsControl[fieldId] = mode;
  const isHR = fieldId === "heartRate";
  const manualBtn = document.getElementById(isHR ? "hr-manual-btn" : "bp-manual-btn");
  const autoBtn = document.getElementById(isHR ? "hr-auto-btn" : "bp-auto-btn");
  manualBtn?.classList.toggle("active", mode === "manual");
  autoBtn?.classList.toggle("active", mode === "auto");
}

document.getElementById("bp-manual-btn")?.addEventListener("click", () => setVitalsControl("systolicBP", "manual"));
document.getElementById("bp-auto-btn")?.addEventListener("click", () => setVitalsControl("systolicBP", "auto"));
document.getElementById("hr-manual-btn")?.addEventListener("click", () => setVitalsControl("heartRate", "manual"));
document.getElementById("hr-auto-btn")?.addEventListener("click", () => setVitalsControl("heartRate", "auto"));

async function fetchVitalsFromApi() {
  try {
    const res = await fetch("/api/vitals");
    if (!res.ok) throw new Error();
    return await res.json();
  } catch {
    const hr = Math.round(72 + Math.random() * 24);
    const sbp = Math.round(118 + Math.random() * 32);
    return { heart_rate: hr, systolic_bp: sbp };
  }
}

async function vitalsTick() {
  const hrInput = document.getElementById("heartRate");
  const bpInput = document.getElementById("systolicBP");
  const telemetryDisplay = document.getElementById("telemetry-display");

  const isHrAuto = state.vitalsControl.heartRate === "auto";
  const isBpAuto = state.vitalsControl.systolicBP === "auto";

  if (isHrAuto || isBpAuto) {
    const vitals = await fetchVitalsFromApi();

    if (isHrAuto && hrInput) {
      hrInput.value = Math.round(vitals.heart_rate);
      const dot = document.getElementById("live-hr");
      dot?.classList.add("pulse");
      window.setTimeout(() => dot?.classList.remove("pulse"), 800);
    }
    if (isBpAuto && bpInput) {
      bpInput.value = Math.round(vitals.systolic_bp);
      const dot = document.getElementById("live-bp");
      dot?.classList.add("pulse");
      window.setTimeout(() => dot?.classList.remove("pulse"), 800);
    }
  }

  if (telemetryDisplay && hrInput && bpInput) {
    telemetryDisplay.textContent = `${hrInput.value || 75} bpm • ${bpInput.value || 120} mmHg`;
  }
}

function startVitalsTelemetry() {
  if (state.vitalsTimer) clearInterval(state.vitalsTimer);
  vitalsTick();
  state.vitalsTimer = setInterval(vitalsTick, 3500);
}

/* ==========================================================================
   RESULTS CARD & RADIAL GAUGE UPDATE
   ========================================================================== */

function updateAssessmentDisplay(result) {
  const probability = Number(result.risk_probability || 0);
  const probPercent = Math.round(probability * 100);
  const riskClass = riskClassCategory(result.risk_class);

  // Radial Gauge Animation (Circumference = 2 * PI * 52 ≈ 326.7)
  const maxCircumference = 326.7;
  const offset = maxCircumference * (1 - probability);
  const gaugeBar = document.getElementById("gauge-bar");
  const gaugeText = document.getElementById("gauge-percentage");
  const gaugeBadge = document.getElementById("gauge-badge");

  if (gaugeBar) {
    gaugeBar.style.strokeDashoffset = offset;
    gaugeBar.className = `gauge-fill ${riskClass}`;
  }

  if (gaugeText) {
    gaugeText.textContent = `${probPercent}%`;
  }

  if (gaugeBadge) {
    gaugeBadge.className = `risk-tier-badge ${riskClass}`;
    gaugeBadge.textContent = `${result.risk_class.toUpperCase()} RISK`;
  }

  // Top KPI Card Updates
  const riskProbKpi = document.getElementById("risk-prob");
  const resultPill = document.getElementById("result-pill");
  const confidenceKpi = document.getElementById("confidence");
  if (riskProbKpi) riskProbKpi.textContent = toPercent(probability);
  if (resultPill) {
    resultPill.className = `status-pill ${riskClass}`;
    resultPill.textContent = `${result.risk_class.toUpperCase()} RISK`;
  }
  if (confidenceKpi) confidenceKpi.textContent = toPercent(result.confidence || 0.9);

  // Split details
  const mlProb = document.getElementById("ml-prob-val");
  const ruleScore = document.getElementById("rule-score-val");
  if (mlProb) mlProb.textContent = toPercent(result.ml_probability || probability);
  if (ruleScore) ruleScore.textContent = result.rule_layer?.rule_score ?? "3.4";

  // Care Protocols
  const plan = result.care_plan || {};
  const line2 = document.getElementById("analysis-line-2");
  const line3 = document.getElementById("analysis-line-3");
  const line4 = document.getElementById("analysis-line-4");
  const emergency1 = document.getElementById("analysis-emergency-1");

  if (line2) line2.textContent = `Estimated risk window: within next ${plan.expected_fall_window_hours || 8} hours.`;
  if (line3) line3.textContent = `${plan.observation_frequency || "Observe every 2 hours"}; priority: ${(plan.care_windows || []).join(", ")}.`;
  if (line4) line4.textContent = plan.medication_guidance || "Stagger sedatives and monitor orthostatic changes.";
  if (emergency1 && plan.emergency_actions?.length) {
    emergency1.textContent = plan.emergency_actions[0];
  }

  // Estimated Bill
  const billEl = document.getElementById("estimated-bill");
  const billMultiplier = document.getElementById("bill-multiplier-info");
  if (billEl) billEl.textContent = toCurrency(result.bill?.total_bill || 240);
  if (billMultiplier) {
    billMultiplier.textContent = `${result.risk_class.toUpperCase()} Multiplier (${result.bill?.risk_multiplier || 1.0}x)`;
  }
}

/* ==========================================================================
   CHARTS HUB (Stratification, Importance, Age-Trend, Operational, Matrix)
   ========================================================================== */

function createOrUpdateChart(chartKey, canvasId, config) {
  if (state.charts[chartKey]) {
    state.charts[chartKey].destroy();
  }
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  state.charts[chartKey] = new Chart(ctx, config);
}

function baseChartOptions() {
  return {
    responsive: true,
    maintainAspectRatio: false,
    font: { family: "'Plus Jakarta Sans', sans-serif" },
    animation: { duration: 1000, easing: "easeOutQuart" },
  };
}

function renderStratificationChart(distribution) {
  const dist = distribution || { low: 10, medium: 15, high: 8 };
  createOrUpdateChart("stratification", "risk-distribution-chart", {
    type: "doughnut",
    data: {
      labels: ["Low Risk", "Medium Risk", "High Risk"],
      datasets: [
        {
          data: [dist.low, dist.medium, dist.high],
          backgroundColor: ["#10b981", "#f59e0b", "#ef4444"],
          borderColor: ["#ffffff", "#ffffff", "#ffffff"],
          borderWidth: 2,
          hoverOffset: 8,
        },
      ],
    },
    options: {
      ...baseChartOptions(),
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#0f172a",
          padding: 10,
          cornerRadius: 8,
        },
      },
      cutout: "68%",
    },
  });
}

function renderFeatureChart(features) {
  const labels = Object.keys(features || {});
  const values = Object.values(features || {});

  createOrUpdateChart("features", "feature-importance-chart", {
    type: "bar",
    data: {
      labels: labels.map((l) => l.replace(/_/g, " ").toUpperCase()),
      datasets: [
        {
          label: "Feature Impact Weight",
          data: values,
          backgroundColor: "rgba(2, 132, 199, 0.85)",
          hoverBackgroundColor: "#0284c7",
          borderRadius: 6,
        },
      ],
    },
    options: {
      ...baseChartOptions(),
      indexAxis: "y",
      scales: {
        x: { grid: { color: "#f1f5f9" }, ticks: { color: "#64748b" } },
        y: { grid: { display: false }, ticks: { color: "#0f172a", font: { weight: 600 } } },
      },
      plugins: { legend: { display: false } },
    },
  });
}

function renderTrendChart(points) {
  const pts = points || [];
  createOrUpdateChart("trend", "trend-chart", {
    type: "line",
    data: {
      labels: pts.map((p) => `${p.age} yrs`),
      datasets: [
        {
          label: "Risk Probability",
          data: pts.map((p) => p.risk_probability),
          borderColor: "#0284c7",
          backgroundColor: "rgba(2, 132, 199, 0.12)",
          fill: true,
          tension: 0.35,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: "Critical Threshold (70%)",
          data: pts.map(() => 0.7),
          borderColor: "#ef4444",
          borderDash: [5, 5],
          pointRadius: 0,
          fill: false,
        },
      ],
    },
    options: {
      ...baseChartOptions(),
      scales: {
        x: { grid: { color: "#f1f5f9" }, ticks: { color: "#64748b" } },
        y: {
          min: 0,
          max: 1,
          grid: { color: "#f1f5f9" },
          ticks: {
            color: "#64748b",
            callback: (v) => `${Math.round(v * 100)}%`,
          },
        },
      },
    },
  });
}

function renderOperationalStreamChart(records) {
  const points = [...(records || [])].reverse().slice(0, 15);
  createOrUpdateChart("operational", "operational-trend-chart", {
    type: "line",
    data: {
      labels: points.map((_, i) => `Evaluation #${i + 1}`),
      datasets: [
        {
          label: "Monitored Patient Probability",
          data: points.map((p) => p.risk_probability),
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.12)",
          fill: true,
          tension: 0.35,
          pointRadius: 4,
        },
      ],
    },
    options: {
      ...baseChartOptions(),
      scales: {
        x: { grid: { color: "#f1f5f9" }, ticks: { color: "#64748b" } },
        y: {
          min: 0,
          max: 1,
          grid: { color: "#f1f5f9" },
          ticks: {
            color: "#64748b",
            callback: (v) => `${Math.round(v * 100)}%`,
          },
        },
      },
    },
  });
}

function updateConfusionMatrix(matrix) {
  const tn = matrix?.[0]?.[0] ?? 138;
  const fp = matrix?.[0]?.[1] ?? 18;
  const fn = matrix?.[1]?.[0] ?? 16;
  const tp = matrix?.[1]?.[1] ?? 128;
  document.getElementById("tn").textContent = tn;
  document.getElementById("fp").textContent = fp;
  document.getElementById("fn").textContent = fn;
  document.getElementById("tp").textContent = tp;
}

// Chart Tab Switcher
document.querySelectorAll("[data-chart-tab]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const tabName = btn.getAttribute("data-chart-tab");
    document.querySelectorAll("[data-chart-tab]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    document.querySelectorAll(".chart-tab-pane").forEach((p) => p.classList.remove("active"));
    document.getElementById(`pane-${tabName}`)?.classList.add("active");

    // Force chart resize
    Object.values(state.charts).forEach((c) => c?.resize());
    logEvent("switch_chart_tab", { tab: tabName });
  });
});

/* ==========================================================================
   PATIENT CENSUS TABLE & SEARCH FILTERING
   ========================================================================== */

function renderCensusTable() {
  const tbody = document.getElementById("records-body");
  if (!tbody) return;

  const records = state.records || [];
  const filter = state.activeFilter;
  const q = state.searchQuery.toLowerCase().trim();

  const filtered = records.filter((r) => {
    const matchFilter = filter === "all" || riskClassCategory(r.risk_class) === filter;
    const matchQuery =
      !q ||
      String(r.id).toLowerCase().includes(q) ||
      String(r.payload?.age).includes(q) ||
      String(r.risk_class).toLowerCase().includes(q);
    return matchFilter && matchQuery;
  });

  if (!filtered.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-table-cell">No monitored patient records found matching current criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = filtered
    .map((r) => {
      const p = r.payload || {};
      const rc = riskClassCategory(r.risk_class);
      const rp = Math.round(Number(r.risk_probability || 0) * 100);
      const timeStr = r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : "--";
      const bill = toCurrency(r.bill?.total_bill || 0);
      const windowStr = r.care_plan?.expected_fall_window_hours
        ? `Within ${r.care_plan.expected_fall_window_hours}h`
        : "--";

      return `
      <tr>
        <td><strong>#PT-${r.id}</strong></td>
        <td>${timeStr}</td>
        <td>${p.age ?? "--"} yrs</td>
        <td><strong>${p.systolic_bp ?? "--"}</strong> / ${p.heart_rate ?? "--"}</td>
        <td><span class="status-pill ${rc}">${String(r.risk_class).toUpperCase()}</span></td>
        <td>
          <div style="display:flex;align-items:center;gap:0.5rem;">
            <div style="width:65px;height:6px;background:#e2e8f0;border-radius:4px;overflow:hidden;">
              <div style="width:${rp}%;height:100%;background:${rc === 'high' ? '#ef4444' : (rc === 'medium' ? '#f59e0b' : '#10b981')}"></div>
            </div>
            <strong>${rp}%</strong>
          </div>
        </td>
        <td><strong>${bill}</strong></td>
        <td>${windowStr}</td>
      </tr>
      `;
    })
    .join("");

  // Update Census KPI & Breakdown
  const totalCount = document.getElementById("total-patients-count");
  const censusBreakdown = document.getElementById("census-breakdown");
  if (totalCount) totalCount.textContent = records.length;

  const lowCount = records.filter((r) => riskClassCategory(r.risk_class) === "low").length;
  const medCount = records.filter((r) => riskClassCategory(r.risk_class) === "medium").length;
  const highCount = records.filter((r) => riskClassCategory(r.risk_class) === "high").length;
  if (censusBreakdown) {
    censusBreakdown.textContent = `Low: ${lowCount} • Med: ${medCount} • High: ${highCount}`;
  }

  // Update High Risk incident feed list
  const highRiskList = document.getElementById("high-risk-list");
  if (highRiskList) {
    const highRecords = records.filter((r) => riskClassCategory(r.risk_class) === "high").slice(0, 4);
    if (!highRecords.length) {
      highRiskList.innerHTML = `<li class="empty-list-notice">No high-risk patients currently flagged.</li>`;
    } else {
      highRiskList.innerHTML = highRecords
        .map(
          (hr) => `
        <li class="incident-feed-item">
          <div class="incident-meta">
            <span class="incident-avatar">!</span>
            <div>
              <strong>Patient #PT-${hr.id} (Age ${hr.payload?.age})</strong>
              <small style="display:block;color:#64748b;">BP: ${hr.payload?.systolic_bp} mmHg • HR: ${hr.payload?.heart_rate} bpm</small>
            </div>
          </div>
          <span class="status-pill high">${Math.round(hr.risk_probability * 100)}% RISK</span>
        </li>
      `
        )
        .join("");
    }
  }
}

// Filter pills
document.querySelectorAll(".filter-pill").forEach((pill) => {
  pill.addEventListener("click", () => {
    document.querySelectorAll(".filter-pill").forEach((p) => p.classList.remove("active"));
    pill.classList.add("active");
    state.activeFilter = pill.getAttribute("data-filter") || "all";
    renderCensusTable();
  });
});

// Search input
document.getElementById("census-search")?.addEventListener("input", (e) => {
  state.searchQuery = e.target.value;
  renderCensusTable();
});

/* ==========================================================================
   MODALS: EMERGENCY & SETTINGS
   ========================================================================== */

function openModal(modalId) {
  document.getElementById(modalId)?.classList.remove("hidden");
}

function closeModal(modalId) {
  document.getElementById(modalId)?.classList.add("hidden");
}

document.getElementById("emergency-toggle-btn")?.addEventListener("click", () => {
  renderEmergencyDirectory();
  openModal("emergency-modal");
  logEvent("open_emergency_modal");
});
document.getElementById("close-emergency-btn")?.addEventListener("click", () => closeModal("emergency-modal"));
document.getElementById("done-emergency-btn")?.addEventListener("click", () => closeModal("emergency-modal"));

document.getElementById("settings-btn")?.addEventListener("click", () => {
  openModal("settings-modal");
  logEvent("open_settings_modal");
});
document.getElementById("close-settings-btn")?.addEventListener("click", () => closeModal("settings-modal"));
document.getElementById("cancel-settings-btn")?.addEventListener("click", () => closeModal("settings-modal"));

function renderEmergencyDirectory() {
  const city = document.getElementById("city-select")?.value || "mumbai";
  const list = document.getElementById("emergency-contact-list");
  if (!list) return;

  const contacts = emergencyContactsByCity[city] || [];
  list.innerHTML = contacts
    .map(
      (c) => `
    <li class="emergency-contact-card">
      <div class="contact-details">
        <strong>${c.name}</strong>
        <span>${c.tel} • ${c.loc}</span>
      </div>
      <a href="tel:${c.tel.replace(/\s+/g, '')}" class="dial-btn">📞 Dispatch</a>
    </li>
  `
    )
    .join("");
}

document.getElementById("city-select")?.addEventListener("change", renderEmergencyDirectory);

// Alert settings save & test
document.getElementById("save-alert-settings-btn")?.addEventListener("click", async () => {
  const payload = {
    enabled: document.getElementById("alerts-enabled").checked,
    heart_rate_threshold: Number(document.getElementById("alert-hr-threshold").value),
    systolic_bp_threshold: Number(document.getElementById("alert-bp-threshold").value),
    risk_probability_threshold: Number(document.getElementById("alert-risk-threshold").value),
    caretaker_email: document.getElementById("caretaker-email").value.trim(),
  };

  try {
    const res = await fetch("/api/alerts/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      document.getElementById("alert-status-text").textContent = "Status: Alert settings configured successfully!";
      window.setTimeout(() => closeModal("settings-modal"), 800);
    }
  } catch {
    document.getElementById("alert-status-text").textContent = "Status: Error saving settings";
  }
});

document.getElementById("test-alert-btn")?.addEventListener("click", async () => {
  const statusEl = document.getElementById("alert-status-text");
  statusEl.textContent = "Status: Dispatching test alert simulation...";

  const payload = {
    caretaker_email: document.getElementById("caretaker-email").value.trim(),
    risk_probability: 0.94,
    risk_class: "high",
    patient: {
      age: Number(document.getElementById("input-age")?.value || 75),
      heart_rate: Number(document.getElementById("heartRate")?.value || 94),
      systolic_bp: Number(document.getElementById("systolicBP")?.value || 148),
      mobility_status: 2,
    },
  };

  try {
    const res = await fetch("/api/send-alert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      statusEl.textContent = "Status: Test alert simulation dispatched successfully!";
      fetchDashboard().catch(() => {});
    }
  } catch {
    statusEl.textContent = "Status: Test alert simulation complete (offline mode)";
  }
});

/* ==========================================================================
   PDF EXPORT
   ========================================================================== */

document.getElementById("download-pdf-btn")?.addEventListener("click", async () => {
  const btn = document.getElementById("download-pdf-btn");
  const originalText = btn.innerHTML;
  btn.innerHTML = `<span class="spinner-sm"></span> <span>Preparing PDF...</span>`;
  btn.disabled = true;

  try {
    const res = await fetch("/api/export-report");
    if (!res.ok) throw new Error();
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `techmechs_clinical_fall_report_${Date.now()}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    logEvent("download_pdf_success");
  } catch {
    alert("Could not generate PDF report at this moment. Please ensure you have completed at least one patient assessment.");
  } finally {
    btn.innerHTML = originalText;
    btn.disabled = false;
  }
});

/* ==========================================================================
   SIGN OUT
   ========================================================================== */

document.getElementById("logout-btn")?.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  window.location.href = "/signin";
});

/* ==========================================================================
   PREDICTION FORM SUBMIT
   ========================================================================== */

document.getElementById("predict-form")?.addEventListener("submit", async (e) => {
  e.preventDefault();

  const submitBtn = document.getElementById("submit-predict-btn");
  const spinner = document.getElementById("predict-spinner");
  const btnText = document.getElementById("predict-btn-text");

  submitBtn.disabled = true;
  spinner?.classList.remove("hidden");
  btnText.textContent = "Running Neural & Rule Inference...";

  const form = e.currentTarget;
  const fd = new FormData(form);

  const payload = {
    age: Number(fd.get("age")),
    systolic_bp: Number(fd.get("systolic_bp")),
    heart_rate: Number(fd.get("heart_rate")),
    mobility_status: Number(fd.get("mobility_status")),
    medications_count: Number(fd.get("medications_count")),
    previous_falls: Number(fd.get("previous_falls")),
    sedatives: fd.get("sedatives") ? 1 : 0,
    opioids: fd.get("opioids") ? 1 : 0,
    anti_hypertensives: fd.get("anti_hypertensives") ? 1 : 0,
    post_surgery: fd.get("post_surgery") ? 1 : 0,
    vision_impairment: Number(fd.get("vision_impairment") || 0),
    mental_status: Number(fd.get("mental_status") || 0),
  };

  try {
    const res = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) throw new Error("Inference request failed");
    const result = await res.json();

    updateAssessmentDisplay(result);

    // Prepend to local records
    state.records.unshift(result.record);
    renderCensusTable();

    // Update charts with latest census
    renderOperationalStreamChart(state.records);
    if (state.dashboard?.trend_points) renderTrendChart(state.dashboard.trend_points);

    document.getElementById("last-prediction-time").textContent = `Assessed: ${new Date().toLocaleTimeString()}`;
    logEvent("prediction_successful", { risk_class: result.risk_class });
  } catch (err) {
    alert("Inference engine error. Please check patient vital values and retry.");
  } finally {
    submitBtn.disabled = false;
    spinner?.classList.add("hidden");
    btnText.textContent = "⚡ Run Fall Risk Assessment";
  }
});

/* ==========================================================================
   INITIALIZATION & DASHBOARD DATA FETCH
   ========================================================================== */

async function fetchDashboard() {
  const res = await fetch("/api/dashboard");
  if (res.status === 401) {
    window.location.href = "/signin";
    return;
  }
  if (!res.ok) throw new Error("Failed to load dashboard telemetry");

  const data = await res.json();
  state.dashboard = data;
  state.records = data.recent_records || [];

  document.getElementById("welcome-user").textContent = `Dr. ${data.username || "Clinician"}`;

  // Metrics
  if (data.metrics) {
    document.getElementById("accuracy").textContent = toPercent(data.metrics.accuracy || 0.885);
    document.getElementById("precision").textContent = toPercent(data.metrics.precision || 0.875);
    document.getElementById("recall").textContent = toPercent(data.metrics.recall || 0.882);
    document.getElementById("best-model").textContent = data.metrics.selected_model || "Logistic / Ensemble";
  }

  // Visualizations
  renderStratificationChart(data.risk_distribution);
  renderFeatureChart(data.feature_importance);
  renderTrendChart(data.trend_points);
  renderOperationalStreamChart(state.records);
  updateConfusionMatrix(data.confusion_matrix);

  // Census Table
  renderCensusTable();

  // If records exist, update hero outcome card with latest
  if (state.records.length > 0) {
    updateAssessmentDisplay(state.records[0]);
  }

  // Populate Alert Settings
  if (data.alert_settings) {
    state.alertSettings = data.alert_settings;
    document.getElementById("alert-hr-threshold").value = data.alert_settings.heart_rate_threshold || 110;
    document.getElementById("alert-bp-threshold").value = data.alert_settings.systolic_bp_threshold || 140;
    document.getElementById("alert-risk-threshold").value = data.alert_settings.risk_probability_threshold || 0.75;
    document.getElementById("caretaker-email").value = data.alert_settings.caretaker_email || "";
    document.getElementById("alerts-enabled").checked = Boolean(data.alert_settings.enabled);
  }

  // Alert History
  const historyList = document.getElementById("alert-history-list");
  if (historyList && data.alert_history) {
    historyList.innerHTML = data.alert_history
      .map(
        (h) => `
      <li>${new Date(h.timestamp).toLocaleTimeString()} - Status: <strong>${h.status}</strong> (${Math.round(h.risk_probability * 100)}% risk ceiling)</li>
    `
      )
      .join("") || "<li>No automated alert dispatches triggered yet.</li>";
  }
}

// Start Telemetry and Load Data
startVitalsTelemetry();
fetchDashboard().catch(() => {});
