# Rivendell Import Web

A small local web frontend for `rdimport`. Lets you pick a group, choose
audio file(s) or a whole folder via your browser's native file picker,
and import — without going through Rivendell's dropbox.

## How it works

- Reads DB credentials straight from `/etc/rd.conf` (`[mySQL]` section) to
  query the `GROUPS` table for the group dropdown and `SCHED_CODES` for
  the scheduler code multi-select.
- **File selection uses the browser's native "Choose files" / "Choose
  folder" dialogs.** Browsers deliberately don't expose the real
  filesystem path of a picked file for security reasons — they only hand
  over the file's name and contents — so picked files are uploaded to the
  server into a temporary staging folder
  (`RD_IMPORT_ROOT/_uploads/<uuid>/`), which is what actually gets handed
  to `rdimport`. That staging folder is deleted automatically once the
  import attempt finishes, whether it succeeds or fails.
  **This only makes sense when the browser doing the picking is running
  on the same machine as the app** (a local session, or VNC/remote
  desktop to the Debian box) — if you access this from a different
  computer, the picker shows *that* computer's files, not what's on the
  server's disk.
- Non-audio files (e.g. `.txt`, `.DS_Store`) in a folder selection are
  silently skipped, both client-side (to avoid uploading them) and
  server-side (as a backstop).
- "Auto" cart mode passes no cart-number flag to `rdimport`, which is its
  built-in default (assign the next free cart in the group's range).
  "Manual" mode lets you target a specific cart number for a single file
  via `--to-cart`, and the app checks the `CART` table first so you get a
  clear "already taken" error instead of a cryptic rdimport failure.
- The app never writes to the Rivendell database itself — every actual
  import is delegated to `rdimport`, same as if you ran it by hand.

### Scheduler tab

Generates (and optionally traffic-merges) Rivendell logs for a service,
for one or more days at a time, by driving `rdlogmanager` — the same tool
the station's own cron script uses — instead of hand-running it.

- Pick a **Service**, then click day(s) on the calendar. Each selected
  day gets its own `rdlogmanager -g [-t] -s <service> -d <offset>` call,
  run sequentially; the `-d` offset is computed from *tomorrow*, matching
  `rdlogmanager`'s own convention (`-d 0` = tomorrow, `-d -1` = today).
  Past days can't be selected.
- The calendar shades days that already have a generated log, using
  Rivendell's own log state: green (traffic merged **and** chained to the
  next day's log), orange (chained, traffic not merged), purple (traffic
  merged, not chained), red (neither — incomplete). Generating a
  already-shaded day warns before overwriting it, unless "Overwrite
  already-scheduled days without asking" is checked.
- **Import traffic during this run** adds `-t` to the `rdlogmanager` call
  for every selected day.
- Advanced options let you raise the per-day timeout (default 30
  minutes) — generating one day against a remote DB on modest hardware
  (e.g. a Raspberry Pi host) can be slow, and a run that times out is
  terminated (SIGTERM, then SIGKILL after a grace period) rather than
  left to hang.
- Requires the service's Rivendell `NAME_TEMPLATE` to be set — that's how
  a calendar date maps to a `LOGS.NAME`.

#### Auto Scheduling

A single recurring rule — service, weekday, time, and a day count — that
keeps a rolling window of logs generated ahead of time without anyone
running the Scheduler tab by hand.

- Targets whichever service is picked in the **Service** dropdown at the
  top of the tab — there's no separate service field here. Pick a
  **Weekday**, a **Time**, and **Days to keep scheduled ahead** (N), then
  check "Enable auto scheduling" and save. Saving just writes the rule to
  `data/auto_schedule.json` — it doesn't run anything itself. On reload,
  the top Service dropdown restores to whatever was last saved (unless
  something else already selected one, e.g. the single-service
  auto-select).
- A systemd timer (`rd-auto-schedule.timer`, installed by
  `install-service.sh`) ticks every 15 minutes and runs
  `app/auto_schedule_runner.py`. On the configured weekday, within 15
  minutes of the configured time, it fires once and runs
  `rdlogmanager -g [-t] -s <service> -d <offset>` for each of the next N
  days starting tomorrow — the same rolling window every time, so
  already-generated days in it get regenerated too (this is the point:
  it keeps the buffer current as traffic changes). Outside that window,
  or on any other weekday, it does nothing.
- "Import traffic on each auto run" adds `-t` to every call in the run,
  same as the manual Scheduler tab's equivalent option.
- The card shows the result of the last auto run (date, success/failure,
  days affected). This state — along with the rule itself — lives in
  `data/auto_schedule.json`, read by both the web app and the timer's
  script.
- The timer only exists if `install-service.sh` has been (re)run since
  this feature was added — see "Running as a systemd service" below.

## Setup

```bash
cd rd-import-web
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

The user running this needs:
- Read access to `/etc/rd.conf`
- Execute access to `rdimport` and `rdlogmanager` (and whatever they
  need — Rivendell's own user/group is usually simplest, e.g. run as `rd`
  or add your service user to the `rivendell` group)
- Write access to `RD_IMPORT_ROOT` (used only as a scratch space for
  uploaded files before rdimport picks them up)

## Configuration

All via environment variables, all optional:

| Variable              | Default             | Purpose                                    |
|-----------------------|----------------------|---------------------------------------------|
| `RD_CONF_PATH`         | `/etc/rd.conf`       | Where to read DB creds from                |
| `RD_IMPORT_ROOT`       | `/home/rd/import`    | Scratch directory for staged uploads before import |
| `RDIMPORT_BIN`         | `rdimport`           | Path to the rdimport binary (if not on PATH) |
| `RD_IMPORT_TIMEOUT`    | `1800`               | Max seconds a single rdimport call can run |
| `RDLOGMANAGER_BIN`     | `rdlogmanager`       | Path to the rdlogmanager binary (if not on PATH) |
| `RD_SCHEDULER_TIMEOUT` | `1800`               | Default max seconds per day for a Scheduler tab run (overridable per-run in the UI) |
| `RD_AUTO_SCHEDULE_CONFIG_PATH` | `<project root>/data/auto_schedule.json` | Where the Auto Scheduling rule and last-run result are persisted |

## Running

```bash
export RD_IMPORT_ROOT=/home/rd/import
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then visit `http://<host>:8000/` **from a browser running on the same
machine** (directly, or via VNC/remote desktop to it) — the file picker
needs to see the server's own filesystem context, and since picked files
are uploaded rather than referenced by path, this also keeps things
working correctly regardless of where `RD_IMPORT_ROOT` actually points.

Since this touches live Rivendell DB credentials, keep it off any
interface other than localhost/LAN — put it behind your existing Pangolin
instance with auth if you want remote access, rather than exposing it
directly.

## Running as a systemd service

The easiest way — run this from the project directory as the normal user
that should own the app (not root):

```bash
./install-service.sh
```

It creates/updates the venv, installs dependencies, writes systemd unit
files for both the main app and the Auto Scheduling timer
(`rd-auto-schedule.timer`, see "Auto Scheduling" above), and
enables/starts them. It uses `sudo` itself for the steps that actually
need root (writing unit files, `systemctl`), so you'll be prompted for
your password. It's safe to rerun on an already-deployed box — e.g. after
a `git pull` that adds a new unit like the Auto Scheduling timer, or any
time you just need the running service to pick up new code (see the
restart note further down).

Defaults to running as whoever invokes it, listening on
`127.0.0.1:8000`, with `RD_IMPORT_ROOT` set to that user's home
directory. Override any of these via environment variables, e.g.:

```bash
PORT=8080 RD_IMPORT_ROOT=/home/rd/import ./install-service.sh
```

Useful commands afterward:

```bash
sudo systemctl status rd-import-web
sudo systemctl restart rd-import-web
journalctl -u rd-import-web -f

# Auto Scheduling timer
systemctl list-timers rd-auto-schedule.timer   # confirm it's scheduled
journalctl -u rd-auto-schedule -f              # logs from each firing
```

**After pulling code updates on an already-deployed box, always
`systemctl restart rd-import-web`.** Templates and static files
(`index.html`, `app.js`) are read from disk on every request, but the
FastAPI route table is built once at process startup — so a `git pull`
without a restart can serve new frontend against old backend routes,
e.g. a page/button that calls an endpoint the running process doesn't
have yet, failing with a 404 that looks like a missing file.

### Manual setup (if you'd rather write the unit file yourself)

```ini
# /etc/systemd/system/rd-import-web.service
[Unit]
Description=Rivendell Import Web
After=network.target mysql.service

[Service]
Type=simple
User=rd
Group=rivendell
WorkingDirectory=/opt/rd-import-web
Environment=RD_IMPORT_ROOT=/home/rd/import
ExecStart=/opt/rd-import-web/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Adjust `User`/`Group` to whatever account has rdimport + rd.conf access
on your box.

## Notes / things worth double-checking on your install

- I've assumed "categories" maps to Rivendell **Groups**, since that's
  the argument `rdimport` actually takes and what determines cart ranges.
- I've assumed the `SCHED_CODES` table has columns `CODE` and
  `DESCRIPTION` — consistent with what I could confirm about Rivendell's
  schema, but not verified directly against a live database. If
  `/api/scheduler-codes` errors out with something like "Unknown column"
  once pointed at your real DB, it's a one-line fix in
  `app/db.py`'s `list_scheduler_codes()`.
- `rdimport` flags shift a little between Rivendell versions — worth a
  quick `rdimport --help` on your production box to confirm flag names
  match if you upgrade Rivendell later.
- The audio extension list in `app/config.py` (server-side) and
  `app/static/app.js` (client-side, for pre-upload filtering) covers the
  common Rivendell formats; keep both in sync if you add/remove one.
