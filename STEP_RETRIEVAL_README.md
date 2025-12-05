### 1. Check IP for Arktie API
Make sure that the main body of the API calls to Arkite contain your IPv4 instead of "localhost" as in the template example in the API Tester.

### 2. Run Docker
Run `docker-compose down` and `docker-compose up --build`

### 3. Connect to MQTT
In MQTT Broker connect to Host `localhost` and Port `1883`.

### 4. Check the Postgres tables
In Postgres there should be tabel in "odoo" database, called "public.arkite_steps", where the steps should be put.

