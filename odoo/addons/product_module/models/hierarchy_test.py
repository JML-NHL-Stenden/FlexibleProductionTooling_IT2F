# product_module/models/hierarchy_test.py
from odoo import models, fields, api

class HierarchyTestItem(models.TransientModel):
    """Test model for hierarchy drag-and-drop functionality"""
    _name = 'product_module.hierarchy.test'
    _description = 'Hierarchy Test Item'
    _order = 'sequence, id'
    _parent_name = 'parent_id'
    _parent_store = False
    
    project_id = fields.Many2one('product_module.project', string='Project', required=True, ondelete='cascade')
    name = fields.Char(string='Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    parent_id = fields.Many2one('product_module.hierarchy.test', string='Parent', ondelete='cascade', domain="[('project_id', '=', project_id)]")
    child_ids = fields.One2many('product_module.hierarchy.test', 'parent_id', string='Children')
    level = fields.Integer(string='Level', compute='_compute_level', store=False)
    
    @api.depends('parent_id', 'parent_id.level')
    def _compute_level(self):
        for record in self:
            if record.parent_id:
                record.level = record.parent_id.level + 1
            else:
                record.level = 0
    
