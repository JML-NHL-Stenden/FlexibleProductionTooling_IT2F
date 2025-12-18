# product_module/models/project.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProductModuleProject(models.Model):
    _name = 'product_module.project'
    _description = 'Product Project'
    _order = 'name, id'

    page_id = fields.Many2one('product_module.page', string='Page', ondelete='cascade')
    name = fields.Char(string='Project Name', required=True, size=50)
    description = fields.Text(string='Description', size=250)
    
    # Related jobs (Many2many relationship)
    job_ids = fields.Many2many('product_module.type', string='Jobs')
    job_count = fields.Integer(string='Total Jobs', compute='_compute_job_count')

    @api.depends('job_ids')
    def _compute_job_count(self):
        """Count number of jobs for this project"""
        for record in self:
            record.job_count = len(record.job_ids)

    # Input constrains
    @api.constrains('name')
    def _check_name_length(self):
        for record in self:
            if record.name and len(record.name) > 50:
                raise UserError(_('Project Name cannot exceed 50 characters.'))
    
    @api.constrains('description')
    def _check_description_length(self):
        for record in self:
            if record.description and len(record.description) > 250:
                raise UserError(_('Description cannot exceed 250 characters.'))

