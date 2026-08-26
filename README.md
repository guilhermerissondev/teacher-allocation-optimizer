# Teacher Allocation Optimizer

**How to optimally assign hundreds of teachers to courses while respecting eligibility rules, workload limits, and institutional constraints?**

Full-stack optimization system that automates teacher-to-course allocation using CP-SAT (Constraint Programming), with data validation, audit trails, scenario simulation, and a web dashboard for operational monitoring.

This repository keeps **two released versions side by side**, so the evolution of the system is visible in the code, not only in a changelog.

## Key Highlights

| Feature | Detail |
|---------|--------|
| Solver | Google OR-Tools CP-SAT |
| Approach | Constraint programming + lexicographic phases |
| Validation | Automated rule checking with inconsistency reports |
| Scenarios | What-if policy simulations for decision support |
| Interface | React + FastAPI web dashboard |
| Audit | Full traceability per allocation round |
| Demo data | Fully synthetic — no real people, courses, or institution |

## Stack

`Python` · `OR-Tools (CP-SAT)` · `FastAPI` · `React` · `TypeScript` · `Vite` · `Pandas` · `SQLite`

## Versions

| | [`vbeta1.0/`](vbeta1.0/) | [`vbeta2.0/`](vbeta2.0/) |
|---|---|---|
| Status | First production release | Current release |
| Eligibility | Fixed: exact profile match | **User-selected at import**: exact profile, cluster with preferred profile, or pure cluster |
| Validation contract | 2.2 | 2.3 — eligibility-aware, new informational code for cluster-only coverage |
| Audit | Profile compatibility | Re-checks compatibility under the active criterion; new codes for out-of-cluster profile, divergent criterion, inconsistent adherence |
| Output schema | 2 | 3 — `BASE_ELEGIBILIDADE` per assignment, criterion and exact-vs-cluster split in the summary |
| Scenarios | Isolated secondary engine | Scenario inherits the base round's criterion; promotion requires matching criteria |
| Backward compatibility | — | Previous rounds stay readable; criterion columns backfilled as exact-profile by automatic migration |

The defaults did not change: running 2.0 with the exact-profile criterion reproduces 1.0 exactly. Both versions ship the same demo base, so the two can be compared from an identical input.

Full release notes: [`vbeta2.0/docs/10_NOTAS_DA_VERSAO.md`](vbeta2.0/docs/10_NOTAS_DA_VERSAO.md).

## Architecture

```
├── vbeta1.0/               # First production release package
└── vbeta2.0/               # Current release package
    ├── engines/primary/    # Main CP-SAT solver
    ├── engines/scenarios/  # Isolated scenario solver
    ├── backend/            # FastAPI, SQLite, orchestration
    ├── frontend/           # React app + built dist/
    ├── docs/               # Full documentation (10 chapters + glossary)
    ├── exemplos/           # Synthetic demonstration bases
    └── scripts/            # Install, test, release and anonymization tools
```

The engines are deliberately separated: the Scenarios tab never modifies or silently replaces the primary solver.

## How It Works

1. **Upload** — Spreadsheet with teachers, courses, and constraints; the eligibility criterion is chosen here
2. **Validate** — Automated rule-checking flags inconsistencies before solving
3. **Optimize** — CP-SAT solver finds optimal teacher-course assignments
4. **Audit** — Every round generates traceability reports (JSON + XLSX)
5. **Simulate** — Run alternative scenarios and compare policy impacts
6. **Promote** — A scenario becomes the official reference only when guardrails approve

## How to Run

```bash
git clone https://github.com/guilhermehrsilva/teacher-allocation-optimizer.git
cd teacher-allocation-optimizer/vbeta2.0
pip install -r requirements.txt
python executar.py
```

On Windows, `OPTIMAL.bat` checks dependencies and starts the app at `http://127.0.0.1:8000`. The frontend is pre-built; Node.js is only needed to rebuild the interface.

Start the demo by uploading `vbeta2.0/exemplos/BASE_DEMONSTRACAO_ANONIMIZADA_M52.xlsx`.

## Verifying a Release

Each version ships a `MANIFESTO_RELEASE.json` with the SHA-256 of every file:

```bash
python ./scripts/integridade_release.py --verificar
```

## Data, Privacy and Security

The demonstration bases in `exemplos/` are **entirely synthetic**. Personal identifiers (names, badge numbers, managers, coordinators, comments, links, document metadata) and the academic catalog itself (course and discipline codes and names, curricula) are invented and match no real person, course, or institution.

What is preserved is the structure that makes the tool behave as it does in production — cluster, discipline profile, matrix, module, workloads and schedules — so the demo exercises the real eligibility and optimization logic. Verified: a round over the synthetic base reproduces the homologation metrics exactly (402 offers, 377 allocated, 25 unallocated, 222 teachers used, solver `OPTIMAL`, audit `APROVADO`).

No real institutional data is present in this repository or its history. The application is designed for local use on `127.0.0.1`: it has no authentication and no TLS, and must not be exposed on a network. Real spreadsheets and results are written to the local data directory and never form part of the package — see [`vbeta2.0/docs/07_SEGURANCA_PRIVACIDADE.md`](vbeta2.0/docs/07_SEGURANCA_PRIVACIDADE.md).

## Documentation

Start with [Visão executiva](vbeta2.0/docs/00_VISAO_EXECUTIVA.md) and [Instalação e operação](vbeta2.0/docs/06_INSTALACAO_E_OPERACAO.md). Business rules, architecture, solvers, API, interface, security, homologation and troubleshooting are detailed in [`vbeta2.0/docs/`](vbeta2.0/docs/). Documentation is in Portuguese.
