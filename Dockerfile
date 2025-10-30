# Dockerfile for Odoo custom module extensions
FROM odoo:18.0

# Install additional Python packages for custom modules
USER root
COPY ./odoo/addons/product_module/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt

# Copy custom addons into container
COPY ./odoo/addons /mnt/extra-addons/

# Set permissions
RUN chown -R odoo:odoo /mnt/extra-addons

USER odoo
