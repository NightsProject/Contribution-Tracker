# QUICKSTART.md — Contribution Tracker One-Page Agent Handoff Checklist

## 🎯 First 5 Minutes
```bash
cd ~/Vault/Projects/Contribution Tracker
cat AGENTS.md                    # Project conventions
cat docs/design/README.md        # Decision map
cat docs/design/decision-roadmap.md  # Current phase
```

## 📍 Where Am I?
- **Project**: `~/Vault/Projects/Contribution Tracker/`
- **Design**: `docs/design/decision-*.md`
- **Plan**: `plans/phase-N-<name>.md`
- **Source**: `app/`
- **Tests**: `tests/`

## 🔄 Current Phase Loop
1. **Read** phase plan + relevant decisions
2. **Confirm** with user: "Start implementing?"
3. **Implement** one step → test → commit
4. **Verify** exit criteria
5. **Update** decision files with implementation notes
6. **Repeat** or advance phase

## ⛔ Guardrails
| Never | Always |
|-------|--------|
| Code without decision | Trace implementation to decision file |
| Skip phase exit criteria | Run all phase tests before advancing |
| Hardcode secrets | Use env/secret mechanism |
| Cross layer boundaries | `domain` imports nothing; `routes` → `services` → `domain` |
| Silent deviation | Update decision file if implementation differs |

## 📋 Key Decisions by Topic (create as needed)
| Topic | File |
|-------|------|
| Product scope | `decision-product-boundary.md` |
| Database | `decision-persistence.md` + `decision-data-design.md` |
| Background work | `decision-scheduler.md` |
| Tools/API | `decision-tools.md` |
| Testing | `decision-testing.md` |
| Risks | `decision-risks.md` |
| Open questions | `decision-open-questions.md` |

## ✅ Before Committing
- [ ] Tests pass (`uv run pytest -x`)
- [ ] Layer boundaries respected
- [ ] Conventional commit: `feat(<area>): <desc> per decision-<x>.md`
- [ ] Decision files updated if implementation diverged
- [ ] Plan checkboxes updated

## 🆘 Stuck?
1. Check `decision-risks.md` — known issue?
2. Check `decision-open-questions.md` — blocked on decision?
3. Re-read relevant decision file
4. Ask user with specific question + decision reference

## 📁 File Creation Rules
- New decision → `docs/design/decision-<kebab-case>.md`
- New plan → `plans/phase-N-<name>.md`
- Source code → `app/<layer>/` per architecture
- Tests → `tests/<layer>/` mirroring source

---

**Remember**: The decisions ARE the spec. Code is just executable decisions.