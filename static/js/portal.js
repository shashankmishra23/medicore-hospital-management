// Patient portal: home, online booking, appointments, prescriptions, bills, profile.
// Uses the shared helpers in core.js (api, html, modals, forms, formatting).

const portal = { me: null, doctors: [], spec: "", booking: {}, apptView: "upcoming" };
const WEEKDAY = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const BOOK_DAYS_AHEAD = 30;

pages.home = { title: "Home", load: loadHome };
pages.book = { title: "Book Appointment", load: loadBooking };
pages.appointments = { title: "My Appointments", load: loadMyAppointments };
pages.prescriptions = { title: "My Prescriptions", load: loadMyPrescriptions };
pages.bills = { title: "My Bills", load: loadMyBills };
pages.profile = { title: "My Profile", load: loadProfile };

async function loadMe() {
  portal.me = await api.get("/portal/me");
  const name = `${portal.me.first_name} ${portal.me.last_name}`;
  $("#user-avatar").textContent = initials(name);
  $("#user-name").textContent = name;
  return portal.me;
}

function dateKey(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function niceDate(d) {
  return parseDate(d).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
}

// Home
async function loadHome() {
  const h = new Date().getHours();
  const box = $("#home-content");
  try {
    const me = await loadMe();
    $("#greeting").textContent = `${h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"}, ${me.first_name} 👋`;
    const next = me.upcoming[0];
    box.innerHTML = html`
      ${me.admitted ? html`<div class="note-box">🛏 You are admitted in ${me.admitted.ward_name || "the hospital"}
        ${me.admitted.room_number ? `(room ${me.admitted.room_number})` : ""} since ${formatDate(me.admitted.admission_date)}. Get well soon!</div>` : ""}

      <div class="hero-card">
        ${next ? html`
          <div>
            <div class="label">Your next appointment</div>
            <div class="big">${niceDate(next.appointment_date)} · ${formatTime(next.appointment_time)}</div>
            <div>${next.doctor_name} — ${next.specialization}</div>
          </div>
          <button class="btn" onclick="showPage('appointments')">View all (${me.upcoming.length})</button>`
        : html`
          <div>
            <div class="label">No upcoming appointments</div>
            <div class="big">Need to see a doctor?</div>
            <div>Book online in under a minute.</div>
          </div>
          <button class="btn" onclick="showPage('book')">Book now →</button>`}
      </div>

      <div class="quick-grid">
        <div class="quick-tile" onclick="showPage('book')"><div class="q-icon">📅</div><b>Book appointment</b><small>Choose doctor & time</small></div>
        <div class="quick-tile" onclick="showPage('prescriptions')"><div class="q-icon">℞</div><b>Prescriptions</b><small>${me.prescription_count} on file</small></div>
        <div class="quick-tile" onclick="showPage('bills')"><div class="q-icon">🧾</div><b>Bills</b><small>${Number(me.unpaid_total) ? `${fmt(me.unpaid_total)} due` : "Nothing due"}</small></div>
        <div class="quick-tile" onclick="showPage('profile')"><div class="q-icon">👤</div><b>My profile</b><small>Contact & allergies</small></div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title">Health card</div>
          <button class="btn btn-ghost btn-sm" onclick="showPage('profile')">Edit</button>
        </div>
        <div class="card-body">
          <div class="info-grid">
            ${info("Patient ID", code("P", me.patient_id))}
            ${info("Age", `${calcAge(me.dob)} years`)}
            ${info("Blood group", me.blood_group)}
            ${info("Allergies", me.allergies || "None recorded")}
            ${info("Emergency contact", me.emergency_contact_name && `${me.emergency_contact_name} (${me.emergency_contact_phone || "no phone"})`)}
          </div>
        </div>
      </div>`;
  } catch (e) { box.innerHTML = html`<div class="empty-state">${e.message}</div>`; }
}

function info(label, value) {
  return html`<div><div class="info-label">${label}</div><div class="info-value">${value || "—"}</div></div>`;
}

// Booking
async function loadBooking() {
  hideError("book-error");
  try {
    portal.doctors = await api.get("/portal/doctors");
  } catch (e) { showError("book-error", e.message); return; }
  const specs = [...new Set(portal.doctors.map(d => d.specialization))].sort();
  $("#spec-chips").innerHTML = html`
    <div class="chip" data-value="" onclick="filterSpec('')">All doctors</div>
    ${specs.map(s => html`<div class="chip" data-value="${s}" onclick="filterSpec(this.dataset.value)">${s}</div>`)}`;
  renderDoctors();
  renderBookingSteps();
}

function filterSpec(spec) {
  portal.spec = spec;
  renderDoctors();
}

function renderDoctors() {
  setChip("spec-chips", portal.spec);
  const list = portal.doctors.filter(d => !portal.spec || d.specialization === portal.spec);
  $("#doctor-grid").innerHTML = list.length ? html`${list.map(d => html`
    <button type="button" class="doctor-card ${portal.booking.doctor?.doctor_id === d.doctor_id ? "selected" : ""}" onclick="pickDoctor(${d.doctor_id})">
      <div class="doc-top">
        <div class="avatar">${initials(d.name.replace("Dr. ", ""))}</div>
        <div><b>${d.name}</b><div class="meta">${d.specialization}</div></div>
      </div>
      <div class="meta">
        ${d.qualification ? html`🎓 ${d.qualification}<br>` : ""}
        🗓 ${(d.available_days || "Every day").replaceAll(",", ", ")}<br>
        💳 Consultation ${fmt(d.consultation_fee)}
      </div>
    </button>`)}` : html`<div class="empty-state">No doctors available right now.</div>`;
}

function pickDoctor(id) {
  portal.booking = { doctor: portal.doctors.find(d => d.doctor_id === id) };
  renderDoctors();
  renderBookingSteps();
  $("#step-date").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderBookingSteps() {
  const b = portal.booking;
  $("#step-date").hidden = !b.doctor;
  $("#step-time").hidden = !b.date;
  $("#step-reason").hidden = !b.time;
  $("#booking-bar").hidden = !b.doctor;
  if (b.doctor) {
    const works = (b.doctor.available_days || "").split(",").filter(Boolean);
    const days = [];
    for (let i = 0; i <= BOOK_DAYS_AHEAD; i++) {
      const d = new Date();
      d.setDate(d.getDate() + i);
      days.push(d);
    }
    $("#date-strip").innerHTML = html`${days.map(d => {
      const key = dateKey(d);
      const off = works.length && !works.includes(WEEKDAY[d.getDay()]);
      return html`<button type="button" class="date-chip ${b.date === key ? "selected" : ""}" ${off ? raw("disabled title=\"Doctor not available\"") : ""} onclick="pickDate('${key}')">
        <small>${WEEKDAY[d.getDay()]}</small><b>${d.getDate()}</b><small>${d.toLocaleDateString("en-IN", { month: "short" })}</small>
      </button>`;
    })}`;
  }
  $("#booking-summary").textContent = b.doctor
    ? [b.doctor.name, b.date ? niceDate(b.date) : "pick a day", b.time ? formatTime(b.time) : b.date ? "pick a time" : null,
       `Fee ${fmt(b.doctor.consultation_fee)}`].filter(Boolean).join(" · ")
    : "";
  $("#book-btn").disabled = !(b.doctor && b.date && b.time);
}

async function pickDate(key) {
  portal.booking.date = key;
  portal.booking.time = null;
  renderBookingSteps();
  const grid = $("#slot-grid");
  grid.innerHTML = html`<div class="loading"><div class="spinner"></div></div>`;
  hideError("book-error");
  try {
    const slots = await api.get(`/portal/slots?doctor_id=${portal.booking.doctor.doctor_id}&date=${key}`);
    renderSlots(slots);
  } catch (e) { grid.innerHTML = ""; showError("book-error", e.message); }
}

function renderSlots(slots) {
  const free = slots.filter(s => s.available).length;
  $("#slot-grid").innerHTML = free ? html`${slots.map(s => html`
    <button type="button" class="slot ${portal.booking.time === s.time ? "selected" : ""}" data-time="${s.time}"
      ${s.available ? "" : raw("disabled")} onclick="pickTime('${s.time}')">${formatTime(s.time)}</button>`)}`
    : html`<div class="text-muted text-sm">No free times left on this day. Please pick another day.</div>`;
}

function pickTime(time) {
  portal.booking.time = time;
  $$("#slot-grid .slot").forEach(s => s.classList.toggle("selected", s.dataset.time === time));
  renderBookingSteps();
}

async function confirmBooking() {
  const b = portal.booking;
  const btn = $("#book-btn");
  btn.disabled = true;
  btn.textContent = "Booking…";
  hideError("book-error");
  try {
    const r = await api.post("/portal/appointments", {
      doctor_id: b.doctor.doctor_id, appointment_date: b.date, appointment_time: b.time, reason: $("#book-reason").value,
    });
    openModal({
      title: "Appointment Booked ✓",
      body: html`
        <div class="hero-card" style="margin-bottom:16px">
          <div>
            <div class="label">Booking ${code("A", r.appointment_id)}</div>
            <div class="big">${niceDate(b.date)} · ${formatTime(b.time)}</div>
            <div>${b.doctor.name} — ${b.doctor.specialization}</div>
          </div>
        </div>
        <div class="text-sm" style="line-height:1.7">
          • Please arrive 15 minutes early and bring any old reports.<br>
          • Consultation fee ${fmt(b.doctor.consultation_fee)} is paid at the counter.<br>
          • Can't make it? Cancel from <b>My Appointments</b> so someone else can have the slot.
        </div>`,
      footer: html`<button type="button" class="btn btn-ghost" onclick="closeModal(); showPage('appointments')">My appointments</button>
        <button type="button" class="btn btn-primary" onclick="closeModal(); showPage('home')">Done</button>`,
    });
    portal.booking = {};
    $("#book-reason").value = "";
    renderDoctors();
    renderBookingSteps();
  } catch (e) {
    showError("book-error", e.message);
    if (b.date) pickDate(b.date);  // the slot may have just been taken: show fresh times
  } finally {
    btn.textContent = "Confirm Booking";
    btn.disabled = !(portal.booking.doctor && portal.booking.date && portal.booking.time);
  }
}

// My appointments
function filterMyAppts(view) {
  portal.apptView = view;
  loadMyAppointments();
}

async function loadMyAppointments() {
  setChip("pa-chips", portal.apptView);
  const box = $("#my-appts");
  box.innerHTML = html`<div class="loading"><div class="spinner"></div></div>`;
  try {
    const today = todayLocal();
    const all = await api.get("/portal/appointments");
    const upcoming = a => a.status === "Scheduled" && a.appointment_date >= today;
    const list = all.filter(a => (portal.apptView === "upcoming") === upcoming(a));
    if (portal.apptView === "upcoming") list.reverse();  // soonest first
    if (!list.length) {
      box.innerHTML = portal.apptView === "upcoming"
        ? html`<div class="empty-state">No upcoming appointments.<br><br><button class="btn btn-primary" onclick="showPage('book')">Book one now</button></div>`
        : html`<div class="empty-state">No past appointments yet.</div>`;
      return;
    }
    box.innerHTML = html`${list.map(a => {
      const d = parseDate(a.appointment_date);
      return html`<div class="appt-card">
        <div class="flex items-center" style="gap:14px">
          <div class="appt-date"><small>${WEEKDAY[d.getDay()]}</small><b>${d.getDate()}</b><small>${d.toLocaleDateString("en-IN", { month: "short" })}</small></div>
          <div>
            <div style="font-weight:600">${a.doctor_name} <span class="cell-sub">· ${a.specialization}</span></div>
            <div class="cell-sub">${formatTime(a.appointment_time)} · ${a.reason || "General consultation"}</div>
            ${a.notes && a.status === "Completed" ? html`<div class="text-sm" style="margin-top:4px">📝 ${a.notes}</div>` : ""}
          </div>
        </div>
        <div class="btn-row items-center">
          ${statusBadge(a.status)}
          ${upcoming(a) ? html`<button class="btn btn-danger btn-sm" onclick="cancelAppointment(${a.appointment_id})">Cancel</button>` : ""}
        </div>
      </div>`;
    })}`;
  } catch (e) { box.innerHTML = html`<div class="empty-state">${e.message}</div>`; }
}

function cancelAppointment(id) {
  openModal({
    title: "Cancel Appointment?",
    intro: "The time slot will be given to another patient. You can book again any time.",
    submitLabel: "Yes, cancel it",
    body: "",
    onSubmit: async () => {
      await api.post(`/portal/appointments/${id}/cancel`);
      saved("Appointment cancelled.");
    },
  });
}

// Prescriptions
let myPrescriptions = [];

async function loadMyPrescriptions() {
  const box = $("#my-rx");
  box.innerHTML = html`<div class="loading"><div class="spinner"></div></div>`;
  try {
    myPrescriptions = await api.get("/portal/prescriptions");
    if (!myPrescriptions.length) { box.innerHTML = html`<div class="empty-state">No prescriptions yet.</div>`; return; }
    box.innerHTML = html`${myPrescriptions.map(r => html`
      <div class="card">
        <div class="card-header">
          <div>
            <div class="card-title">${code("RX", r.prescription_id)} · ${r.doctor_name}</div>
            <div class="cell-sub">${r.specialization} · ${formatDate(r.issued_date)}</div>
          </div>
          <button class="btn btn-ghost btn-sm" onclick="printMyPrescription(${r.prescription_id})">🖨 Print</button>
        </div>
        <div class="table-wrap"><table>
          <thead><tr><th>Medicine</th><th>Dosage</th><th>How often</th><th>Days</th><th>Qty</th></tr></thead>
          <tbody>${r.items.map(i => html`<tr><td><b style="font-weight:600">${i.name}</b></td><td>${i.dosage || "—"}</td>
            <td>${i.frequency || "—"}</td><td>${i.duration_days || "—"}</td><td class="td-mono">${i.qty_prescribed}</td></tr>`)}</tbody>
        </table></div>
        ${r.notes ? html`<div class="card-body text-sm">📝 ${r.notes}</div>` : ""}
      </div>`)}`;
  } catch (e) { box.innerHTML = html`<div class="empty-state">${e.message}</div>`; }
}

function printMyPrescription(id) {
  const r = myPrescriptions.find(x => x.prescription_id === id);
  printWindow(`Prescription ${code("RX", id)}`, async () => html`
    ${printHeader("Prescription", code("RX", id), formatDateTime(r.issued_date))}
    <p><b>Patient:</b> ${portal.me.first_name} ${portal.me.last_name} (${code("P", portal.me.patient_id)})<br><b>Doctor:</b> ${r.doctor_name}, ${r.specialization}</p>
    <table><tr><th>Medicine</th><th>Dosage</th><th>How often</th><th>Days</th><th class="r">Qty</th></tr>
      ${r.items.map(i => html`<tr><td>${i.name}</td><td>${i.dosage || ""}</td><td>${i.frequency || ""}</td><td>${i.duration_days || ""}</td><td class="r">${i.qty_prescribed}</td></tr>`)}
    </table>
    ${r.notes ? html`<p><b>Notes:</b> ${r.notes}</p>` : ""}`);
}

// Bills
async function loadMyBills() {
  const tbody = $("#my-bills");
  tbody.innerHTML = loadingRow(8);
  try {
    const bills = await api.get("/portal/bills");
    if (!bills.length) { tbody.innerHTML = emptyRow(8, "No bills yet."); return; }
    tbody.innerHTML = html`${bills.map(b => html`<tr>
      <td class="td-mono">${code("B", b.bill_id)}</td>
      <td class="td-mono">${formatDate(b.bill_date)}</td>
      <td class="td-mono">${formatDate(b.due_date)}</td>
      <td class="td-mono">${fmt(b.total_amount)}</td>
      <td class="td-mono text-accent">${fmt(b.paid_amount)}</td>
      <td class="td-mono" style="${b.balance > 0 ? "color:var(--danger)" : ""}">${fmt(b.balance)}</td>
      <td>${statusBadge(b.status)}</td>
      <td><button class="btn btn-ghost btn-sm" onclick="openReceipt(${b.bill_id}, '/portal/bills/${b.bill_id}')">View</button></td>
    </tr>`)}`;
  } catch (e) { tbody.innerHTML = emptyRow(8, e.message); }
}

// Profile
async function loadProfile() {
  const box = $("#profile-content");
  try {
    const me = await loadMe();
    box.innerHTML = html`
      <div class="card">
        <div class="card-body">
          <div class="info-grid">
            ${info("Name", `${me.first_name} ${me.last_name}`)}
            ${info("Patient ID", code("P", me.patient_id))}
            ${info("Date of birth", formatDate(me.dob))}
            ${info("Gender", me.gender)}
            ${info("Sign-in email", me.login_email)}
          </div>
          <div class="form-hint">To change your name or date of birth, please visit reception with an ID.</div>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><div class="card-title">Contact & medical details</div></div>
        <form class="card-body" id="profile-form" novalidate>
          <div id="profile-error" class="error-banner"></div>
          ${formGrid([
            { name: "phone", label: "Mobile Number", type: "tel", required: true, value: me.phone },
            { name: "blood_group", label: "Blood Group", type: "select", placeholder: "Don't know", options: ["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"], value: me.blood_group },
            { name: "address", label: "Address", type: "textarea", full: true, value: me.address },
            { name: "emergency_contact_name", label: "Emergency Contact Name", value: me.emergency_contact_name },
            { name: "emergency_contact_phone", label: "Emergency Contact Phone", type: "tel", value: me.emergency_contact_phone },
            { name: "allergies", label: "Allergies", full: true, placeholder: "e.g. Penicillin, peanuts", value: me.allergies },
          ])}
          <div class="btn-row" style="margin-top:18px;justify-content:flex-end">
            <button type="button" class="btn btn-ghost" onclick="openChangePassword()">🔑 Change password</button>
            <button type="submit" class="btn btn-primary">Save changes</button>
          </div>
        </form>
      </div>`;
    $("#profile-form").onsubmit = async e => {
      e.preventDefault();
      hideError("profile-error");
      try {
        await api.put("/portal/profile", readForm(e.target));
        showToast("Profile saved!");
      } catch (err) { showError("profile-error", err.message); }
    };
  } catch (e) { box.innerHTML = html`<div class="empty-state">${e.message}</div>`; }
}

// Start
async function logout() {
  try { await api.post("/auth/logout"); } finally { window.location.href = "/login#patient"; }
}

document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });
$("#modal").addEventListener("mousedown", e => { if (e.target.id === "modal") closeModal(); });
window.addEventListener("hashchange", () => {
  const id = location.hash.slice(1);
  if (id !== state.page) showPage(id);
});

applyTheme(document.documentElement.getAttribute("data-theme") || "dark");
loadMe().then(me => {
  if (me.must_change_password) openChangePassword(true);  // signed in with a one-time password
  else showPage(location.hash.slice(1) || "home");
}).catch(() => { });
