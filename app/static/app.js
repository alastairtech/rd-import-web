const AUDIO_EXTENSIONS = [".wav", ".flac", ".mp3", ".ogg", ".m4a", ".aif", ".aiff"];

const state = {
  selectedFiles: new Set(), // server-side relative paths, after upload
};

function formatDetail(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => {
        if (e && typeof e === "object") {
          const loc = Array.isArray(e.loc) ? e.loc.join(".") : "";
          return `${loc ? loc + ": " : ""}${e.msg || JSON.stringify(e)}`;
        }
        return String(e);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return String(detail);
}

async function loadSchedulerCodes() {
  const select = el("scheduler_codes");
  try {
    const res = await fetch("/api/scheduler-codes");
    const data = await res.json();
    if (!res.ok) throw new Error(formatDetail(data.detail));
    select.innerHTML = data
      .map((c) => `<option value="${c.code}">${escapeHtml(c.code)}${c.description ? " — " + escapeHtml(c.description) : ""}</option>`)
      .join("");
  } catch (err) {
    select.innerHTML = `<option disabled>(failed to load: ${err.message})</option>`;
  }
}

function getSelectedSchedulerCodes() {
  return Array.from(el("scheduler_codes").selectedOptions).map((o) => o.value);
}

const el = (id) => document.getElementById(id);

async function loadGroups() {
  const select = el("group");
  try {
    const res = await fetch("/api/groups");
    if (!res.ok) throw new Error(formatDetail((await res.json()).detail) || res.statusText);
    const groups = await res.json();
    select.innerHTML = groups
      .map((g) => `<option value="${g.name}">${g.name}</option>`)
      .join("");
    updateGroupRange(groups);
    select.addEventListener("change", () => updateGroupRange(groups));
  } catch (err) {
    select.innerHTML = `<option>(failed to load: ${err.message})</option>`;
  }
}

function updateGroupRange(groups) {
  const select = el("group");
  const g = groups.find((g) => g.name === select.value);
  el("group-range").textContent = g
    ? `Cart range: ${g.low_cart}–${g.high_cart}`
    : "";
}

function isAudioFile(filename) {
  const lower = filename.toLowerCase();
  return AUDIO_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

async function uploadAndSelect(fileList) {
  const allFiles = Array.from(fileList);
  const audioFiles = allFiles.filter((f) => isAudioFile(f.name));

  if (audioFiles.length === 0) {
    alert("No recognized audio files were in that selection.");
    return;
  }

  const filesBtn = el("choose-files-btn");
  const folderBtn = el("choose-folder-btn");
  const importBtn = el("import-btn");
  const summary = el("selected-path");

  filesBtn.disabled = true;
  folderBtn.disabled = true;
  importBtn.disabled = true;
  summary.textContent = `Uploading ${audioFiles.length} file(s)\u2026`;

  const formData = new FormData();
  audioFiles.forEach((f) => formData.append("files", f, f.name));

  try {
    const res = await fetch("/api/upload", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(formatDetail(data.detail));

    state.selectedFiles = new Set(data.paths);
    const names = data.paths.map((p) => p.split("/").pop());
    const label =
      names.length <= 3 ? names.join(", ") : `${names.slice(0, 3).join(", ")}, +${names.length - 3} more`;
    summary.textContent = `${names.length} file(s) ready to import: ${label}`;
  } catch (err) {
    summary.textContent = "none";
    alert(`Upload failed: ${err.message}`);
  } finally {
    filesBtn.disabled = false;
    folderBtn.disabled = false;
    importBtn.disabled = false;
  }
}

let cartCheckTimer = null;

function setupCartMode() {
  const radios = document.querySelectorAll('input[name="cart_mode"]');
  const cartInput = el("cart_number");
  radios.forEach((r) =>
    r.addEventListener("change", () => {
      cartInput.disabled = r.value !== "manual" || !r.checked;
      document.querySelectorAll('input[name="cart_mode"]').forEach((rr) => {
        if (rr.value === "manual") cartInput.disabled = !rr.checked;
      });
      if (cartInput.disabled) hideCartExistsNotice();
    })
  );
  cartInput.addEventListener("input", () => {
    clearTimeout(cartCheckTimer);
    cartCheckTimer = setTimeout(checkCartExists, 350);
  });
}

async function checkCartExists() {
  const cartInput = el("cart_number");
  const n = parseInt(cartInput.value, 10);
  if (cartInput.disabled || !n || n <= 0) {
    hideCartExistsNotice();
    return;
  }
  try {
    const res = await fetch(`/api/cart-check?number=${n}`);
    const data = await res.json();
    if (!res.ok) throw new Error(formatDetail(data.detail));
    if (data.exists) {
      showCartExistsNotice(n, data.group);
    } else {
      hideCartExistsNotice();
    }
  } catch (err) {
    // Don't block the form over a check failure — the server re-validates
    // this authoritatively at import time regardless.
    hideCartExistsNotice();
  }
}

function showCartExistsNotice(number, group) {
  el("cart-exists-number").textContent = number;
  el("cart-exists-group").textContent = group;
  el("cart-exists-notice").hidden = false;
}

function hideCartExistsNotice() {
  el("cart-exists-notice").hidden = true;
}

function getExistingCartAction() {
  if (el("cart-exists-notice").hidden) return null;
  const checked = document.querySelector('input[name="existing_cart_action"]:checked');
  return checked ? checked.value : null;
}

function numOrNull(id) {
  const v = el(id).value;
  return v === "" ? null : parseInt(v, 10);
}

function showModalLoading(message, title = "Importing\u2026") {
  el("modal-icon").innerHTML = `<div class="spinner" id="modal-spinner"></div>`;
  el("modal-title").textContent = title;
  el("modal-message").textContent = message;
  el("modal-raw-log").hidden = true;
  el("modal-raw-log").textContent = "";
  el("modal-raw-log-btn").textContent = "View raw log";
  el("modal-actions").hidden = true;
  el("import-modal").hidden = false;
}

function showModalResult({ success, title, message, rawLog }) {
  el("modal-icon").innerHTML = success
    ? `<span class="status-icon status-ok">\u2713</span>`
    : `<span class="status-icon status-fail">\u2717</span>`;
  el("modal-title").textContent = title;
  el("modal-message").textContent = message;
  el("modal-raw-log").hidden = true;
  el("modal-raw-log").textContent = rawLog || "";
  el("modal-raw-log-btn").textContent = "View raw log";
  el("modal-raw-log-btn").hidden = !rawLog;
  el("modal-actions").hidden = false;
}

function closeModal() {
  el("import-modal").hidden = true;
}

function toggleRawLog() {
  const pre = el("modal-raw-log");
  const btn = el("modal-raw-log-btn");
  pre.hidden = !pre.hidden;
  btn.textContent = pre.hidden ? "View raw log" : "Hide raw log";
}

async function runImport() {
  const btn = el("import-btn");

  const cartMode = document.querySelector('input[name="cart_mode"]:checked').value;
  const cartNumber = el("cart_number").value ? parseInt(el("cart_number").value, 10) : null;

  if (state.selectedFiles.size === 0) {
    alert("Choose one or more audio files, or a folder, first.");
    return;
  }
  const paths = Array.from(state.selectedFiles);
  const groupName = el("group").value;

  const payload = {
    group: groupName,
    paths: paths,
    cart_mode: cartMode,
    cart_number: cartNumber,
    existing_cart_action: getExistingCartAction(),
    delete_source: el("delete_source").checked,
    scheduler_codes: getSelectedSchedulerCodes(),
    normalization_level: numOrNull("normalization_level"),
    autotrim_level: numOrNull("autotrim_level"),
    segue_level: numOrNull("segue_level"),
    fix_broken_formats: el("fix_broken_formats").checked,
    startdate_offset: numOrNull("startdate_offset"),
    enddate_offset: numOrNull("enddate_offset"),
  };

  btn.disabled = true;
  btn.textContent = "Importing\u2026";
  const fileWord = paths.length === 1 ? "file" : "files";
  showModalLoading(`Importing ${paths.length} ${fileWord} into "${groupName}"\u2026`);

  const rawLogFor = (data) =>
    [
      `Command: ${data.command}`,
      "",
      "--- stdout ---",
      data.stdout || "(none)",
      "--- stderr ---",
      data.stderr || "(none)",
    ].join("\n");

  try {
    const res = await fetch("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    if (!res.ok) {
      showModalResult({
        success: false,
        title: "Import failed",
        message: formatDetail(data.detail),
        rawLog: null,
      });
      return;
    }

    if (data.success) {
      state.selectedFiles.clear();
      el("selected-path").textContent = "none";
      showModalResult({
        success: true,
        title: "Import complete",
        message: `Imported ${data.files_imported.length} ${data.files_imported.length === 1 ? "file" : "files"} into "${groupName}".`,
        rawLog: rawLogFor(data),
      });
    } else {
      const reason =
        data.skipped_count > 0
          ? `rdimport skipped ${data.skipped_count} file(s) it couldn't open. Check the raw log for details.`
          : `rdimport reported a problem (exit code ${data.returncode}). Check the raw log for details.`;
      showModalResult({
        success: false,
        title: "Import failed",
        message: reason,
        rawLog: rawLogFor(data),
      });
    }
  } catch (err) {
    showModalResult({
      success: false,
      title: "Import failed",
      message: `Request failed: ${err.message}`,
      rawLog: null,
    });
  } finally {
    btn.disabled = false;
    btn.textContent = "Import";
  }
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

const ADVANCED_DEFAULTS = {
  normalization_level: "-13",
  autotrim_level: "-40",
  segue_level: "-15",
  startdate_offset: "0",
  enddate_offset: "0",
  fix_broken_formats: true,
};

function resetAdvancedDefaults() {
  el("normalization_level").value = ADVANCED_DEFAULTS.normalization_level;
  el("autotrim_level").value = ADVANCED_DEFAULTS.autotrim_level;
  el("segue_level").value = ADVANCED_DEFAULTS.segue_level;
  el("startdate_offset").value = ADVANCED_DEFAULTS.startdate_offset;
  el("enddate_offset").value = ADVANCED_DEFAULTS.enddate_offset;
  el("fix_broken_formats").checked = ADVANCED_DEFAULTS.fix_broken_formats;
}

const schedulerState = {
  service: null,
  visibleMonth: null, // Date, first-of-month
  selectedDates: new Set(), // ISO strings, may span multiple visited months
  scheduledCache: new Map(), // key `${service}|${yyyy-mm}` -> Map<ISO string, color>
};

const STATUS_COLORS = ["green", "orange", "purple", "red"];

function toISODate(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseISODate(s) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function startOfMonth(d) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

function addMonths(d, n) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}

function isSameDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

async function loadServices() {
  const select = el("scheduler_service");
  try {
    const res = await fetch("/api/services");
    const data = await res.json();
    if (!res.ok) throw new Error(formatDetail(data.detail));

    const options = data.map((s) => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.name)}${s.description ? " — " + escapeHtml(s.description) : ""}</option>`);
    select.innerHTML = `<option value="">Select a service…</option>` + options.join("");

    if (data.length === 1) {
      select.value = data[0].name;
      onServiceChange();
    }
  } catch (err) {
    select.innerHTML = `<option value="">(failed to load: ${err.message})</option>`;
  }
  loadAutoSchedule();
}

function updateAutoServiceLabel() {
  el("auto-service-label").textContent = el("scheduler_service").value || "(no service selected)";
}

async function loadAutoSchedule() {
  try {
    const res = await fetch("/api/auto-schedule");
    const data = await res.json();
    if (!res.ok) throw new Error(formatDetail(data.detail));

    // Restore the saved rule's service into the top selector, but only if
    // nothing else already picked one (e.g. the single-service auto-select
    // in loadServices()) — never override an explicit user choice.
    if (data.service && !el("scheduler_service").value) {
      el("scheduler_service").value = data.service;
      onServiceChange();
    } else {
      updateAutoServiceLabel();
    }

    el("auto_enabled").checked = data.enabled;
    el("auto_weekday").value = String(data.weekday);
    el("auto_time").value = data.time;
    el("auto_days_ahead").value = String(data.days_ahead);
    el("auto_import_traffic").checked = data.import_traffic;
    renderAutoScheduleStatus(data);
  } catch (err) {
    el("auto-schedule-status").textContent = `Failed to load saved settings: ${err.message}`;
  }
}

function renderAutoScheduleStatus(data) {
  const status = el("auto-schedule-status");
  const parts = [];
  if (data.service) parts.push(`Saved for service "${data.service}".`);
  if (data.last_run) {
    const outcome = data.last_run.success
      ? "succeeded"
      : `failed (${data.last_run.failed_days} of ${data.last_run.days_run} day(s))`;
    parts.push(`Last auto run: ${data.last_run.date} — ${outcome}.`);
  } else {
    parts.push("Auto scheduling hasn't run yet.");
  }
  status.textContent = parts.join(" ");
}

async function saveAutoSchedule() {
  const btn = el("auto-save-btn");
  const payload = {
    enabled: el("auto_enabled").checked,
    service: el("scheduler_service").value,
    weekday: parseInt(el("auto_weekday").value, 10),
    time: el("auto_time").value,
    days_ahead: parseInt(el("auto_days_ahead").value, 10),
    import_traffic: el("auto_import_traffic").checked,
  };

  if (payload.enabled && !payload.service) {
    alert("Select a service at the top of the Scheduler tab before enabling auto scheduling.");
    return;
  }

  btn.disabled = true;
  try {
    const res = await fetch("/api/auto-schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatDetail(data.detail));
    await loadAutoSchedule();
  } catch (err) {
    alert(`Failed to save auto scheduling: ${err.message}`);
  } finally {
    btn.disabled = false;
  }
}

function onServiceChange() {
  const service = el("scheduler_service").value;
  schedulerState.service = service || null;
  schedulerState.selectedDates.clear();
  schedulerState.scheduledCache.clear();
  hideSchedulerOverwriteNotice();
  updateAutoServiceLabel();

  const hasService = !!schedulerState.service;
  el("scheduler-calendar-card").hidden = !hasService;
  el("scheduler-options-card").hidden = !hasService;
  el("scheduler-advanced-card").hidden = !hasService;

  if (hasService) {
    schedulerState.visibleMonth = startOfMonth(new Date());
    renderCalendar();
  }
}

function renderCalendar() {
  const month = schedulerState.visibleMonth;
  const monthNames = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];
  el("cal-month-label").textContent = `${monthNames[month.getMonth()]} ${month.getFullYear()}`;

  const grid = el("calendar-grid");
  grid.innerHTML = "";

  const firstWeekday = month.getDay(); // 0 = Sunday
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  for (let i = 0; i < firstWeekday; i++) {
    const pad = document.createElement("div");
    pad.className = "calendar-day calendar-day-pad";
    grid.appendChild(pad);
  }

  for (let day = 1; day <= daysInMonth; day++) {
    const cellDate = new Date(month.getFullYear(), month.getMonth(), day);
    const iso = toISODate(cellDate);
    const cell = document.createElement("div");
    cell.className = "calendar-day";
    cell.textContent = String(day);
    cell.dataset.date = iso;

    if (cellDate < today) cell.classList.add("is-past");
    if (isSameDay(cellDate, today)) cell.classList.add("is-today");
    if (schedulerState.selectedDates.has(iso)) cell.classList.add("is-selected");

    grid.appendChild(cell);
  }

  fetchScheduledDays();
}

async function fetchScheduledDays() {
  const month = schedulerState.visibleMonth;
  const service = schedulerState.service;
  if (!service) return;

  const key = `${service}|${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}`;
  const cached = schedulerState.scheduledCache.get(key);
  if (cached) {
    applyScheduledShading(cached);
    return;
  }

  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const dates = [];
  for (let day = 1; day <= daysInMonth; day++) {
    dates.push(toISODate(new Date(month.getFullYear(), month.getMonth(), day)));
  }

  try {
    const res = await fetch("/api/scheduled-days", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ service, dates }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatDetail(data.detail));

    const statusMap = new Map(Object.entries(data.days));
    schedulerState.scheduledCache.set(key, statusMap);
    // The service/month may have changed while this request was in flight.
    if (schedulerState.service === service && schedulerState.visibleMonth === month) {
      applyScheduledShading(statusMap);
    }
  } catch (err) {
    // Shading is informational only — don't block calendar use over it.
  }
}

function applyScheduledShading(statusMap) {
  const grid = el("calendar-grid");
  grid.querySelectorAll(".calendar-day[data-date]").forEach((cell) => {
    STATUS_COLORS.forEach((color) => cell.classList.remove(`status-${color}`));
    const color = statusMap.get(cell.dataset.date);
    if (color) cell.classList.add(`status-${color}`);
  });
}

function onCalendarGridClick(ev) {
  const cell = ev.target.closest(".calendar-day[data-date]");
  if (!cell || cell.classList.contains("is-past")) return;

  const iso = cell.dataset.date;
  if (schedulerState.selectedDates.has(iso)) {
    schedulerState.selectedDates.delete(iso);
    cell.classList.remove("is-selected");
  } else {
    schedulerState.selectedDates.add(iso);
    cell.classList.add("is-selected");
  }
  hideSchedulerOverwriteNotice();
}

function onCalPrev() {
  schedulerState.visibleMonth = addMonths(schedulerState.visibleMonth, -1);
  renderCalendar();
}

function onCalNext() {
  schedulerState.visibleMonth = addMonths(schedulerState.visibleMonth, 1);
  renderCalendar();
}

function getScheduledConflicts() {
  const allScheduled = new Set();
  const prefix = `${schedulerState.service}|`;
  for (const [key, statusMap] of schedulerState.scheduledCache.entries()) {
    if (key.startsWith(prefix)) {
      statusMap.forEach((color, iso) => allScheduled.add(iso));
    }
  }
  return Array.from(schedulerState.selectedDates)
    .filter((iso) => allScheduled.has(iso))
    .sort();
}

function showSchedulerOverwriteNotice(conflicts) {
  el("scheduler-overwrite-count").textContent = String(conflicts.length);
  el("scheduler-overwrite-dates").textContent = conflicts.join(", ");
  el("scheduler-overwrite-notice").hidden = false;
}

function hideSchedulerOverwriteNotice() {
  el("scheduler-overwrite-notice").hidden = true;
}

function onGenerateClick() {
  if (schedulerState.selectedDates.size === 0) {
    alert("Select at least one day first.");
    return;
  }

  const conflicts = getScheduledConflicts();
  if (conflicts.length > 0 && !el("overwrite_without_asking").checked) {
    showSchedulerOverwriteNotice(conflicts);
    return;
  }

  runSchedule();
}

async function runSchedule() {
  hideSchedulerOverwriteNotice();

  const service = schedulerState.service;
  const dates = Array.from(schedulerState.selectedDates).sort();
  const importTraffic = el("import_traffic").checked;
  const timeoutMinutes = parseInt(el("scheduler_timeout_minutes").value, 10) || SCHEDULER_ADVANCED_DEFAULTS.timeout_minutes;

  const genBtn = el("scheduler-generate-btn");
  genBtn.disabled = true;
  const dayWord = dates.length === 1 ? "day" : "days";
  showModalLoading(`Generating ${dates.length} ${dayWord} for "${service}"…`, "Generating schedule…");

  try {
    const res = await fetch("/api/scheduler-run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        service,
        dates,
        import_traffic: importTraffic,
        timeout_minutes: timeoutMinutes,
      }),
    });
    const data = await res.json();

    if (!res.ok) {
      showModalResult({
        success: false,
        title: "Schedule generation failed",
        message: formatDetail(data.detail),
        rawLog: null,
      });
      return;
    }

    const rawLog = data.days
      .map((d) =>
        [
          `[${d.date}] Command: ${d.command}`,
          d.stdout || "(no stdout)",
          d.stderr ? `--- stderr ---\n${d.stderr}` : null,
        ]
          .filter(Boolean)
          .join("\n")
      )
      .join("\n\n");

    if (data.success) {
      schedulerState.selectedDates.clear();
      schedulerState.scheduledCache.clear();
      renderCalendar();
      showModalResult({
        success: true,
        title: "Schedule generated",
        message: `Generated ${data.days.length} ${data.days.length === 1 ? "day" : "days"} for "${service}".`,
        rawLog,
      });
    } else {
      const failed = data.days.filter((d) => !d.success).length;
      showModalResult({
        success: false,
        title: "Schedule generation failed",
        message: `${failed} of ${data.days.length} day(s) failed. Check the raw log for details.`,
        rawLog,
      });
    }
  } catch (err) {
    showModalResult({
      success: false,
      title: "Schedule generation failed",
      message: `Request failed: ${err.message}`,
      rawLog: null,
    });
  } finally {
    genBtn.disabled = false;
  }
}

const SCHEDULER_ADVANCED_DEFAULTS = {
  timeout_minutes: 30,
};

function resetSchedulerAdvancedDefaults() {
  el("scheduler_timeout_minutes").value = String(SCHEDULER_ADVANCED_DEFAULTS.timeout_minutes);
}

function setupScheduler() {
  el("scheduler_service").addEventListener("change", onServiceChange);
  el("cal-prev-btn").addEventListener("click", onCalPrev);
  el("cal-next-btn").addEventListener("click", onCalNext);
  el("calendar-grid").addEventListener("click", onCalendarGridClick);
  el("scheduler-generate-btn").addEventListener("click", onGenerateClick);
  el("scheduler-overwrite-cancel-btn").addEventListener("click", hideSchedulerOverwriteNotice);
  el("scheduler-overwrite-confirm-btn").addEventListener("click", runSchedule);
  el("scheduler-reset-advanced-btn").addEventListener("click", resetSchedulerAdvancedDefaults);
  el("auto-save-btn").addEventListener("click", saveAutoSchedule);
}

function setupTabs() {
  const tabs = [
    { btn: el("tab-btn-import"), panel: el("tab-panel-import") },
    { btn: el("tab-btn-scheduler"), panel: el("tab-panel-scheduler") },
  ];

  tabs.forEach(({ btn, panel }) => {
    btn.addEventListener("click", () => {
      tabs.forEach(({ btn: b, panel: p }) => {
        const active = b === btn;
        b.classList.toggle("active", active);
        b.setAttribute("aria-selected", String(active));
        p.hidden = !active;
      });
    });
  });
}

el("choose-files-btn").addEventListener("click", () => el("file-input").click());
el("choose-folder-btn").addEventListener("click", () => el("folder-input").click());

el("file-input").addEventListener("change", (ev) => {
  if (ev.target.files.length > 0) uploadAndSelect(ev.target.files);
  ev.target.value = ""; // allow re-selecting the same file(s) later
});

el("folder-input").addEventListener("change", (ev) => {
  if (ev.target.files.length > 0) uploadAndSelect(ev.target.files);
  ev.target.value = "";
});

el("modal-close-btn").addEventListener("click", closeModal);
el("modal-raw-log-btn").addEventListener("click", toggleRawLog);

loadGroups();
setupCartMode();
setupTabs();
loadSchedulerCodes();
resetAdvancedDefaults();
el("import-btn").addEventListener("click", runImport);
el("reset-advanced-btn").addEventListener("click", resetAdvancedDefaults);

loadServices();
setupScheduler();
resetSchedulerAdvancedDefaults();
