// Appointments: list, filter, book, update status
pages.appointments = { title: "Appointments", load: loadAppointments, perm: "view.appointments" };

let apptFilter = "";
let apptsById = {};

function filterAppts(value) {
  apptFilter = value;
  loadAppointments();
}

async function loadAppointments() {
  setChip("appt-chips", apptFilter);
  const tbody = $("#appts-tbody");
  tbody.innerHTML = loadingRow(7);
  hideError("appts-error");
  const query = apptFilter === "today" ? `?date=${todayLocal()}`
    : apptFilter === "online" ? "?booked_via=Online"
    : apptFilter ? `?status=${apptFilter}` : "";
  try {
    const data = await api.get("/appointments" + query);
    apptsById = Object.fromEntries(data.map(a => [a.appointment_id, a]));
    if (!data.length) { tbody.innerHTML = emptyRow(7, "No appointments found"); return; }
    tbody.innerHTML = html`${data.map(a => html`<tr>
      <td class="td-mono">${code("A", a.appointment_id)}</td>
      <td class="clickable" onclick="viewPatient(${a.patient_id})">${a.patient_name}</td>
      <td>Dr. ${a.doctor_name}<div class="cell-sub">${a.specialization}</div></td>
      <td class="td-mono">${formatDate(a.appointment_date)} · ${formatTime(a.appointment_time)}</td>
      <td>${a.reason || "—"}${a.notes ? html`<div class="cell-sub">📝 ${a.notes}</div>` : ""}</td>
      <td>${statusBadge(a.status)}${a.booked_via === "Online" ? html` <span class="badge badge-online" title="Booked by the patient online">🌐 Online</span>` : ""}</td>
      <td><button class="btn btn-ghost btn-sm" data-perm="appointments.write" onclick="openApptManage(${a.appointment_id})">Manage</button></td>
    </tr>`)}`;
    applyPermissions(tbody);
  } catch (e) { showError("appts-error", "Failed to load appointments: " + e.message); tbody.innerHTML = ""; }
}

// Book
async function openAppointmentForm(preset = {}) {
  let patients, doctors;
  try {
    [patients, doctors] = await Promise.all([patientOptions(), doctorOptions()]);
  } catch (e) { showToast(e.message, true); return; }

  openModal({
    title: "Book Appointment",
    submitLabel: "Book Appointment",
    body: formGrid([
      { name: "patient_id", label: "Patient", type: "select", required: true, full: true, placeholder: "Choose a patient…", options: patients, value: preset.patient_id },
      { name: "doctor_id", label: "Doctor", type: "select", required: true, full: true, placeholder: "Choose a doctor…", options: doctors.options, hint: " " },
      { name: "appointment_date", label: "Date", type: "date", required: true, min: todayLocal(), value: todayLocal(1) },
      { name: "appointment_time", label: "Time Slot", type: "select", required: true, placeholder: "Choose a doctor first", options: [], hint: " " },
      { name: "reason", label: "Reason for Visit", full: true, placeholder: "e.g. Routine check-up" },
    ]),
    onOpen: form => {
      const doctor = $("#f_doctor_id", form), day = $("#f_appointment_date", form), slot = $("#f_appointment_time", form);
      // Show the doctor's working days, then the free time slots for that day
      const refresh = async () => {
        const d = doctors.list.find(x => String(x.doctor_id) === doctor.value);
        $("#f_doctor_id_hint", form).textContent = d
          ? `Works on: ${(d.available_days || "any day").replaceAll(",", ", ")} · Fee ${fmt(d.consultation_fee)}` : " ";
        slot.innerHTML = html`<option value="">${d ? "Loading…" : "Choose a doctor first"}</option>`;
        $("#f_appointment_time_hint", form).textContent = " ";
        if (!d || !day.value) return;
        try {
          const slots = await api.get(`/appointments/slots?doctor_id=${d.doctor_id}&date=${day.value}`);
          const free = slots.filter(s => s.available);
          slot.innerHTML = html`<option value="">${free.length ? "Choose a time…" : "No free slots"}</option>
            ${free.map(s => html`<option value="${s.time}">${formatTime(s.time)}</option>`)}`;
          $("#f_appointment_time_hint", form).textContent = `${free.length} of ${slots.length} slots free`;
        } catch (e) {
          slot.innerHTML = html`<option value="">Not available</option>`;
          $("#f_appointment_time_hint", form).textContent = e.message;
        }
      };
      doctor.addEventListener("change", refresh);
      day.addEventListener("change", refresh);
    },
    onSubmit: async data => {
      const r = await api.post("/appointments", data);
      saved(`Appointment ${code("A", r.appointment_id)} booked!`);
    },
  });
}

// Update status / notes
function openApptManage(id) {
  const a = apptsById[id];
  if (!a) return;
  openModal({
    title: `Appointment ${code("A", id)}`,
    intro: `${a.patient_name} with Dr. ${a.doctor_name} on ${formatDate(a.appointment_date)} at ${formatTime(a.appointment_time)}.`,
    submitLabel: "Update",
    body: formGrid([
      { name: "status", label: "Status", type: "select", full: true, options: ["Scheduled", "Completed", "Cancelled", "No-Show"], value: a.status },
      { name: "notes", label: "Doctor's Notes", type: "textarea", full: true, rows: 3, value: a.notes },
    ]),
    onSubmit: async data => {
      await api.put(`/appointments/${id}`, data);
      saved("Appointment updated!");
    },
  });
}
