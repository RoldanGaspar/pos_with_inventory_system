# RetailFlow POS - New Laptop Setup & Migration Guide

Gabay para sa mabilis at maayos na pag-setup ng **RetailFlow POS** system kapag binuksan sa bagong laptop o device.

---

## 1. Prerequisites (Mga Kailangan Bago Magsimula)

- **Python 3.12** (Inirerekomenda: Python 3.12.x dahil sa PySide6 at dependency compatibility).
- **Git** (Naka-install at naka-configure).

---

## 2. Pag-clone ng Repository

Buksan ang terminal (PowerShell o CMD) sa nais mong folder:

```powershell
git clone https://github.com/Roldan12323/pos_with_inventory_system.git
cd pos_with_inventory_system
```

---

## 3. Important: Working Directory Rule

> ⚠️ **TANDAAN:** Ang buong application ay dinisenyo na tatakbo mula sa loob ng **`retailflow_pos/`** folder. Huwag magpatakbo ng commands sa root folder.

```powershell
cd retailflow_pos
```

---

## 4. Virtual Environment & Dependencies Setup

Gumawa ng malinis na virtual environment at i-install ang requirements:

```powershell
# 1. Gumawa ng venv gamit ang Python 3.12
python -m venv .venv

# 2. I-activate ang venv (Windows PowerShell)
.\.venv\Scripts\Activate.ps1
# Kung magka-ExecutionPolicy error, patakbuhin muna:
# Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

# 3. I-upgrade ang pip at i-install ang dependencies
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Environment Configuration (.env)

Kopyahin ang example config patungong `.env`:

```powershell
copy .env.example .env
```

*Default development configuration (SQLite) na ito. Hindi kailangang baguhin maliban kung may specific port/settings ka.*

---

## 6. Database Setup & Migration Note

### Sitwasyon A: Bagong Simula (Fresh Database)
Kung gusto mo ng malinis na database na may default seed data (admin account, roles, initial categories):
- Diretso mo lang i-run ang app (kusang gagawin ng system ang `retailflow.db` at initial seedings kapag wala pa).

### Sitwasyon B: Paglipat ng Lumang Data (Existing Data Migration)
Kung kailangan mo ang mga lumang records, benta, o produkto mula sa lumang laptop:
1. Kopyahin ang `retailflow.db` mula sa lumang laptop:
   - Lumang lokasyon: `retailflow_pos/data/retailflow.db`
2. I-paste ito sa bagong laptop:
   - Bagong lokasyon: `pos_with_inventory_system/retailflow_pos/data/retailflow.db`
3. Kung may mga in-upload na larawan/assets:
   - Kopyahin din ang folder: `retailflow_pos/data/assets/`

---

## 7. Paano Patakbuhin ang Application

Tiyaking nasa loob ka ng `retailflow_pos/` at naka-activate ang `.venv`:

```powershell
python -m app.main
```

> ⚠️ **Huwag gamitin ang:** `python app/main.py`
> Dapat laging **`python -m app.main`** upang mapanatili ang tamang Python path resolution.

### Default Login Credentials:
- **Username:** `admin`
- **Password:** `admin123`

---

## 8. Pagpapatakbo ng Tests (Verification)

Upang masigurong 100% working ang lahat sa bagong laptop:

```powershell
# Unit tests
pytest tests/unit

# Lint check
ruff check .
```
