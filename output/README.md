# Output Directory

This directory contains generated LP OnePager markdown files produced by the workflow.

## Contents

- **LP OnePager files**: Generated markdown files with company financial snapshots, investment thesis, and key risks.

## File Naming Convention

Files are named using the pattern:
```
LP_OnePager_{Company_Name}_{Period_End}.md
```

Example: `LP_OnePager_Acme_Software_Inc_2025_09_30_nondet.md`

## Usage

Generated files are automatically saved here when running:
- `demo_nondet_workflow.py` (non-deterministic workflow)
- `demo_langgraph_workflow.py` (deterministic workflow)
- `demo_agent_workflow.py` (simple orchestrator)
- `demo_full_workflow.sh` (shell script)

## Note

This directory is excluded from git tracking (via `.gitignore`) to prevent generated files from being committed. Only the directory structure and this README are tracked.

