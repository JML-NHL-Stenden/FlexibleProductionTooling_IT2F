# 🏭 Flexible Production Tooling (FPT)

This project creates a **modular and intelligent production environment** that dynamically adapts work instructions using **Arkite HIM** and MQTT-based communication. It integrates QR scanning, Odoo ERP, PostgreSQL, Docker services, and real-time monitoring tools.

---

## 🎯 Objectives

- 🖥️ Dynamic work instructions via **Arkite HIM**
- 📷 QR code scanning to identify products/variants
- 🔄 Real-time event handling using **MQTT**
- ⚡ Trigger Arkite instruction flows from product codes
- 🗄️ Optional integration with **PostgreSQL** or **Odoo**
- 🐳 Docker-based deployment for replication
- 📦 Manage multiple products in a single environment

---

## 📂 Folder Structure

```
flexible-production-tooling/
├── mqtt-bridge/                  # PLC → DB bridge
├── mqtt-publish/                 # DB → MQTT publisher
├── odoo/                         # Odoo with custom module
├── pgadmin/                      # DB GUI (optional)
├── uns/                          # Mosquitto config
├── docker-compose.yml
└── .env
```

---

## ⚙️ Required Tools

- **Arkite Studio / HIM** → Create and deploy operator instructions
- **Eclipse Mosquitto** → MQTT broker for event handling
- **MQTT Explorer** → Monitor MQTT messages
- **QR Code Scanner** → Publishes product UIDs to MQTT
- **Python 3.10+** → Optional DB bridge scripts
- **Docker Desktop** → Run broker, Odoo, PostgreSQL, services
- **VS Code** → Edit configs or scripts

---

## 🚀 Step-by-Step Deployment

### ▶️ Step 1: Start Docker

Open Docker Desktop.

---

### ▶️ Step 2: Build and Start Containers

```powershell
docker-compose down -v
docker-compose up --build -d
```

Containers started:

- 📨 flexible-production-tooling-mqtt-1
- 📊 flexible-production-tooling-odoo-1
- 🗄️ flexible-production-tooling-db-1
- 📋 flexible-production-tooling-pgadmin-1
- 🔌 flexible-production-tooling-mqtt-bridge
- 📡 flexible-production-tooling-mqtt-publish

---

### ▶️ Step 3: Verify Containers

```powershell
docker ps
```

✅ All should be listed as **Up**.  
⚠️ If some are `Exited`, restart them in Docker Desktop.

---

### ▶️ Step 4: Initialize Odoo (first setup only)

```powershell
docker exec -it flexible-production-tooling-odoo-1 bash
odoo -d odoo -i base --without-demo=all --stop-after-init
```

---

### ▶️ Step 5: Open pgAdmin

🌐 Go to [http://localhost:5050](http://localhost:5050)

- Username: `admin@admin.com`
- Password: `admin`

---

### ▶️ Step 6: Register Odoo Database in pgAdmin

- General → Name: **odoo**
- Connection → Host: **db**
- Username: **odoo**
- Password: **odoo**

---

### ▶️ Step 7: Access Odoo

🌐 Go to [http://localhost:8069](http://localhost:8069)

- Email: `admin`
- Password: `admin`

Steps:

1. Go to **Settings → Developer Tools → Activate Developer Mode**
2. Go to **Apps → Search `Product Module` → Install**

---

### ▶️ Step 8: Setup MQTT Explorer

1. Add new connection
2. Set values:
   - Name: `FPT Broker`
   - Host: `localhost`
   - Port: `1883`
   - Protocol: `mqtt://`
3. Click **Connect**

Expected topics:

- `localhost/factory/products/all_product_codes`
- `localhost/factory/products/all_product_details`



---

## ✅ Verification Checklist

- [x] **Containers running** → `docker ps` shows all services
- [x] **MQTT Explorer** → Messages visible on product topics
- [x] **QR Scan** → Correct Arkite workflow triggered
- [x] **PostgreSQL** → Database accessible in pgAdmin
- [x] **Odoo** → Product visible in Product Module

---

## 🛠️ Troubleshooting

- ❌ **Containers not running** → Docker stopped  
  🔧 Start Docker Desktop

- ❌ **No MQTT messages** → Port blocked  
  🔧 Ensure port **1883** is open

- ❌ **Bridge not logging** → Service inactive  
  🔧 Restart MQTT bridge

- ❌ **Odoo blank page** → Database not initialized  
  🔧 Repeat Step 4 (Odoo init)

- ❌ **pgAdmin cannot connect** → Wrong hostname  
  🔧 Use `db` instead of `localhost`

---

## 🧰 Commit Hooks (Husky)
- Run Terminal/Powershell as Administrator:
  ```sh
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  ```

- Install dependencies once after pulling:
  ```sh
  npm install
  ```
- What runs automatically: the `pre-commit` hook calls `npm run precommit`, which compiles the Python packages (`mqtt_bridge`, `mqtt_publish`, `odoo`) to catch syntax errors early. You can trigger it manually with:
  ```sh
  npm run precommit
  ```
- Hooks stopped running? Reinstall them:
  ```sh
  npx husky install
  ```
- Commit messages must follow the Conventional Commits prefix:
  ```
  feat: add mqtt bridge checks
  fix(auth): handle expired tokens
  ```
  Allowed types:
  - `feat`: add a new user-facing feature
  - `fix`: patch a bug
  - `docs`: documentation-only changes
  - `style`: formatting changes, no logic impact
  - `refactor`: code change that neither fixes a bug nor adds a feature
  - `perf`: improve performance
  - `test`: add or adjust tests
  - `build`: build system or external dependencies
  - `ci`: continuous integration configuration
  - `chore`: routine maintenance (deps, tooling)
  - `revert`: undo a previous commit
- Emergency bypass (fix the root cause right after):
  ```sh
  HUSKY=0 git commit
  ```

---

## Branch Conventions

### Branching Naming Prefixes
```sh
<type>/<description>
```
- `main`: The main development branch (e.g., `main`, `master`, or `develope`)
- `feature/` (or `feat/`): For new features (e.g., `feature/add-login-page`, `feat/add-login-page`)
- `bugfix/` (or `fix/`): For bug fixes (e.g., `bugfix/fix-header-bug`, `fix/head-bug`)
- `hotfix/`: For urgent fixes (e.g., `hotfix/security-patch`)
- `release/`: For branches perparing a release (e.g., `release/v1.2.0`)
- `chore/`: For non-code tasks like dependency, docs updates (e.g., `chore/update-dependencies`)

### Basic Rules
1. **Use Lowercase Alphanumerics, Hyphens, and Dots:** Always use lowercase letters(`a-z`), numbers (`0-9`), and hyphens (`-`) to separate words. Avoid special characters, underscores, or spaces. For release branches, dots (`.`) may be used in the description to represent version numbers (e.g., `release/v1.2.0`).
2. **No Consecutive, Leading, or Trailing Hyphens or Dots:** Ensure that hyphens and dots do not appear consecutively (e.g., `feature/new--login`, `release/v1.-2.0`).
3. **Keep it Clear and Concise:** The branch name should be descriptive yet concise, clearly indicating the purpose of the work.
4. **Include Ticket Numbers:** If applicable, include the ticket number from your project management tool to make tracking easier. For example, for a ticket `issue-123`, the branch name coud be `feat/issue-123-new-login`.

(https://conventional-branch.github.io/)

---

## 👤 Author

**Daryl Genove, Jia Men Lam, Quentin Hamelet**
