// Doctors & staff: lists, add staff (with optional login), change status
pages.doctors = { title: "Doctors & Staff", load: loadStaffPage, perm: "view.staff" };

let staffView = "doctors";
let staffById = {};

function filterStaff(value) {
  staffView = value;
  loadStaffPage();
}

async function loadStaffPage() {
  setChip("staff-chips", staffView);
  const wrap = $("#staff-table");
  wrap.innerHTML = html`<div class="loading"><div class="spinner"></div></div>`;
  hideError("doctors-error");
  try {
    if (staffView === "doctors") {
      const data = await api.get("/doctors");
      wrap.innerHTML = html`<table>
        <thead><tr><th>Name</th><th>Specialization</th><th>Department</th><th>Available Days</th><th>Fee</th><th>Status</th></tr></thead>
        <tbody>${data.length ? data.map(d => html`<tr>
          <td><div class="flex items-center" style="gap:10px"><div class="avatar">Dr</div>
            <div>Dr. ${d.first_name} ${d.last_name}<div class="cell-sub">${d.qualification || d.license_number}</div></div></div></td>
          <td>${d.specialization}</td>
          <td>${d.dept_name || "—"}</td>
          <td class="td-mono">${(d.available_days || "—").replaceAll(",", ", ")}</td>
          <td class="td-mono text-accent">${fmt(d.consultation_fee)}</td>
          <td>${d.status === "Active" ? html`<div class="pulse"><div class="pulse-dot"></div>Active</div>` : statusBadge(d.status)}</td>
        </tr>`) : emptyRow(6, "No doctors found")}</tbody>
      </table>`;
    } else {
      const data = await api.get("/staff");
      staffById = Object.fromEntries(data.map(s => [s.staff_id, s]));
      wrap.innerHTML = html`<table>
        <thead><tr><th>Name</th><th>Role</th><th>Department</th><th>Contact</th><th>Login</th><th>Joined</th><th>Status</th><th data-perm="staff.write"></th></tr></thead>
        <tbody>${data.map(s => html`<tr>
          <td><div class="flex items-center" style="gap:10px"><div class="avatar">${initials(s.first_name + " " + s.last_name)}</div>${s.first_name} ${s.last_name}</div></td>
          <td><span class="badge badge-blue">${s.role}</span>${s.specialization ? html`<div class="cell-sub">${s.specialization}</div>` : ""}</td>
          <td>${s.dept_name || "—"}</td>
          <td class="td-mono">${s.email}<div class="cell-sub">${s.phone || ""}</div></td>
          <td class="td-mono">${s.username ? html`${s.username}<div class="cell-sub">${s.login_role}</div>` : "—"}</td>
          <td class="td-mono">${formatDate(s.hire_date)}</td>
          <td>${statusBadge(s.status)}</td>
          <td data-perm="staff.write"><button class="btn btn-ghost btn-sm" onclick="openStaffStatus(${s.staff_id})">Status</button></td>
        </tr>`)}</tbody>
      </table>`;
    }
    applyPermissions(wrap);
  } catch (e) { showError("doctors-error", "Failed to load staff: " + e.message); wrap.innerHTML = ""; }
}

async function openStaffForm() {
  let departments;
  try { departments = await api.get("/departments"); } catch (e) { showToast(e.message, true); return; }
  const roles = ["Doctor", "Nurse", "Pharmacist", "Lab Technician", "Receptionist", "Admin", "Support"];

  openModal({
    title: "Add Staff Member",
    wide: true,
    submitLabel: "Add Staff Member",
    body: formGrid([
      { name: "first_name", label: "First Name", required: true },
      { name: "last_name", label: "Last Name", required: true },
      { name: "role", label: "Role", type: "select", required: true, options: roles, value: "Nurse" },
      { name: "dept_id", label: "Department", type: "select", placeholder: "None", options: departments.map(d => ({ value: d.dept_id, label: d.dept_name })) },
      { name: "email", label: "Work Email", type: "email", required: true },
      { name: "phone", label: "Phone", type: "tel" },
      { name: "gender", label: "Gender", type: "select", placeholder: "—", options: ["Male", "Female", "Other"] },
      { name: "dob", label: "Date of Birth", type: "date", max: todayLocal(-1) },
      { name: "hire_date", label: "Joining Date", type: "date", required: true, value: todayLocal() },
      { name: "salary", label: "Monthly Salary (₹)", type: "number", min: 0 },

      { type: "section", label: "Doctor details", group: "doctor" },
      { name: "specialization", label: "Specialization", required: true, group: "doctor", placeholder: "e.g. Cardiology" },
      { name: "qualification", label: "Qualification", group: "doctor", placeholder: "e.g. MBBS, MD" },
      { name: "license_number", label: "Medical Licence No.", required: true, group: "doctor" },
      { name: "consultation_fee", label: "Consultation Fee (₹)", type: "number", min: 0, group: "doctor" },
      { name: "available_days", label: "Working Days", type: "checks", full: true, group: "doctor",
        options: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"], value: ["Mon", "Tue", "Wed", "Thu", "Fri"] },

    ]),
    onOpen: form => {
      const role = $("#f_role", form);
      const sync = () => showGroup(form, "doctor", role.value === "Doctor");
      role.addEventListener("change", sync);
      sync();
    },
    onSubmit: async data => {
      await api.post("/staff", data);
      saved(`${data.first_name} ${data.last_name} added! Create their login on the Settings page.`);
    },
  });
}

function openStaffStatus(id) {
  const s = staffById[id];
  if (!s) return;
  openModal({
    title: `${s.first_name} ${s.last_name}`,
    intro: "Inactive staff cannot log in.",
    submitLabel: "Update",
    body: formGrid([{ name: "status", label: "Status", type: "select", full: true, options: ["Active", "On Leave", "Inactive"], value: s.status }]),
    onSubmit: async data => {
      await api.put(`/staff/${id}/status`, data);
      saved("Status updated!");
    },
  });
}
