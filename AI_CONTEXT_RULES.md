# AI_CONTEXT_RULES.md — Anti-Hallucination & Architecture Specification

Para sa sinumang AI Assistant (Cursor, Claude, Copilot, ChatGPT, Antigravity, etc.) na magtatrabaho sa codebase na ito:

Basahin at sundin ang mga alituntuning ito bago gumawa ng anomang pagbabago sa code upang maiwasan ang maling assumptions at hallucinations.

---

## 1. Project Overview & Golden Rule

- **Proyekto:** RetailFlow POS (Point of Sale & Inventory Management System)
- **Tech Stack:** Python 3.12+, PySide6 (Qt for Python), SQLAlchemy 2.0 (ORM), SQLite (Dev) / PostgreSQL (Prod), Argon2-cffi.
- **Working Directory:** Lahat ng commands at executions ay dapat patakbuhin sa loob ng `retailflow_pos/`.
- **Packaging Note:** HINDI ito pip-installed package (walang `pip install -e .`). Ang layout ay flat modules sa loob ng `retailflow_pos/`.
  - **BAWAL:** `python app/main.py`
  - **TAMA:** `python -m app.main`
  - **BAWAL:** Mag-import gamit ang prefix na `retailflow_pos.` (hal. `from retailflow_pos.domain...` ❌). Diretso dapat: `from domain...` o `from application...` ✔️.

---

## 2. Strict Clean Architecture (Non-Negotiable Layers)

Mahigpit na sinusunod ng codebase na ito ang Clean / Onion Architecture. BAWAL baligtarin ang dependencies:

```
presentation/   →   application/   →   domain/
       ↑                 ↑                ↑
       |                 |         infrastructure/ (implements domain interfaces)
       +-------- shared/ (pure utility, walang domain imports) --------+
```

### Mga Mahigpit na Bawal (Zero Tolerance):
1. **`domain/` layer:**
   - HINDI kailanman mag-iimport ng SQLAlchemy, PySide6, o `app.config`.
   - Purong Python business entities, exceptions, interfaces, at domain rules lamang.
   - *Exception:* `domain/enums/__init__.py` re-exports from `app/constants.py` para sa centralized enum truth. Huwag babaguhin ito.
2. **`presentation/` layer:**
   - HINDI kailanman direktang tatawag sa `domain/` o `infrastructure/`.
   - Laging dadaan sa `application/services/`.
   - Walang business logic sa UI classes. Presentation lang para sa widgets, inputs, at event handling.
3. **`infrastructure/` layer:**
   - Ang raw SQLAlchemy `Session` ay nananatili lamang sa loob ng `infrastructure/database/repositories/`.
   - Ang application services ay gumagamit ng repositories, HINDI direct session access.
4. **`shared/` layer:**
   - Mga pure utilities lang (date helpers, formatting, base result pattern). Walang domain or framework logic.

---

## 3. Database & Entity Conventions

- **SQLAlchemy 2.0 Style:** Laging gumamit ng `Mapped[...]` at `mapped_column(...)`. Huwag gagamit ng lumang 1.4 syntax (`Column(String, ...)`).
- **Primary Keys:** UUID (stored as string) o nanoid depende sa existing model pattern.
- **Result Pattern:** Gamitin ang `shared.result.Result` (`Result.ok(...)` at `Result.fail(...)`) para sa business service returns sa halip na magbato ng generic exceptions.
- **Exceptions:** Gamitin ang custom hierarchy sa `domain/exceptions/`. Huwag mag-raise ng generic `Exception` o `ValueError` sa loob ng services.

---

## 4. UI / PySide6 Rules

- **Code-First UI:** Lahat ng screens ay gawa sa Python code (PySide6 widgets), WALANG `.ui` XML files mula sa Qt Designer.
- **Styling:** Custom styles sa `app.qss`. Gumamit ng object naming (`btn.setObjectName("primaryButton")`).
- **Dynamic QSS States:** Kapag nagpapalit ng property (hal. `btn.setProperty("active", True)`), laging tawagin ang:
  ```python
  btn.style().unpolish(btn)
  btn.style().polish(btn)
  ```
  dahil hindi nag-au-auto refresh ang dynamic selector ng Qt stylesheet.
- **Currency Format:** Gamitin ang Philippine Peso (`₱`) via `shared.date_time` formatting utilities.

---

## 5. Verification Commands (Bago Sabihing Tapos ang Task)

Kapag nag-modify ka ng code, patakbuhin ito sa sequence na ito sa loob ng `retailflow_pos/`:

```powershell
ruff check . --fix
black . --check
mypy .
pytest tests/unit
```

Huwag mag-imbento ng bagong folder structures o external libraries nang walang pahintulot. Basahin ang `retailflow_pos/docs/` para sa detalyadong specs.
