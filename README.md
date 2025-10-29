# ⚙️ Flexible Production Tooling (FPT)

## 📌 Version
**0.1** – October 28, 2025  
👤 Author: **Daryl Genove**

---

## 👥 Client
**Gerard Van De Kolk**

## 👨‍💻 Group F
- 🧑‍💻 Thijs Thiery  
- 🧑‍💻 Jia Men Lam  
- 🧑‍💻 Fjodor Smorodins  
- 🧑‍💻 Mihael Druzeta  
- 🧑‍💻 Daryl Genove  
- 🧑‍💻 Quentin Hamelet  

---

## 🎯 Main Objective
The **Flexible Production Tooling (FPT)** system creates a modular and intelligent production environment that dynamically adapts work instructions based on real-time product input.

### 🔑 Key Objectives
- 🖥️ Enable dynamic and flexible work instructions using **Arkite HIM**  
- 📷 Use **QR code scanning** to identify products or variants  
- 🔄 Communicate via **MQTT broker** for real-time event handling  
- ⚡ Trigger Arkite instruction flows based on scanned product codes  
- 🗄️ Support optional integration with **PostgreSQL** or **Odoo** for production tracking  
- 🐳 Provide **Docker-based deployment** for simplified setup and replication  
- 📦 Ensure scalable **multi-product management** within one environment  

---

## 📂 Repository Setup

### 🛠️ 1. Clone Repository
```bash
cd ~/Desktop
mkdir flexible-production-tooling
cd flexible-production-tooling
git clone https://github.com/JML-NHL-Stenden/FlexibleProductionTooling_IT2F.git
cd FlexibleProductionTooling_IT2F
git branch
✅ Expected result: *main

🔑 2. Add Credentials
Add a .env file in the repository folder.

⚙️ Preconditions
🛠️ Tool	📋 Purpose
Arkite Studio / HIM	Create & deploy operator work instructions
Eclipse Mosquitto	MQTT broker for message handling
MQTT Explorer	Monitor MQTT messages
QR Code Scanner	Publish product UIDs to MQTT broker
Python 3.10+	Run the MQTT-to-database bridge (optional)
Docker Desktop	Deploy broker, database, and services
Visual Studio Code	Edit configurations or bridge scripts

🚀 Step-by-Step Instructions
▶️ Step 1: Install and open Docker Desktop
▶️ Step 2: Start the system
powershell
Copy code
docker-compose down -v
docker-compose up --build -d
📦 Containers started:

📨 flexible-production-tooling-mqtt-1

📊 flexible-production-tooling-odoo-1

🗄️ flexible-production-tooling-db-1

📋 flexible-production-tooling-pgadmin-1

🔌 flexible-production-tooling-mqtt-bridge

📡 flexible-production-tooling-mqtt-publish

▶️ Step 3: Verify containers
powershell
Copy code
docker ps
✅ If all containers show Up, continue.
⚠️ If some are Exited, restart them via Docker Desktop.

▶️ Step 4: Initialize Odoo (first setup only)
powershell
Copy code
docker exec -it flexible-production-tooling-odoo-1 bash
odoo -d odoo -i base --without-demo=all --stop-after-init
▶️ Step 5: Open pgAdmin
🌐 Go to: http://localhost:5050
🔑 Credentials:

Username: admin@admin.com

Password: admin

▶️ Step 6: Register Odoo database in pgAdmin
Right-click Servers → Register → Server…

General → Name: odoo

Connection → Host: db

Username: odoo

Password: odoo

▶️ Step 7: Access Odoo
🌐 Go to: http://localhost:8069
🔑 Login:

Email: admin

Password: admin

Then:

⚙️ Activate Developer Mode → Settings → Developer Tools

📦 Go to Apps → Search Product Module → Install

▶️ Step 8: Set up MQTT Explorer
➕ Add new connection

Name: FPT Broker

Host: localhost

Port: 1883

Protocol: mqtt://

✅ Click Connect

Expected topics:

localhost/factory/products/all_product_codes

localhost/factory/products/all_product_details

✅ System Verification Checklist
🔍 Test	✅ Expected Result
docker ps	All containers running
MQTT Explorer	Messages visible on topics
📷 QR Scan	Correct workflow triggered
🗄️ PostgreSQL	Database visible
📊 Odoo	Product visible in Product Module

🛠️ Troubleshooting
⚠️ Issue	❌ Cause	🔧 Solution
Containers not running	Docker stopped	Start Docker Desktop
No MQTT messages	Port blocked	Ensure port 1883 is open
Bridge not logging	Service inactive	Restart MQTT bridge
Odoo blank page	DB not initialized	Repeat Step 4
pgAdmin cannot connect	Wrong host	Use db as host name