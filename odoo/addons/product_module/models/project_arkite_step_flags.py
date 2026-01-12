from odoo import models, fields


class ProductModuleProjectArkiteStepFlags(models.Model):
    _inherit = 'product_module.project'

    arkite_job_steps_loaded = fields.Boolean(
        string='Job Steps Loaded',
        default=False,
        copy=False,
        help='Set when Job Steps have been loaded from Arkite into Odoo for this project.'
    )
    arkite_process_steps_loaded = fields.Boolean(
        string='Process Steps Loaded',
        default=False,
        copy=False,
        help='Set when Process Steps have been loaded from Arkite into Odoo for this project.'
    )
    arkite_job_steps_dirty = fields.Boolean(
        string='Job Steps Staged',
        default=False,
        copy=False,
        help='Local job step hierarchy/order has changed and will be synced to Arkite when the project is saved.'
    )
    arkite_process_steps_dirty = fields.Boolean(
        string='Process Steps Staged',
        default=False,
        copy=False,
        help='Local process step hierarchy/order has changed and will be synced to Arkite when the project is saved.'
    )

    def action_load_job_steps(self):
        self.ensure_one()
        res = super().action_load_job_steps()
        # Loading is a reset to Arkite state → mark loaded, clear staged changes.
        self.with_context(skip_arkite_hierarchy_autosync=True).write({
            'arkite_job_steps_loaded': True,
            'arkite_job_steps_dirty': False,
            # Keep legacy flag consistent (some code still checks it)
            'arkite_hierarchy_dirty': bool(self.arkite_process_steps_dirty),
        })
        return res

    def action_load_process_steps(self):
        self.ensure_one()
        res = super().action_load_process_steps()
        self.with_context(skip_arkite_hierarchy_autosync=True).write({
            'arkite_process_steps_loaded': True,
            'arkite_process_steps_dirty': False,
            'arkite_hierarchy_dirty': bool(self.arkite_job_steps_dirty),
        })
        return res

