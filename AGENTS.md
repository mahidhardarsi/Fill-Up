# Agent Operating Manual: Fill-Up (Fuel Route Planner API)

**Audience:** Antigravity Orchestrator (lead session) and all spawned subagents  |  **Companion:** PRD: Fuel Route Planner API  |  **Version:** 2.0 (Antigravity Edition)

> [!IMPORTANT]
> **Antigravity Rule Size Compliance**: This manual is structured to remain strictly below the Antigravity 24 KB (24,000 bytes) rule-loading ceiling to guarantee full inline context retention without truncation.

---

## 1. Purpose and How to Use This Document

This manual instructs Antigravity agents on building the Fuel Route Planner API as a production-grade Django system. It defines responsibilities, delegation boundaries, frozen contracts, quality gates, and escalation protocols.

**Precedence Order:**
1. Human instructions in the active session
2. PRD (`PRD Fuel Route Planner API.md`)
3. This manual (`AGENTS.md`)
4. Architecture Decision Records (`docs/adr/`)
5. Task brief
6. Code comments and documentation

---

## 2. Project & Repository Identity

All work lands in repository [Fill-Up](https://github.com/mahidhardarsi/Fill-Up). Confirm the remote before pushing.

| Item | Specification |
| --- | --- |
| Project Name | Fill-Up (Fuel Route Planner API) |
| Remote URL | `https://github.com/mahidhardarsi/Fill-Up.git` |
| Remote Name / Default Branch | `origin` / `main` |
| Primary Workspace Root | Repository root (`manage.py` at top level) |
| Python Packages | `config`, `stations`, `routing`, `planner`, `api`, `maps` |
| Subagent Definitions | `.agents/agents/<role>.md` (Antigravity workspace convention) |
| Workspace Rules & Skills | `AGENTS.md`, `.agents/skills/` |

### Repository & Version Control Rules
- Never push directly to `main`. Never force-push or rewrite merged history.
- Feature work occurs on `agent/<role>/<task-id>` branches or Antigravity isolated workspaces (`Workspace: 'branch'` or `'share'`).
- Merges into `main` require green per-task gates and an independent Reviewer sign-off.
- Commit clean, reproducible files: source, tests, docs, raw CSV (`data/raw/`), and cleaned geocoded data (`data/processed/`). Never commit `.env`, caches, `.sqlite3`, or virtual environments.
- On Windows, execute Git commands via direct path `& "C:\Program Files\Git\cmd\git.exe"` or verified PATH.

---

## 3. Prime Directive: Orchestrate & Delegate

The lead agent is an **orchestrator, integrator, and quality gatekeeper**, not a monolithic implementer.

### The Orchestrator MUST Delegate
- Non-trivial implementation (modules, algorithms, endpoints, commands, templates).
- Test suite authoring for delegated components.
- Independent code review, security audits, and performance profiling.
- Detailed documentation drafting.

### The Orchestrator MAY Directly Perform
- Task planning, writing briefs, and updating `docs/STATUS.md` (surfaced as Antigravity Artifacts).
- Freezing interface contracts and writing ADRs (`docs/adr/`).
- Resolving integration glue code (strictly $\le$ 30 lines).
- Running verification quality gates.
- Communicating status and open questions to the human.

### Antigravity Subagent Spawning Mechanism
- Invoke native subagents via `invoke_subagent` using `.agents/agents/<role>.md` definitions or `define_subagent`.
- Set `Workspace: 'share'` (worktree-style shared repo) or `Workspace: 'branch'` for isolated edits.
- Antigravity uses **reactive wakeups**: do not poll running subagents or tasks. The system automatically resumes execution when subagent messages (`send_message`) or background task notifications arrive.
- Recommended slash commands: suggest `/plan` during architecture, `/teamwork` for parallel tracks, and `/boost` for algorithmic verification.

---

## 4. Agent Roster & Ownership

Each agent owns specific file paths. Parallel agents must never edit the same file.

| Agent | Charter & Responsibilities | Owned Paths | Tool Capabilities |
| --- | --- | --- | --- |
| **Orchestrator** | Planning, briefs, subagent spawning, gate execution, artifacts, status | `AGENTS.md`, `docs/adr/`, `docs/STATUS.md`, task briefs | All tools; Orchestrator only |
| **Git/Release** | Repo bootstrap, branches, pull requests, releases, tags | `.gitignore`, `.github/`, `CHANGELOG.md` | WriteTools, Shell (Git only) |
| **Data Engineer** | CSV cleaning, deduplication, offline geocoding, station loader | `stations/`, `data/processed/` | WriteTools, Shell, BypassSandbox for Census batch |
| **Geo/Routing** | Routing & geocoding clients, caching, geometry, corridor index | `routing/`, `planner/geometry.py`, `planner/corridor.py` | WriteTools, Shell, Sandboxed fixtures |
| **Algorithm** | Optimal fuel stop algorithm, cost maths, property tests | `planner/optimizer.py`, `planner/types.py`, `planner/service.py` | WriteTools, Shell (no HTTP/DB) |
| **API Engineer** | DRF views, serializers, error mapping, throttling | `api/`, `config/urls.py` | WriteTools, Shell (thin views) |
| **Map Engineer** | GeoJSON builder, Leaflet view, HTML template, UI widgets | `maps/` | WriteTools, Shell, Generative UI |
| **QA Engineer** | Test strategy, integration suites, call-budget assertions | `tests/` (except `tests/perf/`) | WriteTools, Shell (no prod code edits) |
| **Performance** | Benchmarks, profiling, latency & memory budget enforcement | `tests/perf/`, `docs/PERF.md` | WriteTools, Shell |
| **Reviewer** | Independent code review, security and config audit | `docs/reviews/` | Read-only commands, no self-fixes |
| **DevOps/Docs** | Django settings, dependencies, Docker, CI workflows, README | `config/settings/`, `Dockerfile`, `requirements.txt`, `README.md` | WriteTools, Shell |

---

## 5. Repository Layout

```
Fill-Up/
  manage.py
  AGENTS.md                       # Antigravity operational manual (<= 24 KB)
  .agents/
    agents/<role>.md             # Role charters & prompts
    skills/                      # Antigravity skill bundles (e.g. ui-ux-pro-max)
  .github/workflows/ci.yml       # GitHub Actions CI
  config/settings/{base,dev,prod}.py
  config/urls.py, wsgi.py, asgi.py
  stations/                      # models.py, loader.py, cleaning.py, geocoding.py
  routing/                       # clients/{base,ors,osrm}.py, geocode.py, errors.py
  planner/                       # types.py, geometry.py, corridor.py, optimizer.py, service.py
  api/                           # views.py, serializers.py, errors.py, throttling.py, urls.py
  maps/                          # builders.py, views.py, templates/maps/route.html
  tests/                         # unit/, integration/, fixtures/, perf/
  data/raw/                      # fuel-prices-for-be-assessment.csv (read-only)
  data/processed/                # stations_geocoded.json / .csv (committed)
  docs/                          # adr/, reviews/, PERF.md, STATUS.md
  Dockerfile, requirements.txt, .env.example, README.md, CHANGELOG.md
```

---

## 6. Delegation & Execution Protocols

### 6.1 Task Brief Template (Orchestrator $\to$ Subagent)
```markdown
TASK: <ID and Title>
ROLE: <Agent Role>
GOAL: <Single clear outcome sentence>
CONTEXT: <PRD sections, ADRs, relevant frozen contracts>
OWNS (May Edit): <Explicit file paths>
READ-ONLY: <Explicit reference paths>
DELIVERABLES: <Files, unit tests, docs>
ACCEPTANCE: <Testable criteria>
GATES: <Commands that must pass before handoff>
SANDBOX POLICY: <Standard (BypassSandbox: false) | Network Required (BypassSandbox: true)>
```

### 6.2 Handoff Report Template (Subagent $\to$ Orchestrator)
```markdown
TASK: <ID>   STATUS: done | partial | blocked
SUMMARY: <3 to 5 lines on implemented outcome>
FILES CHANGED: <List of modified paths>
GATE RESULTS: <Command outputs: ruff, mypy, pytest coverage %>
DECISIONS & ASSUMPTIONS: <Technical choices within scope>
BLOCKERS / QUESTIONS: <Unresolved issues requiring escalation>
FOLLOW-UPS: <Recommended next tasks>
```

### 6.3 Antigravity Sandbox & Windows Terminal Rules
1. **Sandboxed First**: Run commands inside Antigravity Standard Sandbox (`BypassSandbox: false`). Auto-approval matches command prefixes.
2. **Elevate Only When Essential**: Use `BypassSandbox: true` exclusively for network-dependent commands (e.g., one-time Census geocoding batch, live provider contract test, or pip package install).
3. **Command Shapes**: Prefer direct binary execution on Windows (`.venv\Scripts\python.exe manage.py test`). Avoid complex subshell expansions (`$()`) that break prefix auto-approval.
4. **No Busy Polling**: Do not sleep-loop in terminal. Rely on Antigravity's reactive notifications for background tasks and subagents.

---

## 7. Frozen Interface Contracts (ADR-001)

These interfaces are frozen in Phase 0. Subagents code against these types without cross-blocking.

```python
# planner/types.py
from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

@dataclass(frozen=True, slots=True)
class LatLon:
    lat: float
    lon: float

@dataclass(frozen=True, slots=True)
class RoutePath:
    points: tuple[LatLon, ...]          # Polyline points
    distance_miles: float

@dataclass(frozen=True, slots=True)
class CandidateStation:
    station_id: str
    name: str
    address: str
    city: str
    state: str
    location: LatLon
    price_per_gallon: Decimal
    mile_marker: float                  # Cumulative distance along route

@dataclass(frozen=True, slots=True)
class FuelStop:
    order: int
    station: CandidateStation
    gallons: Decimal
    cost: Decimal

@dataclass(frozen=True, slots=True)
class FuelPlan:
    stops: tuple[FuelStop, ...]
    total_cost: Decimal
    total_gallons_purchased: Decimal
    gallons_consumed: Decimal
```

```python
# planner/optimizer.py & routing protocols
from typing import Protocol, Sequence

def plan_fuel_stops(
    stations: Sequence[CandidateStation],
    total_distance_miles: float,
    *,
    range_miles: float = 500.0,
    mpg: float = 10.0,
    initial_range_miles: float = 500.0,
    reserve_miles: float = 0.0,
) -> FuelPlan: ...                       # Raises InfeasibleRouteError

class RoutingClient(Protocol):
    def route(self, start: LatLon, finish: LatLon) -> RoutePath: ...

class Geocoder(Protocol):
    def geocode_us(self, query: str) -> LatLon: ...

class StationIndex(Protocol):
    def candidates(self, route: RoutePath, corridor_miles: float = 5.0) -> list[CandidateStation]: ...
```

**Shared Exceptions (`routing/errors.py`, `planner/types.py`):**
`LocationNotFound`, `OutsideUSA`, `ProviderError`, `ProviderRateLimited`, `InfeasibleRouteError`.

---

## 8. Engineering Standards

| Area | Production Standard |
| --- | --- |
| Runtime & Framework | Python 3.12+, Django (latest stable), Django REST Framework |
| Lint & Formatting | `ruff check .` and `ruff format --check .` (line-length 100) |
| Static Typing | `mypy --strict` on `planner/`, `routing/`, `stations/services/` |
| Financial Maths | `Decimal` for all fuel prices, costs, and gallons. Round half-up to cents at serialization |
| Configuration | 12-factor split (`base.py`, `dev.py`, `prod.py`). Keys from environment variables. `.env` ignored |
| Architecture | Thin views (validate $\to$ service $\to$ serialize). Core algorithm is pure Python without framework dependencies |
| Error Envelope | Standardized schema: `{"error": {"code": "...", "message": "..."}}` |
| Security | Sanitized inputs, DRF throttling, timeouts (5s) with 1 retry on outbound calls, zero secret leakage |

---

## 9. Quality Gates

### 9.1 Per-Task Gate (Run by Author, Verified by Orchestrator)
```powershell
ruff check .
ruff format --check .
mypy planner routing stations/services
pytest -q --cov --cov-fail-under=90
python manage.py makemigrations --check --dry-run
python manage.py check
```

### 9.2 Release Gates (Before Tagging `v1.0.0`)
1. All per-task gates green across the complete codebase.
2. `python manage.py check --deploy` clean under `config.settings.prod`.
3. Property verification: Greedy optimizer yields identical costs to brute-force DP on $\ge 500$ seeded test scenarios.
4. Call-count assertions verified: 0 calls on cache hits, 1 call with coordinates, $\le 3$ calls with text.
5. Performance budgets verified and documented in `docs/PERF.md`.
6. Dependency audit (`pip-audit`) reports 0 high/critical CVEs.
7. Independent Reviewer confirms zero open blocker/major defects.

---

## 10. Performance Budgets

| Metric | Budget Target | Verification Method |
| --- | --- | --- |
| Local Compute (excluding network), p95 | $< 300\text{ ms}$ | Benchmarked on coast-to-coast route fixture |
| Cache-Hit Response, p95 | $< 50\text{ ms}$ | Integration test with cached response |
| Cold Request Total, p95 | $< 2.0\text{ s}$ | End-to-end integration test with mock network |
| External API Calls | $1\text{ (coords)}, \le 3\text{ (text)}, 0\text{ (cached)}$ | Unit and integration call-counter assertions |
| Spatial Index Startup Build | $< 2.0\text{ s}$ | Startup time benchmark with 8,000+ stations |

---

## 11. Testing & Verification Matrix

- **Data Cleaning & Geocoding**: Verify deduplication keeps lowest price, discards Canadian provinces, handles unresolvable addresses with city centroids, and produces zero runtime external calls.
- **Geometry & Spatial Index**: Verify polyline densification (1–2 mile steps), KD-tree radius search, cumulative mile markers, and bounding-box prefilters.
- **Optimizer**: Test edge cases (trip $< 500$ mi $\to$ 0 stops, single stop, cheaper station just outside reach, equal pricing, and unbridgeable gaps $> 500$ mi).
- **Property-Based Testing**: Cross-check greedy solution against exhaustive dynamic programming across seeded random topologies.
- **Mocked Integration**: Assert end-to-end payload format and exact external call counts.

---

## 12. Escalation & Stop-the-Line Protocol

### Escalate to Human Immediately When:
- PRD requirements conflict with external provider free-tier rate limits.
- Geocoding coverage of US truckstops falls below 95%.
- Scope risks exceeding the delivery timeframe without scope adjustment.

### Stop-the-Line (Halt All Subagents):
- Any credential or API secret committed to git.
- Any regression breaking quality gates on `main`.
- Concurrent file edit collision between subagents.

---

## 13. Antigravity Artifacts & Status Reporting

The Orchestrator maintains project transparency by writing structured reports to `docs/STATUS.md` and presenting them as Antigravity Artifacts:
- **Phase Boundary Reports**: Delivered via Antigravity Artifacts with metadata `UserFacing: true`.
- **Interactive Visualizations**: Route previews and stop markers rendered via Antigravity Generative UI / HTML widgets.
- **Review Findings**: Stored in `docs/reviews/` with categorized severities (**blocker**, **major**, **minor**, **nit**).

---

## 14. Phased Delivery Roadmap

```
Phase 0: Architecture, ADRs, Contracts, Antigravity Subagent Definitions
Phase 1: Project Scaffolding, Tooling & CI Configuration
Phase 2 (Parallel, Max 4 Subagents):
  - Data Engineer: CSV Cleaning, Deduplication, Offline Geocoding & Loader
  - Geo Engineer: Routing/Geocoding Clients & Spatial Corridor Index
  - Algorithm Engineer: Pure Greedy Optimizer & Property-Based DP Tests
Phase 3 (Parallel):
  - API Engineer: DRF Endpoints, Serializers, Throttling & Caching
  - Map Engineer: GeoJSON Builders & Leaflet Route Visualization Page
Phase 4: QA Integration Testing, Performance Profiling & Security Review
Phase 5: Documentation, Verification Gate Run & Release Tagging (v1.0.0)
```

---

## Appendix: Subagent Charters

- **Data Engineer**: "Build reliable offline station data. Deduplicate deterministically to lowest price, geocode offline with Census + city fallback, and never call external APIs at request time."
- **Geo/Routing Engineer**: "Own routing/geocoding provider integrations and geometry. Guarantee exactly 1 route call per trip. Build KD-tree corridor search."
- **Algorithm Engineer**: "Author the pure, framework-free fuel optimizer. Use Decimal for money. Prove global optimality against a brute-force dynamic program."
- **API Engineer**: "Maintain thin, robust views. Validate input, orchestrate services, map typed domain exceptions to the API error envelope, and throttle endpoints."
- **Map Engineer**: "Generate valid GeoJSON and an interactive Leaflet visualization page with numbered stop markers and trip metrics."
- **QA Engineer**: "Enforce the test matrix and call budgets. Ensure tests fail against broken implementations. Never modify production code to make tests pass."
- **Performance Engineer**: "Profile before optimizing. Benchmark corridor queries, KD-tree lookups, and latency budgets on reference routes."
- **Reviewer/Security**: "Audit independent code changes for security, SSRF risks, and architectural integrity. Report severity-categorized findings without self-fixing."
- **DevOps/Docs**: "Ensure complete reproducibility. A user or agent cloning the repository must be able to install, migrate, load, and test seamlessly from the README."
- **Git/Release**: "Safeguard repository integrity. Verify remotes, enforce clean branching and PR workflows, and publish tagged releases with changelogs."
