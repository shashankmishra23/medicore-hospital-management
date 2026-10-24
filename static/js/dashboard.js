// Dashboard: numbers, charts, today's lists, alerts bell
pages.dashboard = { title: "Dashboard", load: loadDashboard };

const charts = {};
let chartData = null;

function greeting() {
  const h = new Date().getHours();
  const part = h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
  return `${part}, ${state.user.name.split(" ")[0]} 👋`;
}

async function loadDashboard() {
  $("#greeting").textContent = greeting();
  try {
    // The server only sends the numbers this role may see
    const d = await api.get("/dashboard");
    const cards = [
      { key: "total_patients", icon: "👥", label: "Total Patients", color: "var(--accent)", page: "patients" },
      { key: "admitted", icon: "🛏", label: "Currently Admitted", color: "var(--accent2)", page: "admissions" },
      { key: "todays_appointments", icon: "📅", label: "Today's Appointments", color: "var(--accent3)", page: "appointments" },
      { key: "online_bookings", icon: "🌐", label: "Online Bookings (7 days)", color: "#a855f7", page: "appointments" },
      { key: "monthly_revenue", icon: "₹", label: "Revenue This Month", color: "var(--success)", page: "billing", money: true },
      { key: "outstanding", icon: "🧾", label: "Unpaid Bills", color: "var(--danger)", page: "billing", money: true },
      { key: "active_doctors", icon: "⚕", label: "Active Doctors", color: "#a855f7", page: "doctors" },
      { key: "free_beds", icon: "🛌", label: "Free Beds", color: "var(--accent)", page: "wards" },
      { key: "pending_prescriptions", icon: "℞", label: "Prescriptions Waiting", color: "var(--accent3)", page: "prescriptions" },
      { key: "low_stock_medicines", icon: "💊", label: "Low Stock Medicines", color: "var(--danger)", page: "pharmacy" },
    ].filter(c => d[c.key] !== undefined).map(c => ({ ...c, value: c.money ? fmt(d[c.key]) : d[c.key] }));
    const grid = $("#dashboard-stats");
    grid.innerHTML = html`${cards.map(c => html`
      <div class="stat-card clickable" style="--card-accent:${c.color}" onclick="showPage('${c.page}')">
        <div class="stat-icon">${c.icon}</div>
        <div class="stat-value">${c.value}</div>
        <div class="stat-label">${c.label}</div>
      </div>`)}`;
    grid.style.display = "grid";
    $("#dashboard-loading").style.display = "none";
    $("#dashboard-content").style.display = "block";
    loadCharts();
    const showAppts = can("view.appointments"), showStock = can("view.pharmacy");
    $("#today-appts").closest(".card").hidden = !showAppts;
    $("#low-stock-list").closest(".card").hidden = !showStock;
    $("#dashboard-lists").hidden = !showAppts && !showStock;
    $("#dashboard-lists").style.gridTemplateColumns = showAppts && showStock ? "" : "1fr";
    if (showAppts) loadTodayAppointments();
    if (showStock) loadLowStock();
  } catch (e) {
    $("#dashboard-loading").style.display = "none";
    $("#dashboard-stats").innerHTML = html`<div class="empty-state">Could not load dashboard: ${e.message}</div>`;
    $("#dashboard-stats").style.display = "block";
  }
}

async function loadTodayAppointments() {
  const el = $("#today-appts");
  try {
    const data = await api.get(`/appointments?date=${todayLocal()}&status=Scheduled`);
    if (!data.length) { el.innerHTML = html`<div class="empty-state">No appointments scheduled today</div>`; return; }
    el.innerHTML = html`${data.map(a => html`
      <div class="list-row">
        <div>
          <div style="font-weight:500;font-size:0.875rem">${a.patient_name}</div>
          <div class="cell-sub">${formatTime(a.appointment_time)} · Dr. ${a.doctor_name}</div>
        </div>
        <div class="text-mono text-accent" style="font-size:0.75rem;text-align:right">${a.reason || ""}</div>
      </div>`)}`;
  } catch (e) { el.innerHTML = html`<div class="empty-state">${e.message}</div>`; }
}

async function loadLowStock() {
  const el = $("#low-stock-list");
  try {
    const data = await api.get("/medicines?low_stock=true");
    if (!data.length) { el.innerHTML = html`<div class="empty-state" style="color:var(--success)">✓ All medicines sufficiently stocked</div>`; return; }
    el.innerHTML = html`${data.map(m => html`
      <div class="list-row">
        <div>
          <div style="font-weight:500;font-size:0.875rem">${m.name}</div>
          <div class="cell-sub">Reorder level: ${m.reorder_level}</div>
        </div>
        <div class="text-mono" style="font-size:0.85rem;color:var(--danger)">${m.stock_qty} left</div>
      </div>`)}`;
  } catch (e) { el.innerHTML = html`<div class="empty-state">${e.message}</div>`; }
}

// Charts (Chart.js)
async function loadCharts() {
  if (!window.Chart) {
    $$(".chart-box").forEach(b => { b.innerHTML = html`<div class="empty-state">Charts need an internet connection to load.</div>`; });
    return;
  }
  try {
    chartData = await api.get("/dashboard/charts");
    // Hide the chart cards this role gets no data for
    $("#chart-revenue").closest(".card").hidden = !chartData.revenue;
    $("#chart-appts").closest(".card").hidden = !chartData.appointments;
    $("#chart-beds").closest(".card").hidden = !chartData.beds;
    $(".chart-grid").hidden = !chartData.revenue && !chartData.appointments;
    $(".chart-grid").style.gridTemplateColumns = chartData.revenue && chartData.appointments ? "" : "1fr";
    drawCharts();
  } catch (e) { /* the numbers above still work without charts */ }
}

function drawCharts() {
  if (!chartData || !window.Chart) return;
  chartData = { revenue: [], appointments: [], beds: [], ...chartData };
  const text = cssVar("--muted"), grid = cssVar("--border");
  const accent = cssVar("--accent"), accent2 = cssVar("--accent2"), danger = cssVar("--danger");
  Chart.defaults.color = text;
  Chart.defaults.font.family = "'DM Sans', sans-serif";
  Object.values(charts).forEach(c => c.destroy());

  const monthName = m => new Date(m + "-01T00:00:00").toLocaleDateString("en-IN", { month: "short" });
  charts.revenue = new Chart($("#chart-revenue"), {
    type: "bar",
    data: {
      labels: chartData.revenue.map(r => monthName(r.month)),
      datasets: [{ label: "Revenue", data: chartData.revenue.map(r => r.total), backgroundColor: accent, borderRadius: 6, maxBarThickness: 46 }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => fmt(c.raw) } } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: grid }, ticks: { callback: v => "₹" + Number(v).toLocaleString("en-IN", { notation: "compact" }) } },
      },
    },
  });

  const statusColors = { Scheduled: accent2, Completed: accent, Cancelled: danger, "No-Show": cssVar("--accent3") };
  charts.appts = new Chart($("#chart-appts"), {
    type: "doughnut",
    data: {
      labels: chartData.appointments.map(a => a.status),
      datasets: [{ data: chartData.appointments.map(a => a.total), backgroundColor: chartData.appointments.map(a => statusColors[a.status]), borderWidth: 0 }],
    },
    options: { maintainAspectRatio: false, cutout: "65%", plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } } },
  });

  charts.beds = new Chart($("#chart-beds"), {
    type: "bar",
    data: {
      labels: chartData.beds.map(w => w.ward_name),
      datasets: [
        { label: "Occupied", data: chartData.beds.map(w => w.occupied), backgroundColor: danger, borderRadius: 4 },
        { label: "Free", data: chartData.beds.map(w => w.free), backgroundColor: accent, borderRadius: 4 },
      ],
    },
    options: {
      indexAxis: "y",
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
      scales: { x: { stacked: true, grid: { color: grid } }, y: { stacked: true, grid: { display: false } } },
    },
  });
}

// Redraw charts in the new colours when the theme changes
document.addEventListener("themechange", drawCharts);

// Alerts (bell)
let alertsCache = [];

async function loadAlerts() {
  try {
    alertsCache = await api.get("/alerts");
  } catch (e) {
    alertsCache = null;   // null = could not load
  }
  renderAlerts();
}

function renderAlerts() {
  const count = $("#notif-count");
  const list = $("#notif-list");
  const summary = $("#notif-summary");

  if (alertsCache === null) {
    count.style.display = "none";
    summary.textContent = "";
    list.innerHTML = html`<div class="empty-state">Could not load alerts</div>`;
    return;
  }
  const n = alertsCache.length;
  count.textContent = n > 9 ? "9+" : n;
  count.style.display = n ? "flex" : "none";     // hide the number when there is nothing
  summary.textContent = n ? `${n} need attention` : "";
  if (!n) {
    list.innerHTML = html`<div class="empty-state" style="color:var(--success)">✓ Nothing needs attention</div>`;
    return;
  }
  const icons = { danger: "🔴", warning: "🟠", info: "🔵" };
  list.innerHTML = html`${alertsCache.map((a, i) => html`
    <div class="notif-item" onclick="openAlert(${i})">
      <span>${icons[a.type] || "•"}</span>
      <div>
        <div class="notif-title">${a.title}</div>
        <div class="notif-detail">${a.detail}</div>
      </div>
    </div>`)}`;
}

function toggleAlerts(e) {
  e.stopPropagation();
  const panel = $("#notif-panel");
  const opening = !panel.classList.contains("open");
  panel.classList.toggle("open");
  if (opening) loadAlerts();   // fresh data every time it opens
}

function openAlert(i) {
  const a = alertsCache[i];
  if (!a) return;
  $("#notif-panel").classList.remove("open");
  showPage(a.page);
}
