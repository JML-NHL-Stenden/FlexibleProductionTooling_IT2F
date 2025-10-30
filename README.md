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

## 👤 Author

**Daryl Genove**