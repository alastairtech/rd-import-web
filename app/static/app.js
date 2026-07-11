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

function showModalLoading(message) {
  el("modal-icon").innerHTML = `<div class="spinner" id="modal-spinner"></div>`;
  el("modal-title").textContent = "Importing\u2026";
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
loadSchedulerCodes();
resetAdvancedDefaults();
el("import-btn").addEventListener("click", runImport);
el("reset-advanced-btn").addEventListener("click", resetAdvancedDefaults);
