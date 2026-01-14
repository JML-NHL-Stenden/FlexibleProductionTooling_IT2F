# product_module/models/arkite_template.py
from odoo import models, fields


class ArkiteTemplate(models.Model):
    _name = 'product_module.arkite.template'
    _description = 'Arkite Project Template'
    _rec_name = 'name'

    name = fields.Char(
        string='Template Name',
        required=True,
        help='Name of the Arkite project template'
    )
    
    arkite_project_id = fields.Integer(
        string='Arkite Project ID',
        required=True,
        help='ID of the project in Arkite system',
        unique=True
    )
    
    description = fields.Text(
        string='Description',
        help='Optional description of the template'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this template will not be available for selection'
    )
