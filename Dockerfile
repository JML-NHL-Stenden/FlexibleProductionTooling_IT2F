# Dockerfile for Odoo custom module extensions
FROM odoo:18.0

# Install additional Python packages for custom modules
USER root
COPY ./odoo/addons/product_module/requirements.txt /tmp/requirements.txt
# Odoo 18 base image uses an externally-managed Python environment (PEP 668).
# We intentionally install our module deps system-wide inside the container.
RUN pip3 install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

# Copy custom addons into container
COPY ./odoo/addons /mnt/extra-addons/

# Set permissions
RUN chown -R odoo:odoo /mnt/extra-addons

USER odoo
