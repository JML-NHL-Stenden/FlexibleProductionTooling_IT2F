# product_module/models/hierarchy_widget.py
from odoo import models, fields, api
import json

class HierarchyWidget(models.AbstractModel):
    """Custom widget for displaying interactive hierarchy"""
    _name = 'product_module.hierarchy.widget'
    _description = 'Hierarchy Widget'
