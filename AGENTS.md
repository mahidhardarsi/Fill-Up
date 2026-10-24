# Agent Operating Manual: Fill-Up (Fuel Route Planner API)

**Audience:** the lead (orchestrator) agent and every sub-agent it spawns  |  **Companion:** PRD: Fuel Route Planner API  |  **Version:** 1.1

## 1. Purpose and How to Use This Document

This manual tells AI agents how to build the Fuel Route Planner API as a production-grade Django project. It defines who does what, how work is delegated, what contracts are frozen, what quality gates must pass, and when to stop and ask a human.

Read order for any agent: (1) the PRD, (2) this manual, (3) your task brief. If these conflict, the **PRD wins on product behaviour**, this manual wins on process, and the task brief wins on scope for that task only.

## 1A. Repository and Project Identity

All work for this project lands in one repository: [Fill-Up](https://github.com/mahidhardarsi/Fill-Up). The project is named **Fill-Up**, and every agent must confirm the remote before it commits or pushes anything.

| Item | Value |
| --- | --- |
| Project name | Fill-Up (Fuel Route Planner API) |
| Remote URL | `https://github.com/mahidhardarsi/Fill-Up.git` |
| Clone command | `git clone https://github.com/mahidhardarsi/Fill-Up.git` |
| Remote name | `origin` |
| Default branch | `main` (verify with `git remote show origin`; use what the remote reports) |
| GitHub account | `mahidhardarsi` |
| Django project root | Repository root (`manage.py` at the top level) |
| Python packages | `config`, `stations`, `routing`, `planner`, `api`, `maps` |
| This manual | Committed to the repository root as `AGENTS.md` and kept in sync with this document |
| Sub-agent definitions | `.claude/agents/<role>.md`, committed so every session spawns identical agents (section 6.6) |

### Kickoff protocol (Git/Release Engineer, before any code)

1. Clone the repository, or fetch if a local copy exists. Run `git remote -v`, `git remote show origin`, `git log --oneline -n 20`, and `git ls-files`. The remote URL must match the table above exactly; if it does not, stop and escalate.
2. Report the repository state to the orchestrator: empty, or already containing files.
3. **If it contains files:** read the README, license, and existing structure first. Adapt the plan to what exists. Never overwrite or delete existing files without orchestrator approval and, for deletions, human approval.
4. **If it is empty:** create the baseline commit on `main`: `.gitignore` (Python, Django, `.env`, `*.sqlite3`, virtual environments, caches), `README.md` stub, `AGENTS.md`, `.claude/agents/`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/CODEOWNERS`, and the supplied CSV under `data/raw/`. Ask the human which license to use; do not choose one silently.
5. Give the human the exact GitHub steps to protect `main` (require pull request, require passing CI, block force pushes and deletion). Agents usually lack admin rights, so this is a hand-off, not an action the agent takes.

### Repository rules (apply to every agent)

- Never push directly to `main`. Never force-push. Never rewrite history on a shared or merged branch.
- Agents push only to branches named `agent/<role>/<task-id>`; merges into `main` happen through pull requests that the orchestrator has approved and the Git/Release Engineer performs.
- Before the first push of any session, verify `git remote -v` shows the Fill-Up URL above.
- Credentials come from the human's configured git setup or an environment token such as `GITHUB_TOKEN` with the narrowest scope that works. Never write a token into a file, a commit, a log, or a handoff report.
- Commit only reproducible, intended files: source, tests, docs, the raw CSV in `data/raw/`, and the cleaned geocoded stations file in `data/processed/` (committed so a fresh clone runs without re-geocoding). Never commit `.env`, keys, databases, caches, or virtual environments.
- Run `git status` and `git diff --stat` before every commit and confirm that nothing unintended is staged.
- Releases use semantic version tags (`v1.0.0` for the submission) with release notes generated from conventional commits.

## 2. Prime Directive: Delegate, Do Not Do Everything

The lead agent is a **coordinator, integrator, and gatekeeper**. It is not the main implementer.

### The orchestrator MUST delegate

- All non-trivial implementation (any new module, algorithm, endpoint, command, or template).
- All test writing for code it did not write itself.
- All independent review, security checks, and performance profiling.
- Documentation drafting.

### The orchestrator MAY do directly

- Read the PRD, plan, and write task briefs.
- Freeze interface contracts and record decisions (ADRs).
- Resolve merge conflicts and wire already-reviewed pieces together (glue of roughly 30 lines or less).
- Run quality gates and decide pass or fail.
- Report to the human.

### Hard rule

If the orchestrator catches itself writing more than about 30 lines of feature code, it stops and spawns the owning sub-agent instead. Implementers never review their own work; the Reviewer agent does.

### Spawning mechanism

Use the host's native sub-agent facility (for example Claude Code sub-agents or a Task tool). If no such facility exists, emulate it: run each role in a fresh session or context, give it only its task brief and the files it needs, and require the standard handoff report (section 6.3). Never let one long context play every role.

## 3. Source of Truth and Decision Precedence

| Rank | Source | Governs |
| --- | --- | --- |
| 1 | Human instructions in the current session | Everything |
| 2 | PRD | Product behaviour, API shape, acceptance criteria |
| 3 | This manual | Process, roles, standards, gates |
| 4 | ADRs in `docs/adr/` | Technical decisions already taken |
| 5 | Task brief | Scope of one task |
| 6 | Code comments and README | Explanation only; never override the above |

Any agent that finds a contradiction stops, records it in the handoff report under **Blockers**, and does not guess.

## 4. Agent Roster

Each agent has one charter, owns specific paths, and may not edit files it does not own. If it needs a change in another agent's files, it requests it through the orchestrator.

| Agent | Charter | Owns | Must not |
| --- | --- | --- | --- |
| **Orchestrator** (main session) | Plan, brief, spawn, integrate, gate, report | `AGENTS.md`, `.claude/agents/`, `docs/adr/`, task briefs, `docs/STATUS.md` | Implement features; skip gates; review its own delegated work |
| **Git/Release Engineer** | Verify the Fill-Up remote, bootstrap or adapt the repo, create branches and worktrees, open and merge pull requests as approved, tag releases, write release notes | `.gitignore`, `.github/CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`, `CHANGELOG.md`, tags | Push to `main` directly; force-push; edit application code |
| **Data Engineer** | CSV cleaning, dedupe, offline geocoding, station loading | `stations/`, `data/processed/` | Call external APIs at request time; modify `data/raw/` |
| **Geo/Routing Engineer** | Routing and geocoding clients, caching, geometry utilities, spatial index | `routing/`, `planner/geometry.py`, `planner/corridor.py` | Exceed the external call budget |
| **Algorithm Engineer** | Fuel stop optimiser and cost maths | `planner/optimizer.py`, `planner/types.py`, `planner/service.py` | Touch HTTP, Django views, or the database |
| **API Engineer** | Endpoints, serializers, validation, error format, throttling | `api/`, `config/urls.py` | Put business logic in views |
| **Map Engineer** | GeoJSON builder, Leaflet map page, map view | `maps/` | Add paid or keyed tile providers |
| **QA Engineer** | Test strategy, fixtures, integration tests, call-count assertions | `tests/` (except `tests/perf/`) | Modify production code to make tests pass |
| **Performance Engineer** | Benchmarks, profiling, budget enforcement | `tests/perf/`, `docs/PERF.md` | Optimise without a measurement first |
| **Reviewer/Security** | Independent code review, dependency and config audit | `docs/reviews/` | Fix code itself; it reports findings |
| **DevOps/Docs Engineer** | Scaffold, settings, tooling, CI workflow, Docker, README | `config/settings/`, `.github/workflows/`, `Dockerfile`, `requirements.txt`, `README.md`, `.env.example` | Change application logic |

## 5. Repository Layout and File Ownership

```
Fill-Up/                 repository root (github.com/mahidhardarsi/Fill-Up)
  manage.py
  AGENTS.md              this manual
  .claude/agents/        one definition file per sub-agent (section 6.6)
  .github/               workflows/ci.yml, CODEOWNERS, PULL_REQUEST_TEMPLATE.md
  config/                settings/{base,dev,prod}.py, urls.py, wsgi.py, asgi.py
  stations/              models.py, services/{cleaning,geocoding,loader}.py,
                         management/commands/load_stations.py, index.py
  routing/               clients/{base,ors,osrm}.py, geocode.py, errors.py
  planner/               types.py, geometry.py, corridor.py, optimizer.py, service.py
  api/                   views.py, serializers.py, errors.py, throttling.py, urls.py
  maps/                  builders.py, views.py, templates/maps/route.html
  tests/                 unit/, integration/, fixtures/, perf/
  data/                  raw/ (original CSV, read-only), processed/ (cleaned, geocoded)
  docs/                  adr/, reviews/, PERF.md, STATUS.md
  Dockerfile  requirements.txt  .env.example  .gitignore  README.md  CHANGELOG.md
```

Rules:

- One owner per file. Parallel agents never edit the same file.
- `data/raw/` is read-only. Cleaned and geocoded outputs go to `data/processed/`.
- Business logic lives in `planner/` and `stations/services/`. Views only validate, call a service, and serialise.

## 6. Delegation Protocol

### 6.1 Principles

1. **Contracts before code.** Interfaces in section 8 are frozen before any parallel work starts.
2. **One task, one agent, one deliverable.** A task is small enough to finish and verify in one sitting.
3. **Parallelise independent work.** Tasks with no dependency between them are spawned together.
4. **Verify, do not trust.** The orchestrator re-runs the gates on every returned task. A report that says "done" is not evidence.
5. **No silent scope changes.** Anything outside the brief is reported, not done.

### 6.2 Task brief template (orchestrator to sub-agent)

```
TASK: <ID and title>
ROLE: <agent role>
GOAL: <one sentence outcome>
CONTEXT: <PRD sections and ADRs to read; nothing else>
INPUTS: <files, fixtures, contracts it may depend on>
OWNS (may edit): <explicit paths>
READ-ONLY: <paths it may read but not edit>
DELIVERABLES: <files, tests, docs>
ACCEPTANCE: <testable criteria, copied from the backlog>
CONSTRAINTS: <standards in section 9, external call budget, no new dependencies without approval>
GATES: <commands that must pass before reporting done>
DEADLINE/BUDGET: <time or effort limit; stop and report if exceeded>
```

### 6.3 Handoff report template (sub-agent to orchestrator)

```
TASK: <ID>   STATUS: done | partial | blocked
SUMMARY: <what was built, 3 to 5 lines>
FILES CHANGED: <list>
GATE RESULTS: <command: pass/fail, coverage %>
DECISIONS: <anything chosen that was not in the brief, with reason>
ASSUMPTIONS: <list>
BLOCKERS / QUESTIONS: <list>
FOLLOW-UPS: <suggested tasks, not done>
```

### 6.4 Integration protocol

1. Sub-agent works on its own branch `agent/<role>/<task-id>`.
2. Sub-agent runs its gates and submits the handoff report.
3. Orchestrator re-runs the gates on the branch.
4. Reviewer agent reviews every merge into `main` (a different agent from the author).
5. Orchestrator merges only on green gates plus a clean review. Squash merge, conventional commit message.

### 6.5 Parallel execution and isolation

- **Concurrency cap:** at most 4 sub-agents run at once. The Phase 2 peak (T02, T04, T05, T06) is exactly 4.
- **One worktree per sub-agent.** The Git/Release Engineer creates it so that two agents never share a working directory:

```
git fetch origin
git worktree add ../Fill-Up-wt/T06 -b agent/algorithm/T06 origin/main
```

- **Separate runtime state:** each worktree uses its own SQLite file and cache directory, set through environment variables, so test runs never collide.
- **Context hygiene:** a sub-agent receives only its task brief, the PRD sections it needs, and the contracts. It returns only the handoff report; long logs and profiles are saved under `docs/reviews/` or `docs/PERF.md` and referenced by path.
- **Rebase before review:** `git fetch origin && git rebase origin/main`. Conflicts that touch another agent's files go to the orchestrator, never resolved by guesswork.
- **Failure handling:** a failed or partial task is retried at most twice with a sharper brief. After that the orchestrator splits the task or escalates to the human. It does not quietly take the work over beyond the glue limit in section 2.
- **Reviewer isolation:** the Reviewer is spawned in a fresh context with only the diff, the PRD, and section 9. It never sees the author's reasoning.

### 6.6 Sub-agent definition files

When the host supports named sub-agents (for example Claude Code), each role in section 4 is a file in `.claude/agents/`, committed to the repository: `data-engineer.md`, `geo-routing-engineer.md`, `algorithm-engineer.md`, `api-engineer.md`, `map-engineer.md`, `qa-engineer.md`, `performance-engineer.md`, `reviewer-security.md`, `devops-docs-engineer.md`, and `git-release-engineer.md`. The orchestrator itself is the main session. Example:

```markdown
---
name: algorithm-engineer
description: Use for the fuel stop optimiser, cost maths, and the brute-force property test. Pure Python, no Django, no HTTP.
tools: Read, Write, Edit, Bash, Grep, Glob
model: inherit
---
You are the Algorithm Engineer for Fill-Up (repo: github.com/mahidhardarsi/Fill-Up).
Read the PRD and AGENTS.md sections 2, 8, 9, and 10 first.
You own planner/optimizer.py, planner/types.py, planner/service.py and their tests.
Edit no other path. Use Decimal for money. Prove correctness against the brute-force reference.
Finish by returning the handoff report from AGENTS.md section 6.3 and nothing else.
```

Tool permissions are part of the definition and follow least privilege:

| Agent | Can write | Shell | Network |
| --- | --- | --- | --- |
| Data Engineer | `stations/`, `data/processed/` | Yes | Census geocoder only, during the one-time batch |
| Geo/Routing Engineer | `routing/`, geometry and corridor modules | Yes | Provider sandbox or recorded fixtures in tests; none otherwise |
| Algorithm Engineer | Optimiser modules and tests | Yes | None |
| API Engineer | `api/`, `config/urls.py` | Yes | None |
| Map Engineer | `maps/` | Yes | None |
| QA Engineer | `tests/` only | Yes | None |
| Performance Engineer | `tests/perf/`, `docs/PERF.md` | Yes | None |
| Reviewer/Security | `docs/reviews/` only | Read-only commands | None |
| DevOps/Docs Engineer | Settings, CI workflow, Dockerfile, README | Yes | Package index only |
| Git/Release Engineer | Repo metadata files, tags, release notes | Git and GitHub CLI | GitHub only |

### 6.7 Spawn checklist (orchestrator, before every spawn)

- Every dependency in the backlog is merged and its gates are green.
- The contracts the task relies on are frozen.
- The brief follows the template in 6.2 and lists disjoint `OWNS` paths relative to every sub-agent running right now.
- A worktree and branch exist for the task.
- Gates and a budget are written into the brief.

## 7. Workflow Phases

```
Phase 0  Orchestrator: read PRD, confirm defaults, freeze contracts (ADRs), write sub-agent files (T00)
         Git/Release Engineer: verify the Fill-Up remote, bootstrap or adapt the repo (T00R)
   |
Phase 1  DevOps/Docs scaffold (T01)
   |
Phase 2  PARALLEL, max 4 sub-agents at once, one worktree each:
         Data (T02, then T03)  |  Geo/Routing (T04, T05)  |  Algorithm (T06)
         (Algorithm uses synthetic fixtures; no dependency on Data or Geo)
   |
Phase 3  PARALLEL:  API (T07)  |  Map (T08)
   |
Phase 4  QA integration (T09)  ->  Performance (T10)  ->  Reviewer/Security (T11)
   |
Phase 5  Docs (T12)  ->  Release gate and tag (T13)
```

Timing guide for the 3-day delivery window: Phase 0 to 2 on Day 1 (data geocoding starts first because it is the longest pole), Phase 2 finish to Phase 3 on Day 2, Phases 4 and 5 on Day 3. If any phase slips, the orchestrator cuts scope in this order: Leaflet polish, Docker, OSRM fallback. It never cuts tests, the 500-mile feasibility guarantee, or the call budget.

## 8. Frozen Interface Contracts

These are defined in Phase 0 and changed only through a new ADR. They let agents work in parallel against stubs.

```python
# planner/types.py
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True, slots=True)
class LatLon:
    lat: float
    lon: float

@dataclass(frozen=True, slots=True)
class RoutePath:
    points: tuple[LatLon, ...]          # full-resolution polyline
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
    mile_marker: float                  # distance along the route

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
# planner/optimizer.py
def plan_fuel_stops(
    stations: Sequence[CandidateStation],   # already within the corridor
    total_distance_miles: float,
    *,
    range_miles: float = 500.0,
    mpg: float = 10.0,
    initial_range_miles: float = 500.0,
    reserve_miles: float = 0.0,
) -> FuelPlan: ...                           # raises InfeasibleRouteError

# routing/clients/base.py
class RoutingClient(Protocol):
    def route(self, start: LatLon, finish: LatLon) -> RoutePath: ...   # exactly 1 external call

# routing/geocode.py
class Geocoder(Protocol):
    def geocode_us(self, query: str) -> LatLon: ...                    # raises LocationNotFound, OutsideUSA

# planner/corridor.py
class StationIndex(Protocol):
    def candidates(self, route: RoutePath, corridor_miles: float = 5.0) -> list[CandidateStation]: ...
```

Shared exceptions live in `routing/errors.py` and `planner/types.py`: `LocationNotFound`, `OutsideUSA`, `ProviderError`, `ProviderRateLimited`, `InfeasibleRouteError` (carries the offending mile range). The API layer maps them to the error table in the PRD.

## 9. Engineering Standards

| Area | Standard |
| --- | --- |
| Language and framework | Python 3.12+, latest stable Django (verify at scaffold time), Django REST Framework |
| Style | `ruff` for lint and format; line length 100; no unused code or commented-out blocks |
| Typing | Full type hints; `mypy --strict` on `planner/`, `routing/`, `stations/services/`; no untyped public functions |
| Money and quantities | `Decimal` for all money and gallons; round half-up to cents only at output |
| Settings | 12-factor: split settings (`base`, `dev`, `prod`), all secrets and provider keys from environment variables, `.env.example` committed, `.env` never committed |
| Layering | Views thin; services pure and framework-free where possible; I/O at the edges |
| Errors | Typed exceptions mapped to one error envelope: `{"error": {"code": "...", "message": "..."}}` |
| Logging | Structured logs with `request_id`, external call count, and timings; never log keys or full coordinates of private users |
| Dependencies | Minimal and pinned in `requirements.txt` (with hashes if practical); any new dependency needs orchestrator approval and an ADR line |
| Determinism | No randomness without a seed; tests never depend on the network, the clock, or file system state outside fixtures |
| Commits | Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`); small and reviewable |

## 10. Quality Gates

### 10.1 Per-task gates (the author runs them; the orchestrator re-runs them)

```
ruff check .
ruff format --check .
mypy planner routing stations/services
pytest -q --cov --cov-fail-under=90      # 90% minimum on planner/ and routing/
python manage.py makemigrations --check --dry-run
python manage.py check
```

### 10.2 Release gates (the orchestrator runs them before tagging)

- All per-task gates green on `main`.
- `python manage.py check --deploy` clean under `prod` settings (any accepted warning documented).
- Integration suite green with all providers mocked, and call-count assertions passing.
- Property test passing: greedy optimiser equals brute-force optimum on at least 500 seeded random cases.
- Performance budgets met (section 11).
- Dependency audit (`pip-audit` or equivalent) shows no known high or critical vulnerabilities.
- Reviewer report contains no open **blocker** or **major** findings.
- A clean clone can be set up and run from the README alone.

## 11. Performance Budget and Verification

| Metric | Budget |
| --- | --- |
| Local compute per request (excluding provider calls), p95 | under 300 ms |
| Cache-hit response, p95 | under 50 ms |
| Cold request total, p95 | under 2 s |
| External calls per request | 1 with coordinates, at most 3 with free-text, 0 on cache hit |
| Station index build at startup | under 2 s |

The Performance Engineer measures first (benchmarks in `tests/perf/`, profile output summarised in `docs/PERF.md`), then optimises only the measured hotspot. Likely levers: vectorised numpy distance maths, KD-tree corridor queries, route densification step size, result caching.

## 12. Security and External API Etiquette

- Provider keys come from the environment and are never committed, logged, or returned.
- Validate and bound all input: maximum string length, coordinate ranges, and USA-only checks.
- Use DRF throttling on the planning endpoint.
- Respect provider terms: send an identifying `User-Agent`, honour rate limits, back off on 429, and use a single batch for station geocoding instead of per-row loops against a public service.
- Set explicit timeouts (5 s) on every outbound call, with at most one retry.
- Production settings: `DEBUG=False`, explicit `ALLOWED_HOSTS`, secure cookie and header settings, a non-default `SECRET_KEY` required at boot.
- The Reviewer checks for secrets in history, SSRF-style misuse of user input in outbound URLs, and unbounded cache growth.

## 13. Testing Strategy by Role

| Layer | Owner | What it proves |
| --- | --- | --- |
| Unit: cleaning and dedupe | Data Engineer | Non-USA rows dropped, lowest price kept, malformed rows rejected with counts |
| Unit: geometry and corridor | Geo Engineer | Haversine, densification, mile markers, corridor membership on known fixtures |
| Unit: optimiser | Algorithm Engineer | Trip under range, one stop, cheaper station just out of range, equal prices, infeasible gap, reserve handling |
| Property: optimiser | Algorithm Engineer | Greedy result equals brute-force dynamic program on seeded random cases |
| Contract: clients | Geo Engineer | Provider responses parsed from recorded fixtures; error mapping for 4xx, 5xx, timeout, 429 |
| Integration: API | QA Engineer | Full request path with providers mocked; response schema; call counts of 0, 1, and 3 |
| Map | Map Engineer | GeoJSON validity, stop ordering, HTML renders with markers |
| Performance | Performance Engineer | Budgets in section 11 on short, medium, and coast-to-coast fixtures |

Tests must fail for the right reason: QA verifies each new test fails against a deliberately broken implementation before accepting it.

## 14. Git and Review Workflow

- `main` is always releasable. Direct commits to `main` are not allowed.
- Branch names: `agent/<role>/<task-id>`.
- Each merge needs: green gates, a handoff report, and a Reviewer verdict.
- Review severities: **blocker** (must fix), **major** (fix before release), **minor** (log as follow-up), **nit** (optional).
- The author fixes findings on the same branch; the Reviewer re-checks only what changed.
- Never force-push shared branches or rewrite merged history.

## 15. Escalation Rules

### Ask the human before proceeding when

- A PRD open question changes a user-visible number or behaviour and the default is not clearly acceptable (starting fuel, duplicate price rule, corridor width).
- A free provider's current terms or limits make the PRD call budget impossible.
- Geocoding coverage of stations is below an agreed threshold (suggested: under 95% resolved at address or city level).
- Work would exceed the 3-day window without cutting scope.

### Decide without asking when

- The choice is internal, reversible, and covered by section 9. Record it in the handoff report and, if it affects other agents, an ADR.

### Stop-the-line conditions (halt all agents)

- Secrets committed to the repository.
- A gate that was green turns red on `main`.
- Two agents have edited the same file.

## 16. Hard Rules (Never)

1. Never make a provider call at request time to find stations.
2. Never exceed 3 external calls on any request path.
3. Never use floats for money.
4. Never plan a leg longer than the vehicle range.
5. Never fabricate data, test results, benchmark numbers, or provider limits; measure or look them up.
6. Never mark a task done with failing gates or skipped tests.
7. Never review your own code.
8. Never edit files outside your ownership list.
9. Never commit secrets, raw large datasets beyond the supplied CSV, or generated caches.
10. Never leave TODOs without a linked backlog item.

## 17. Reporting to the Human

The orchestrator updates `docs/STATUS.md` after every merge and reports at each phase boundary in this format:

```
PHASE: <n>   STATUS: on track | at risk | blocked
DONE: <tasks merged, with gate evidence>
IN PROGRESS: <task, agent>
NEXT: <tasks to spawn>
RISKS / DECISIONS NEEDED: <short list>
METRICS: coverage %, p95 compute ms, external calls on the reference routes
```

Reports are factual and short. No claims without evidence from a gate run.

## 18. Definition of Done

### Task level

- Meets every acceptance line in its brief.
- All per-task gates green, run by both author and orchestrator.
- Tests added for new behaviour, including at least one failure-path test.
- Handoff report complete, with decisions and assumptions listed.
- Reviewed by a different agent and merged.

### Project level

- All PRD acceptance criteria demonstrably met.
- All release gates (section 10.2) green.
- README, `.env.example`, example requests, and demo instructions complete.
- `docs/STATUS.md` shows every backlog item closed or explicitly deferred with a reason.

## Appendix A: Seed Task Backlog

| ID | Task | Agent | Depends on | Acceptance |
| --- | --- | --- | --- | --- |
| T00 | Read PRD, confirm default assumptions, write ADR-001 (contracts), ADR-002 (assumptions), and the `.claude/agents/*.md` definitions | Orchestrator | none | Contracts in section 8 committed as stubs; open-question defaults recorded; one definition file per role |
| T00R | Repository kickoff: verify the remote is `https://github.com/mahidhardarsi/Fill-Up.git`, inspect existing content, bootstrap or adapt `main`, commit `AGENTS.md`, `.claude/agents/`, `.gitignore`, PR template, CODEOWNERS, raw CSV; hand the human the branch-protection steps | Git/Release | T00 | Remote verified; baseline on `main` with nothing existing overwritten; kickoff report delivered |
| T01 | Scaffold Django project, split settings, ruff, mypy, pytest, pre-commit, CI workflow, `.env.example` | DevOps/Docs | T00R | Gates in 10.1 run green on an empty skeleton; CI executes them on pull requests |
| T02 | CSV cleaning and dedupe module (drop non-USA, lowest price per ID, normalise text, validate prices) | Data | T01 | Unit tests cover each rule; run emits row counts per rule |
| T03 | Offline geocoding command: Census batch, city-centroid fallback, `geocode_quality` flag, `Station` model, `load_stations` command, coverage report; commit the processed stations file | Data | T02 | Idempotent command; report shows resolved percentages; coverage meets the escalation threshold |
| T04 | Routing client (OpenRouteService primary, OSRM fallback), free-text geocoder, caching, error mapping | Geo/Routing | T01 | Exactly 1 route call; contract tests from recorded fixtures; timeouts and 429 handled |
| T05 | Geometry utilities and `StationIndex`: polyline handling, densification, cumulative distance, KD-tree corridor query, mile markers | Geo/Routing | T01 | Matches hand-checked fixtures; benchmark of corridor query on a coast-to-coast route recorded |
| T06 | Fuel stop optimiser and cost calculation, plus brute-force property test | Algorithm | T00 | Unit and property tests green; infeasible gaps raise `InfeasibleRouteError` with mile range |
| T07 | API: serializers, planning view, health view, error envelope, throttling, request ID, caching of results | API | T04, T05, T06 | Response schema matches the PRD; error table honoured |
| T08 | Map: GeoJSON builder, Leaflet page, map view by request ID | Map | T06 (types), T07 (result store) | Valid GeoJSON; page shows route and numbered stops |
| T09 | Integration test suite with mocked providers and call-count assertions | QA | T07, T08 | Cases for 0, 1, and 3 external calls; error paths covered |
| T10 | Benchmarks and optimisation to meet budgets | Performance | T09 | `docs/PERF.md` records measured numbers against section 11 |
| T11 | Independent review and security audit of all merged code | Reviewer/Security | T09 | Report with severities; no open blocker or major findings at release |
| T12 | README, API examples, assumptions and limitations, demo script | DevOps/Docs | T10, T11 | A clean clone of Fill-Up runs end to end from the README |
| T13 | Release gate run, then tag `v1.0.0`, write release notes, and file the final status report | Orchestrator, with Git/Release for the tag | T12 | All items in 10.2 satisfied and evidenced; tag pushed through the approved path |

## Appendix B: Sub-Agent Charter Snippets

The orchestrator pastes the matching snippet at the top of each task brief.

- **Data Engineer:** "You prepare trustworthy station data offline. You never call external services at request time. Report coverage and rejection counts honestly; do not hide unresolved rows."
- **Geo/Routing Engineer:** "You own every interaction with routing and geocoding providers and all geometry. Exactly one route call per request. Treat provider limits as facts to look up, not to assume."
- **Algorithm Engineer:** "You write a pure, framework-free optimiser. Correctness is proven against a brute-force reference. Use Decimal for money."
- **API Engineer:** "You keep views thin. Validate input, call services, map typed errors to the error envelope, nothing more."
- **Map Engineer:** "You turn a finished plan into GeoJSON and a self-contained map page using free OpenStreetMap tiles."
- **QA Engineer:** "You try to break the system. Every test must fail against a deliberately broken implementation before you accept it. You never alter production code."
- **Performance Engineer:** "You measure before you optimise and report real numbers against the budgets."
- **Reviewer/Security:** "You did not write this code. Report findings with severity and evidence; do not fix them yourself."
- **DevOps/Docs Engineer:** "You make the project reproducible: someone with only the README can run, test, and deploy it."

* **Git/Release Engineer:** "You protect the repository. You verify the remote is Fill-Up, keep history clean, never push to `main` or force-push, and ship only what the gates and the Reviewer have cleared."
