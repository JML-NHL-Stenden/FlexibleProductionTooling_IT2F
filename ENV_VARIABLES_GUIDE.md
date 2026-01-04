# Environment Variables Guide

This document explains all environment variables used in the Flexible Production Tooling project.

## File Locations

- **Root `.env`**: Main environment file for all services (Docker Compose + Windows Agent)
- **`.env.example`**: Template file (safe to commit, contains example values)

**Note**: The Windows Arkite Agent reads from the root `.env` file (parent directory), so no separate `automation/.env` file is needed.

## Environment Variables by Service

### 1. Docker & PostgreSQL Database

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `POSTGRES_VERSION` | PostgreSQL Docker image version | `15` | docker-compose.yml |
| `POSTGRES_DB` | Database name | `odoo` | docker-compose.yml |
| `POSTGRES_USER` | Database username | `odoo` | docker-compose.yml |
| `POSTGRES_PASSWORD` | Database password | `odoo` | docker-compose.yml |

### 2. Odoo Configuration

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `ODOO_VERSION` | Odoo Docker image version | `16` | docker-compose.yml |
| `ODOO_HTTP_PORT` | Port for Odoo web interface | `8069` | docker-compose.yml |
| `DB_HOST` | Database hostname | `db` | docker-compose.yml, odoo.conf |
| `DB_USER` | Database user for Odoo | `odoo` | docker-compose.yml, odoo.conf |
| `DB_PASS` | Database password for Odoo | `odoo` | docker-compose.yml, odoo.conf |
| `DB_PORT` | Database port | `5432` | mqtt_publish |
| `DB_NAME` | Database name | `odoo` | mqtt_publish |

### 3. pgAdmin Configuration

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `PGADMIN_DEFAULT_EMAIL` | pgAdmin login email | `admin@example.com` | docker-compose.yml |
| `PGADMIN_DEFAULT_PASSWORD` | pgAdmin login password | `admin` | docker-compose.yml |
| `PGADMIN_PORT` | Port for pgAdmin web interface | `5050` | docker-compose.yml |

### 4. MQTT Broker (Mosquitto)

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `MOSQUITTO_PORT` | MQTT broker port | `1883` | docker-compose.yml |
| `MQTT_HOST` | MQTT broker hostname | `mqtt` (Docker) or `localhost` (Windows) | All MQTT services |
| `MQTT_PORT` | MQTT broker port | `1883` | All MQTT services |

### 5. MQTT Topics

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `MQTT_TOPIC_QR` | Topic for QR code triggers | `arkite/trigger/QR` | mqtt_bridge, mqtt_publish, arkite_agent |
| `MQTT_TOPIC_CODES` | Topic for product codes list | `factory/products/all_product_codes` | mqtt_publish |
| `MQTT_TOPIC_DETAILS` | Topic for product details (grouped by category) | `factory/products/all_product_details` | mqtt_publish |

### 6. Arkite API Configuration

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `ARKITE_API_BASE` | Base URL of Arkite Server API | `https://192.168.178.99/api/v1` | mqtt_bridge |
| `ARKITE_API_KEY` | API key for Arkite Server | `Xpz2f7dRi` | mqtt_bridge |
| `ARKITE_UNIT_ID` | Unit/Workstation ID | `97640866481035` | mqtt_bridge |
| `ARKITE_TEMPLATE_NAME` | Template project name to duplicate | `FPT-Template` | mqtt_bridge |

### 7. Arkite Agent (Windows Service)

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `ARKITE_USER` | Arkite Workstation login username | `Admin` | arkite_agent.py |
| `ARKITE_PASS` | Arkite Workstation login password | `Arkite3600` | arkite_agent.py |

**Note**: These are read from the root `.env` file (parent directory) or Windows environment variables.

### 8. MQTT Publish Service

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `ODOO_BASE_URL` | Base URL for Odoo image links | `http://odoo:8069` | mqtt_publish |
| `CHECK_INTERVAL` | How often to check for changes (seconds) | `5` | mqtt_publish |
| `PRETTY_JSON` | Pretty print JSON output | `false` | mqtt_publish |

### 9. Logging & Performance

| Variable | Description | Default | Used By |
|----------|-------------|---------|---------|
| `LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | `INFO` | All services |
| `IDLE_INTERVAL_SEC` | Idle interval for loops (seconds) | `1` | mqtt_bridge, arkite_agent |

## Service-Specific Configuration

### Docker Compose Services

All services in `docker-compose.yml` read from the root `.env` file:
- `db` (PostgreSQL)
- `odoo` (Odoo ERP)
- `pgadmin` (pgAdmin)
- `mqtt` (Mosquitto MQTT broker)
- `mqtt-bridge` (MQTT to Arkite bridge)
- `mqtt-publish` (Product data publisher)

### Windows Services

The `arkite_agent.py` service reads from:
1. Windows environment variables (highest priority)
2. Root `.env` file (parent directory: `../.env`)
3. Default values in code (lowest priority)

## Setup Instructions

1. **Copy the template**:
   ```bash
   cp .env.example .env
   ```

2. **Update values**:
   - Change `ARKITE_API_BASE` to your Arkite Server IP/URL
   - Update `ARKITE_API_KEY` with your actual API key
   - Set `ARKITE_UNIT_ID` to your workstation ID
   - Update `ARKITE_TEMPLATE_NAME` if different
   - Change database passwords for production

3. **Windows Agent**:
   - The Windows Agent automatically reads from the root `.env` file
   - No separate configuration file needed
   - If running on Windows, ensure `MQTT_HOST=localhost` (or your MQTT broker IP) in root `.env`

## Security Notes

⚠️ **Important**:
- Never commit `.env` files to version control (they're in `.gitignore`)
- Use strong passwords in production
- Keep API keys secure
- The `.env.example` file is safe to commit (contains example values only)

## Troubleshooting

### MQTT Connection Issues
- If services can't connect to MQTT, check `MQTT_HOST`:
  - Docker services: Use `mqtt` (service name)
  - Windows agent: Use `localhost` or actual IP

### Arkite API Issues
- Verify `ARKITE_API_BASE` is accessible from the Docker network
- Check `ARKITE_API_KEY` is correct
- Ensure `ARKITE_UNIT_ID` matches your workstation

### Database Connection Issues
- Verify `DB_HOST`, `DB_USER`, `DB_PASS` match PostgreSQL settings
- Check network connectivity between services

## Environment Variable Priority

For `arkite_agent.py` (Windows):
1. Windows environment variables (highest priority)
2. Root `.env` file (`../.env` - parent directory)
3. Default values in code (lowest priority)

For Docker services:
1. `.env` file (read by docker-compose)
2. Default values in code (if not in .env)
