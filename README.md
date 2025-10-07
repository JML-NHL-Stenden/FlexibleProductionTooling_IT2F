# FlexibleProductionTooling_IT2F

## Overview

This project provides a flexible production tooling system using Odoo, PostgreSQL, MQTT, and Docker. The system includes a custom Odoo module for product registration with QR code generation and assembly instruction management.

## Components

### 1. Odoo ERP System

- **Container**: `flexible-production-tooling-odoo-1`
- **Port**: 8069 (configurable via `.env`)
- **Custom Module**: Product Module with QR code generation

### 2. PostgreSQL Database

- **Container**: `flexible-production-tooling-db-1`
- **Database**: odoo
- **Persistent Storage**: `odoo-db-data` volume

### 3. pgAdmin (Database Management)

- **Container**: `flexible-production-tooling-pgadmin-1`
- **Port**: 5050 (configurable via `.env`)

### 4. MQTT Broker (Eclipse Mosquitto)

- **Container**: `flexible-production-tooling-mqtt-1`
- **Port**: 1883 (configurable via `.env`)

### 5. MQTT Bridge

- **Container**: `flexible-production-tooling-mqtt-bridge`
- Connects MQTT messages to the database

### 6. MQTT Publisher

- **Container**: `flexible-production-tooling-mqtt-publish`
- Publishes test messages to MQTT broker

## Product Module Features

The custom Odoo module provides:

- **Product Registration**: Register products with name, ID, variant, and optional photo
- **QR Code Generation**: Automatic QR code generation based on product ID
- **Assembly Instructions**: Add step-by-step assembly instructions with images
- **Product List View**: View all products with QR codes and instruction counts
- **Drag & Drop Ordering**: Reorder products and instructions easily

For detailed module documentation, see [odoo/addons/product_module/README.md](odoo/addons/product_module/README.md)

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- Create a `.env` file with the following variables:

```env
# PostgreSQL
POSTGRES_VERSION=16
POSTGRES_DB=odoo
POSTGRES_USER=odoo
POSTGRES_PASSWORD=odoo

# Odoo
ODOO_VERSION=18.0
ODOO_HTTP_PORT=8069

# Database connection
DB_HOST=db
DB_PORT=5432
DB_NAME=odoo
DB_USER=odoo
DB_PASS=odoo

# pgAdmin
PGADMIN_DEFAULT_EMAIL=admin@example.com
PGADMIN_DEFAULT_PASSWORD=admin
PGADMIN_PORT=5050

# MQTT
MQTT_HOST=mqtt
MQTT_PORT=1883
MOSQUITTO_PORT=1883
```

### Installation

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd FlexibleProductionTooling_IT2F
   ```

2. **Create the `.env` file** with the configuration above

3. **Build and start the containers**:

   ```bash
   docker-compose up -d --build
   ```

4. **Access Odoo**:

   - URL: http://localhost:8069
   - Create a database when prompted
   - Install the "Product Module" from Apps

5. **Access pgAdmin** (optional):
   - URL: http://localhost:5050
   - Login with credentials from `.env`

## Module Installation in Odoo

1. Go to **Apps** menu
2. Click **Update Apps List**
3. Search for "Product Module"
4. Click **Install**
5. Access via **Product Module > Product Assemble**

## Usage

### Register a Product

1. Navigate to **Product Module > Product Assemble**
2. Go to **Register Product** tab
3. Add product details (name, ID, variant)
4. QR code is automatically generated

### Add Assembly Instructions

1. Go to **Products List** tab
2. Click on a product
3. Open **Assembly Instructions** tab
4. Add step-by-step instructions with optional images
5. Drag to reorder steps

## Development

### Project Structure

```
FlexibleProductionTooling_IT2F/
├── docker-compose.yml          # Docker orchestration
├── Dockerfile                  # Odoo container with custom modules
├── .env                        # Environment variables (not in repo)
├── odoo/
│   ├── odoo.conf              # Odoo configuration
│   └── addons/
│       └── product_module/    # Custom product module
├── mqtt_bridge/               # MQTT to DB bridge
├── mqtt_publish/              # MQTT publisher
└── uns/                       # MQTT broker config
```

### Rebuilding After Changes

```bash
# Rebuild and restart Odoo container
docker-compose up -d --build odoo

# Restart Odoo with module update
docker-compose restart odoo
```

### Viewing Logs

```bash
# All containers
docker-compose logs -f

# Specific container
docker-compose logs -f odoo
docker-compose logs -f mqtt-bridge
```

## License

LGPL-3

## Authors

II- F Information Technology (NHL Stenden)
