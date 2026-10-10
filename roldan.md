# ROLDAN.md — Master Prompt para sa Susunod na AI

> 💡 **PAANO GAMITIN:**
> Kapag binuksan mo ang proyektong ito sa iyong bagong laptop gamit ang bagong AI assistant (Cursor, Antigravity, Claude, ChatGPT, o Copilot), **i-copy at i-paste mo lamang ang buong text box sa ibaba sa iyong chat prompt.**

---

### 📋 COPY-PASTE PROMPT PARA SA BAGONG AI:

```markdown
Kumusta! Ako si Roldan, ang developer ng RetailFlow POS project na ito.
Lilipat ako sa bagong development environment / device at ipagpapatuloy natin ang development.

Bago ka magbasa o mag-modify ng anumang code, basahin at sundin mo muna ang mga authoritative rules ng proyektong ito para maiwasan ang hallucination at structural errors:

1. **Architecture & Guidelines:**
   - Basahin ang `AI_CONTEXT_RULES.md` sa root.
   - Basahin ang `retailflow_pos/AGENTS.md` at `retailflow_pos/docs/CONTEXT.md`.
   - Sundin ang mahigpit na Clean Architecture:
     `presentation/` → `application/` → `domain/` (walang direct db/qt access sa domain).

2. **Execution & Path Rules:**
   - Lahat ng commands (tests, linting, app launch) ay dapat patakbuhin sa loob ng `retailflow_pos/` directory.
   - Paggamit ng Python: laging `python -m app.main` (BAWAL ang `python app/main.py`).
   - Huwag gagamit ng package prefix tulad ng `from retailflow_pos.xxx import ...`.

3. **Status Check:**
   - Tulungan mo akong i-verify kung maayos ang bagong setup (check venv, dependencies, database existence sa `retailflow_pos/data/retailflow.db`).
   - I-confirm sa akin kapag nabasa mo na ang rules at handa na tayong magpatuloy sa roadmap o feature implementation!
```

---

## 📌 Quick Commands Cheatsheet para kay Roldan:

| Aksyon | PowerShell Command (sa loob ng `retailflow_pos/`) |
|---|---|
| **Paganahin ang Venv** | `.\.venv\Scripts\Activate.ps1` |
| **I-run ang POS App** | `python -m app.main` |
| **I-run ang Tests** | `pytest tests/unit` |
| **Lint & Format Check** | `ruff check .` && `black . --check` |
| **Default Login** | User: `admin` \| Password: `admin123` |
