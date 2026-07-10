# Fixed Log

> **Canonical log lives in:** `D:/EWM ROBOT/fixing codes/fixed-log.md`  
> This project-root copy is kept in sync for visibility.

---

## 2026-07-09 — Initial fixing workspace and plan created
- **Phase**: Setup
- **Issue**: No dedicated workspace or documented plan for the convergence fix.
- **Root cause**: Fixes were going to be scattered and unrecorded.
- **Files changed**: `D:/EWM ROBOT/fixing codes/fixing-plan.md`, `D:/EWM ROBOT/fixing codes/fixed-log.md`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/fixed-log.md`
- **Fix**: Created `D:/EWM ROBOT/fixing codes/` workspace, wrote `fixing-plan.md` with phased approach, and initialized `fixed-log.md` to record every subsequent fix.
- **Verification**: Folder and files exist; plan reviewed by user.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md]]

---

## 2026-07-09 — Fix pyproject.toml missing README reference
- **Phase**: 0
- **Issue**: `pyproject.toml` referenced `README_v5.md` which does not exist, breaking `python -m build`.
- **Root cause**: The v5.0 core was renamed/merged but the package metadata was not updated.
- **Files changed**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/pyproject.toml:9`
- **Fix**: Changed `readme = "README_v5.md"` to `readme = "README.md"`.
- **Verification**: `python -m build --wheel` no longer fails on missing readme file.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md#phase-0]]

---

## 2026-07-09 — Make syntax_check.py cwd-independent and fail on zero files
- **Phase**: 0
- **Issue**: `syntax_check.py` used relative globs and silently reported "0 files valid" when run outside the repo root.
- **Root cause**: `glob.glob(pattern, recursive=True)` resolves against the current working directory.
- **Files changed**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/.github/scripts/syntax_check.py`
- **Fix**: Resolve repo root from `__file__`, use `Path.glob`, and exit with code 2 if no files are found.
- **Verification**: Running the script from any directory reports the real file count and passes.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md#phase-0]]

---

## 2026-07-09 — Remove dangerous Dockerfile sed that injected shell text into main.py
- **Phase**: 0
- **Issue**: `sap-bridge/Dockerfile` ran `sed -i '/^exec/iexec 2>/dev/null || true' /app/main.py`, which could corrupt the Python entrypoint.
- **Root cause**: A shell workaround was added directly into the image build instead of a proper launcher.
- **Files changed**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/sap-bridge/Dockerfile:68`
- **Fix**: Removed the `sed` line and added a comment explaining that shell text must not be injected into Python files.
- **Verification**: Docker build no longer mutates `main.py`; `docker build -t robot-platform-sap-bridge ./sap-bridge` succeeds.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md#phase-0]]

---

## 2026-07-09 — Enable branch coverage and measure omitted code
- **Phase**: 0
- **Issue**: `.coveragerc` omitted `backends/`, `simulators/`, and `main.py`, and branch coverage was disabled, inflating coverage numbers.
- **Root cause**: Overly broad `omit` list and missing `branch = true`.
- **Files changed**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/sap-bridge/.coveragerc`
- **Fix**: Added `branch = true`; removed all omit entries except `wm_backend.py` (requires SAP SDK) and `*/tests/*`; added `raise NotImplementedError` to exclude_lines.
- **Verification**: `pytest --cov` now reports branch coverage and includes previously omitted modules.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md#phase-0]]

---

## 2026-07-09 — Make gateway tests runnable and add them to CI
- **Phase**: 0
- **Issue**: `gateway/tests/` used `@pytest.mark.asyncio` but `pytest-asyncio` was not in requirements and there was no `conftest.py`; gateway tests were not run in CI.
- **Root cause**: Async test infrastructure was missing for the gateway module.
- **Files changed**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/gateway/requirements.txt`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/gateway/tests/conftest.py`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/.github/workflows/ci.yml`
- **Fix**: Added `pytest-asyncio` to requirements; created `conftest.py` with `asyncio_mode = "auto"`; added gateway dependency install and test steps to the CI test job.
- **Verification**: `cd gateway && python -m pytest tests/ -v` passes locally; CI runs gateway tests.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md#phase-0]]

---

## 2026-07-09 — Make gateway Elasticsearch optional with JSONL fallback
- **Phase**: 0
- **Issue**: Gateway imported `AsyncElasticsearch` at module load and awaited `audit.init()` at startup; gateway failed if ES was unavailable or uninstalled.
- **Root cause**: Hard dependency on Elasticsearch with no graceful degradation.
- **Files changed**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/gateway/app/audit_logger.py`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/gateway/app/main.py:122`
- **Fix**: Lazy-imported `AsyncElasticsearch`; made `init()` fault-tolerant; added `healthy`/`status` properties; made `log()` and `query_logs()` fall back to JSONL when ES is unavailable; added audit status to `/health`.
- **Verification**: `cd gateway && python -m pytest tests/ -v` passes without ES; `/health` reports `elasticsearch_available: false` and `source: jsonl_fallback` for audit queries.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md#phase-0]]

---

## 2026-07-09 — Rename v5.0 directory to valid Python package name
- **Phase**: 0
- **Issue**: `v5.0/` is not a valid Python package/identifier and is referenced by CI, Docker Compose, and Dockerfile.
- **Root cause**: Directory name chosen before considering Python identifier rules.
- **Files changed**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/v5.0/` → `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/traffic_coordinator_v5/`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/.dockerignore`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/.github/workflows/v5-core-ci.yml`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/docker-compose-v5.yml`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/traffic_coordinator_v5/Dockerfile.traffic-coordinator`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/core/README.md`
- **Fix**: Renamed directory with `mv`; updated all path references to `traffic_coordinator_v5/`.
- **Verification**: `docker compose -f docker-compose-v5.yml config` succeeds; `python -m traffic_coordinator_v5.traffic_coordinator_main` starts.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md#phase-0]]

---

## 2026-07-09 — Stop CI from deleting package-lock.json and use npm ci
- **Phase**: 0
- **Issue**: CI deleted `dashboard/package-lock.json` before `npm install`, producing non-reproducible builds.
- **Root cause**: Windows-generated lockfile omitted Linux platform binaries, so CI worked around it by deleting the lockfile.
- **Files changed**: `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/.github/workflows/ci.yml:67`, `D:/EWM ROBOT/ROBOTIC PLATFORM CODES/.github/workflows/ci.yml:209`
- **Fix**: Removed both `rm -f package-lock.json` lines and changed `npm install` to `npm ci` for deterministic builds.
- **Verification**: CI build job uses `npm ci`; if platform-specific optional deps are missing, regenerate the lockfile on Linux with `npm install --package-lock-only`.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md#phase-0]]

---

## 2026-07-09 — Commit and push Phase 0 fixes
- **Phase**: Setup / 0
- **Issue**: Need to keep work trackable and resumable before pausing.
- **Root cause**: User session running out of resources; resuming in ~5 hours.
- **Files changed**: All Phase 0 files staged and committed; new branch `core-functions-and-fix` pushed to `origin`.
- **Fix**: Committed Phase 0 changes as `b5256b9` and pushed to `origin/core-functions-and-fix`. Remaining work (Phases 1–3) will continue on this branch.
- **Verification**: `git log --oneline -1` shows commit; `git branch -vv` shows tracking `origin/core-functions-and-fix`.
- **References**: [[D:/EWM ROBOT/fixing codes/fixing-plan.md#phase-0]]

---

*End of current log. New entries go above this line.*
