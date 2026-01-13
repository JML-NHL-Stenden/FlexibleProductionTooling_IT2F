# product_module/models/arkite_job_temp.py
from odoo import models, fields, api, _

class ArkiteJobTemp(models.TransientModel):
    """Temporary model for job selection"""
    _name = 'product_module.arkite.job.temp'
    _description = 'Arkite Job (Temporary)'
    _rec_name = 'name'
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', ondelete='cascade')
    job_id = fields.Many2one('product_module.type', string='Job', ondelete='cascade')
    project_id = fields.Many2one('product_module.project', string='Project', ondelete='cascade')
    job_step_id = fields.Char(string='Job Step ID', required=True, help='Arkite Step ID for this job (root step with ProcessId=0)')
    name = fields.Char(string='Name', required=True)
    job_name = fields.Char(string='Job Name', related='name', store=False)
    step_type = fields.Char(string='Step Type', help='Type of the root step (usually COMPOSITE or JOB)')
    comment = fields.Text(string='Comment')
    
    def action_select_job(self):
        """Select this job and automatically load its steps"""
        self.ensure_one()
        if self.project_id:
            # Set both selected job fields to keep them in sync
            self.project_id.write({
                'selected_arkite_job_id': self.job_step_id,
                'selected_job_id_char': self.job_step_id
            })
            
            # Invalidate cache to force recomputation
            self.project_id.invalidate_recordset(['selected_arkite_job_name', 'arkite_job_ids', 'arkite_job_step_ids'])
            
            # Commit the selection immediately
            self.env.cr.commit()
            
            # Automatically load steps for the selected job
            try:
                # Load steps - this will create the step records
                self.project_id.action_load_job_steps()
                # Return empty - JavaScript will handle the refresh
                return {}
            except Exception as e:
                # If loading fails, still return empty to avoid reload
                return {}
        return False

