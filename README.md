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

## 📂 Project Setup

### 1. Clone Repository
```bash
cd ~/Desktop
mkdir flexible-production-tooling
cd flexible-production-tooling
git clone https://github.com/JML-NHL-Stenden/FlexibleProductionTooling_IT2F.git
cd FlexibleProductionTooling_IT2F
git branch
✅ Expected: *main

2. Add .env file
Place your environment configuration in the project root.

⚙️ Required Tools
Tool	Purpose
Arkite Studio / HIM	Create and deploy operator instructions
Eclipse Mosquitto	MQTT broker for event handling
MQTT Explorer	Monitor MQTT messages
QR Code Scanner	Publishes product UIDs to MQTT
Python 3.10+	Optional DB bridge scripts
Docker Desktop	Run broker, Odoo, PostgreSQL, services
VS Code	Edit configs or scripts

🚀 Step-by-Step Deployment
▶️ Step 1: Start Docker
Open Docker Desktop.

▶️ Step 2: Build and Start Containers
powershell
Copy code
docker-compose down -v
docker-compose up --build -d
Containers started:

📨 flexible-production-tooling-mqtt-1

📊 flexible-production-tooling-odoo-1

🗄️ flexible-production-tooling-db-1

📋 flexible-production-tooling-pgadmin-1

🔌 flexible-production-tooling-mqtt-bridge

📡 flexible-production-tooling-mqtt-publish

▶️ Step 3: Verify Containers
powershell
Copy code
docker ps
✅ All listed as Up.

▶️ Step 4: Initialize Odoo (first setup only)
powershell
Copy code
docker exec -it flexible-production-tooling-odoo-1 bash
odoo -d odoo -i base --without-demo=all --stop-after-init
▶️ Step 5: Open pgAdmin
🌐 http://localhost:5050
Login: admin@admin.com / admin

▶️ Step 6: Register Odoo DB
General → Name: odoo

Connection → Host: db

Username: odoo

Password: odoo

▶️ Step 7: Access Odoo
🌐 http://localhost:8069
Login: admin / admin

Steps:

Activate Developer Mode → Settings → Developer Tools

Go to Apps → Search Product Module → Install

▶️ Step 8: Setup MQTT Explorer
➕ Add new connection:

Name: FPT Broker

Host: localhost

Port: 1883

Protocol: mqtt://

✅ Connect

Expected topics:

localhost/factory/products/all_product_codes

localhost/factory/products/all_product_details

✅ Verification Checklist
Test	Expected Result
docker ps	All containers running
MQTT Explorer	Messages visible on product topics
QR Scan	Correct Arkite workflow triggered
PostgreSQL	Database visible in pgAdmin
Odoo	Product appears in Product Module

🛠️ Troubleshooting
Issue	Cause	Solution
Containers not running	Docker stopped	Start Docker Desktop
No MQTT messages	Port blocked	Open port 1883
Bridge not logging	Service inactive	Restart MQTT bridge
Odoo blank page	DB not initialized	Repeat Step 4 (Odoo init)
pgAdmin cannot connect	Wrong hostname	Use db instead of localhost

👤 Author
Daryl Genove

