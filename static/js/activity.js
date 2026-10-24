// Activity log (admin only): who did what, and when
pages.activity = { title: "Activity Log", load: loadActivity, perm: "view.activity" };

const searchActivity = debounce(loadActivity);

async function loadActivity() {
  const tbody = $("#activity-tbody");
  tbody.innerHTML = loadingRow(5);
  hideError("activity-error");
  try {
    const q = $("#activity-search").value;
    const data = await api.get(`/activity?search=${encodeURIComponent(q)}`);
    if (!data.length) { tbody.innerHTML = emptyRow(5, "No activity found"); return; }
    tbody.innerHTML = html`${data.map(a => html`<tr>
      <td class="td-mono">${formatDateTime(a.created_at)}</td>
      <td>${a.actor_name || "System"}<div class="cell-sub">${a.actor_type === "Patient" ? "Patient (online)" : a.actor_role || ""}</div></td>
      <td><b style="font-weight:600">${a.action}</b></td>
      <td>${a.details || "—"}</td>
      <td class="td-mono">${a.ip_address || "—"}</td>
    </tr>`)}`;
  } catch (e) { showError("activity-error", "Failed to load activity: " + e.message); tbody.innerHTML = ""; }
}
