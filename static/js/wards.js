// Wards & rooms: bed occupancy, room status
pages.wards = { title: "Wards & Rooms", load: loadWards, perm: "view.wards" };

let roomsById = {};

async function loadWards() {
  const container = $("#wards-content");
  container.innerHTML = html`<div class="loading"><div class="spinner"></div></div>`;
  hideError("wards-error");
  try {
    const data = await api.get("/wards");
    if (!data.length) { container.innerHTML = html`<div class="empty-state">No wards found</div>`; return; }
    roomsById = {};
    data.forEach(w => w.rooms.forEach(r => { roomsById[r.room_id] = { ...r, ward_name: w.ward_name }; }));
    container.innerHTML = html`${data.map(w => {
      const used = w.total_beds - w.available_beds;
      const pct = w.total_beds ? Math.round(used / w.total_beds * 100) : 0;
      return html`
      <div class="card">
        <div class="card-header">
          <div class="card-title">${w.ward_name} <span class="badge badge-blue" style="margin-left:8px">${w.ward_type}</span></div>
          <div class="text-mono text-muted" style="font-size:0.8rem">Beds: ${used}/${w.total_beds} occupied</div>
        </div>
        <div class="card-body">
          <div class="progress-bar-wrap" style="margin-bottom:20px">
            <div class="progress-bar" style="width:${pct}%;background:${w.available_beds === 0 ? "var(--danger)" : "var(--accent2)"}"></div>
          </div>
          <div class="room-grid">
            ${w.rooms.length ? w.rooms.map(r => html`
              <div class="room-card ${r.status === "Occupied" ? "occupied" : ""}" onclick="openRoom(${r.room_id})">
                <div class="room-number">${r.room_number}</div>
                <div class="room-type">${r.room_type}</div>
                ${statusBadge(r.status)}
                ${r.patient_name ? html`<div class="room-patient">👤 ${r.patient_name}</div>` : ""}
                <div class="room-rate" style="margin-top:8px">${fmt(r.daily_rate)}/day</div>
              </div>`) : html`<div class="text-muted text-sm">No rooms added to this ward.</div>`}
          </div>
        </div>
      </div>`;
    })}`;
  } catch (e) { showError("wards-error", "Failed to load wards: " + e.message); container.innerHTML = ""; }
}

function openRoom(id) {
  const r = roomsById[id];
  if (!r) return;
  if (r.status === "Occupied") {
    showPage("admissions");
    return;
  }
  const canAdmit = r.status === "Available" && can("admissions.write");
  if (!canAdmit && !can("rooms.write")) return;
  openModal({
    title: `Room ${r.room_number}`,
    intro: `${r.ward_name} · ${r.room_type} · ${fmt(r.daily_rate)}/day`,
    submitLabel: "Update Status",
    body: html`
      ${canAdmit ? html`<button type="button" class="btn btn-primary" style="margin-bottom:18px" onclick="admitToRoom(${id})">🛏 Admit a patient to this room</button>` : ""}
      ${can("rooms.write") ? formGrid([{ name: "status", label: "Room Status", type: "select", full: true, options: ["Available", "Under Maintenance"], value: r.status }]) : ""}`,
    onSubmit: can("rooms.write") ? async data => {
      await api.put(`/rooms/${id}/status`, data);
      saved(`Room ${r.room_number} updated!`);
    } : undefined,
  });
}

async function admitToRoom(id) {
  await openAdmitForm();
  const select = $("#f_room_id");
  if (select) select.value = id;
}
