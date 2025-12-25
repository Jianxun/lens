# Tasks

## Active OKR(s)
- None yet; project bootstrap.

## Current Sprint
- T-002 — Gather project scope and first deliverables  
  - Status: Ready  
  - Owner: Architect  
  - DoD:  
    - Capture user goals and problem statement in the contract overview.  
    - Define first implementation tasks (T-003+) with DoD and verify commands.  
    - Update handoff and codebase_map if new areas are identified.  
  - Verify:  
    - `grep -q "Project overview" agents/context/contract.md`  
    - `grep -q "T-003" agents/context/tasks.md`  
  - Links: TBD

## Backlog
- T-003 — Define initial application skeleton once scope is known  
  - Status: Backlog  
  - Owner: Architect  
  - DoD:  
    - Decide directories/namespaces for first code artifacts.  
    - Add entries to codebase_map and verification steps.  
    - Draft an ADR if multiple architecture options emerge.  
  - Verify:  
    - `test -f agents/context/codebase_map.md`  
  - Links: TBD

## Done
- T-001 — Bootstrap context scaffolding  
  - Status: Done (2025-12-24)  
  - Owner: Architect  
  - DoD:  
    - Create contract, tasks, handoff, tasks_archived, and codebase_map with required sections.  
    - Record current state and next steps in handoff.  
    - Add tasks board entry and verify files exist.  
  - Verify:  
    - `ls agents/context`  
  - Links: `agents/context/contract.md`, `agents/context/handoff.md`


