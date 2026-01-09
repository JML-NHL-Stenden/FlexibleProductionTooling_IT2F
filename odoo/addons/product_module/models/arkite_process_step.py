# product_module/models/arkite_process_step.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging
import time
import re

_logger = logging.getLogger(__name__)


class ArkiteProcessStep(models.TransientModel):
    """Temporary model for displaying process steps in tree view"""
    _name = 'product_module.arkite.process.step'
    _description = 'Arkite Process Step (Temporary)'
    _order = 'sequence, id'
    _rec_name = 'step_name'  # Use step_name for clean display in parent selection
    # web_hierarchy expects the parent field to be named parent_id by default.
    _parent_name = 'parent_id'
    _parent_store = False

    # -------------------------------------------------------------------------
    # Hierarchy editing helpers (NO custom JS): indent/outdent + reorder siblings
    # -------------------------------------------------------------------------

    def _siblings_domain(self):
        self.ensure_one()
        return [
            ('project_id', '=', self.project_id.id),
            ('process_id', '=', self.process_id),
            ('parent_id', '=', self.parent_id.id if self.parent_id else False),
        ]

    def _sorted_siblings(self):
        self.ensure_one()
        return self.env['product_module.arkite.process.step'].search(self._siblings_domain(), order='sequence, id')

    def _ensure_db_record(self):
        """Resolve NewId wrappers to their persisted record when possible."""
        self.ensure_one()
        if self.id:
            return self
        if getattr(self, '_origin', False) and self._origin.id:
            return self._origin
        return self

    def _resequence_process_tree(self):
        """Assign stable preorder-based global sequences so children stay near their parent in the list."""
        self.ensure_one()
        rec = self._ensure_db_record()
        if not rec.project_id or not rec.process_id:
            return

        Step = rec.env['product_module.arkite.process.step']
        records = Step.search([
            ('project_id', '=', rec.project_id.id),
            ('process_id', '=', rec.process_id),
        ], order='sequence, id')
        if not records:
            return

        by_parent = {}
        for r in records:
            pid = r.parent_id.id if r.parent_id else False
            by_parent.setdefault(pid, []).append(r)
        for pid, kids in by_parent.items():
            kids.sort(key=lambda x: (x.sequence or 0, x.id))

        preorder = []
        stack = list(reversed(by_parent.get(False, [])))
        while stack:
            node = stack.pop()
            preorder.append(node)
            for child in reversed(by_parent.get(node.id, [])):
                stack.append(child)

        for i, r in enumerate(preorder, 1):
            r.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': i * 10})

        records.invalidate_recordset(['hierarchical_level', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_name', 'parent_step_display'])

    def _renumber_siblings(self):
        """Ensure siblings have unique, spaced sequence values so moves are deterministic."""
        self.ensure_one()
        siblings = self._sorted_siblings()
        for i, rec in enumerate(siblings, 1):
            rec.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': i * 10})
        return self._sorted_siblings()

    def action_move_up(self):
        self = self._ensure_db_record()
        self.ensure_one()
        siblings = self._renumber_siblings()
        idx = siblings.ids.index(self.id) if self.id in siblings.ids else -1
        if idx <= 0:
            return False

        prev_rec = siblings[idx - 1]
        a_seq, b_seq = self.sequence, prev_rec.sequence
        self.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': b_seq})
        prev_rec.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': a_seq})

        domain = [('project_id', '=', self.project_id.id), ('process_id', '=', self.process_id)]
        all_records = self.env['product_module.arkite.process.step'].search(domain)
        all_records.invalidate_recordset(['hierarchical_level', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_name', 'parent_step_display'])
        self._resequence_process_tree()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_move_down(self):
        self = self._ensure_db_record()
        self.ensure_one()
        siblings = self._renumber_siblings()
        idx = siblings.ids.index(self.id) if self.id in siblings.ids else -1
        if idx < 0 or idx >= len(siblings) - 1:
            return False

        next_rec = siblings[idx + 1]
        a_seq, b_seq = self.sequence, next_rec.sequence
        self.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': b_seq})
        next_rec.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': a_seq})

        domain = [('project_id', '=', self.project_id.id), ('process_id', '=', self.process_id)]
        all_records = self.env['product_module.arkite.process.step'].search(domain)
        all_records.invalidate_recordset(['hierarchical_level', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_name', 'parent_step_display'])
        self._resequence_process_tree()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_indent(self):
        self = self._ensure_db_record()
        self.ensure_one()
        ordered = self.env['product_module.arkite.process.step'].search([
            ('project_id', '=', self.project_id.id),
            ('process_id', '=', self.process_id),
        ], order='sequence, id')
        try:
            idx = ordered.ids.index(self.id)
        except ValueError:
            return False
        if idx <= 0:
            return False

        new_parent = ordered[idx - 1]
        siblings = self.env['product_module.arkite.process.step'].search([
            ('project_id', '=', self.project_id.id),
            ('process_id', '=', self.process_id),
            ('parent_id', '=', new_parent.id),
        ], order='sequence desc, id desc', limit=1)
        new_seq = (siblings.sequence if siblings else new_parent.sequence) + 10

        self.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({
            'parent_id': new_parent.id,
            'sequence': new_seq,
        })

        domain = [('project_id', '=', self.project_id.id), ('process_id', '=', self.process_id)]
        all_records = self.env['product_module.arkite.process.step'].search(domain)
        all_records.invalidate_recordset(['hierarchical_level', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_name', 'parent_step_display'])
        self._resequence_process_tree()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_outdent(self):
        self = self._ensure_db_record()
        self.ensure_one()
        if not self.parent_id:
            return False

        parent = self.parent_id
        new_parent = parent.parent_id
        new_seq = (parent.sequence or 0) + 5
        self.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({
            'parent_id': new_parent.id if new_parent else False,
            'sequence': new_seq,
        })

        domain = [('project_id', '=', self.project_id.id), ('process_id', '=', self.process_id)]
        all_records = self.env['product_module.arkite.process.step'].search(domain)
        all_records.invalidate_recordset(['hierarchical_level', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_name', 'parent_step_display'])
        self._resequence_process_tree()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', ondelete='cascade')
    job_id = fields.Many2one('product_module.type', string='Job', ondelete='cascade')
    project_id = fields.Many2one('product_module.project', string='Project', ondelete='cascade')
    process_id = fields.Char(string='Process ID', required=True)
    
    # Step data
    step_id = fields.Char(string='Step ID', readonly=True, help='Arkite Step ID (auto-filled when loaded from Arkite)')
    step_name = fields.Char(string='Step Name', required=True)
    step_type = fields.Selection([
        ('WORK_INSTRUCTION', 'Work Instruction'),
        ('TOOL_PLACING', 'Tool Placing'),
        ('TOOL_TAKING', 'Tool Taking'),
        ('OBJECT_PLACING', 'Object Placing'),
        ('OBJECT_TAKING', 'Object Taking'),
        ('PICKING_BIN_PLACING', 'Picking Bin Placing'),
        ('PICKING_BIN_TAKING', 'Picking Bin Taking'),
        ('ACTIVITY', 'Activity'),
        ('CHECK_NO_CHANGE_ZONE', 'Check No Change Zone'),
        ('CHECK_VARIABLE', 'Check Variable'),
        ('VIRTUAL_BUTTON_PRESS', 'Virtual Button Press'),
        ('MATERIAL_GRAB', 'Material Grab'),
        ('COMPOSITE', 'Composite'),
        ('COMPONENT', 'Component'),
        ('JOB', 'Job'),
        ('DIALOG', 'Dialog'),
    ], string='Step Type', required=True, default='WORK_INSTRUCTION', help='Type of step to create')
    step_type_raw = fields.Char(
        string='Step Type (Raw)',
        readonly=True,
        help='Raw StepType value received from Arkite when it did not match Odoo selection values.'
    )
    sequence = fields.Integer(string='Sequence', default=10)
    index = fields.Integer(string='Index', readonly=True)
    
    # Parent-child relationship for tree structure
    parent_step_id = fields.Char(string='Parent Step ID', readonly=True, help='ID of parent step (for nested steps)')
    parent_id = fields.Many2one(
        'product_module.arkite.process.step',
                                         string='Parent Step',
                                         ondelete='cascade',
        help='Parent step record (for tree structure). Only COMPOSITE steps can be parents.',
    )
    # web_hierarchy expects the child field to be named child_ids by default
    child_ids = fields.One2many(
        'product_module.arkite.process.step',
        'parent_id',
        string='Child Steps',
        help='Child steps under this composite step',
    )
    group_parent_id = fields.Many2one(
        'product_module.arkite.process.step',
        string='Group Parent',
        compute='_compute_group_parent_id',
        store=True,
        index=True,
        help='Used for grouped list hierarchy: roots group under themselves instead of "None".',
    )
    child_count = fields.Integer(string='Child Count', compute='_compute_child_count', store=False)
    hierarchy_level = fields.Integer(string='Hierarchy Level', compute='_compute_hierarchy_level', store=False, help='Depth level in hierarchy (0 = root)')
    hierarchy_path = fields.Char(string='Hierarchy Path', compute='_compute_hierarchy_path', store=False, help='Full path showing parent chain (e.g., "Parent > Child")')
    display_name_hierarchy = fields.Char(string='Step', compute='_compute_display_name_hierarchy', store=False, help='Step name with visual hierarchy')
    
    # New fields for improved parent display (similar to job steps)
    parent_step_name = fields.Char(string='Parent Step', compute='_compute_parent_step_name', store=False, help='Name of the parent step')
    parent_step_display = fields.Char(string='Parent', compute='_compute_parent_step_display', store=False, help='Parent step name for display (no tree)')
    hierarchical_level = fields.Char(string='Level', compute='_compute_hierarchical_level', store=False, help='Hierarchical level in format like 2.1, 2.2, etc.')
    hierarchy_css_class = fields.Char(string='CSS Class', compute='_compute_hierarchy_css_class', store=False, help='CSS class for hierarchy coloring')
    hierarchical_level_html = fields.Html(string='Level HTML', compute='_compute_hierarchical_level_html', store=False, help='Hierarchical level with inline styles for coloring')
    
    @api.depends('child_ids')
    def _compute_child_count(self):
        """Count child steps under this step"""
        for record in self:
            record.child_count = len(record.child_ids)

    @api.depends('parent_id')
    def _compute_group_parent_id(self):
        for rec in self:
            rec.group_parent_id = rec.parent_id if rec.parent_id else rec
    
    @api.depends('parent_id', 'parent_id.hierarchy_level')
    def _compute_hierarchy_level(self):
        """Calculate hierarchy level based on parent"""
        for record in self:
            if not record.parent_id:
                record.hierarchy_level = 0
            else:
                # Parent's level + 1, but cap at 5 to prevent deep recursion issues
                parent_level = record.parent_id.hierarchy_level if record.parent_id.hierarchy_level is not False else 0
                record.hierarchy_level = min(parent_level + 1, 5)
    
    @api.depends('parent_id', 'parent_id.step_name', 'parent_id.hierarchy_path')
    def _compute_hierarchy_path(self):
        """Compute full hierarchy path for display"""
        for record in self:
            if not record.parent_id:
                record.hierarchy_path = ""
            else:
                parent_path = record.parent_id.hierarchy_path
                parent_name = record.parent_id.step_name or "Unknown"
                if parent_path:
                    record.hierarchy_path = f"{parent_path} > {parent_name}"
                else:
                    record.hierarchy_path = parent_name
    
    @api.depends('step_name', 'hierarchy_level', 'parent_id')
    def _compute_display_name_hierarchy(self):
        """Create visual hierarchy display with clear indentation using Unicode em-spaces"""
        # Using em-space (U+2003) which won't collapse in HTML
        EM_SPACE = '\u2003'  # Em space - won't collapse like regular spaces
        
        for record in self:
            name = record.step_name or "Unnamed Step"
            level = record.hierarchy_level or 0
            
            if level == 0:
                # Root level - no indentation
                record.display_name_hierarchy = name
            else:
                # Child levels - use em-spaces for visible indentation
                # Each level gets 4 em-spaces + arrow indicator
                indent = (EM_SPACE * 4) * level
                record.display_name_hierarchy = f"{indent}└─ {name}"
    
    @api.depends('parent_id', 'parent_id.step_name')
    def _compute_parent_step_name(self):
        """Get the name of the parent step"""
        # Prevent recursion during computation
        if self.env.context.get('computing_parent_step_name'):
            return
        
        for record in self:
            if record.parent_id:
                # Use context to prevent triggering writes
                try:
                    parent_name = record.parent_id.with_context(computing_parent_step_name=True).step_name
                    record.with_context(computing_parent_step_name=True).parent_step_name = parent_name or "Unnamed Parent"
                except Exception:
                    record.with_context(computing_parent_step_name=True).parent_step_name = "Unnamed Parent"
            else:
                record.with_context(computing_parent_step_name=True).parent_step_name = ""
    
    @api.depends('parent_id', 'parent_id.step_name')
    def _compute_parent_step_display(self):
        """Get parent step name for simple text display (no tree structure)"""
        for record in self:
            if record.parent_id:
                # Get just the step name, no tree characters
                parent_name = record.parent_id.step_name or "Unnamed Parent"
                # Remove any tree characters that might be in the name
                parent_name = parent_name.replace('└─', '').replace('├─', '').strip()
                record.parent_step_display = parent_name
            else:
                record.parent_step_display = ""
    
    @api.depends('parent_id', 'sequence', 'project_id', 'process_id')
    def _compute_hierarchical_level(self):
        """Compute hierarchical level in format like 2.1, 2.2, etc. (similar to job steps)"""
        # Prevent recursion
        if self.env.context.get('computing_hierarchical_level'):
            return

        # NewId-safe compute: must assign hierarchical_level for every record in self
        for rec in self.filtered(lambda r: not r.project_id and not r._origin):
            rec.with_context(computing_hierarchical_level=True).hierarchical_level = "?"

        # NOTE: _origin is not a field (can't be used with mapped); it's an attribute for NewId records.
        project_ids = set()
        process_ids = set()
        for rec in self:
            if rec.project_id:
                project_ids.add(rec.project_id.id)
            elif getattr(rec, '_origin', False) and rec._origin.project_id:
                project_ids.add(rec._origin.project_id.id)

            if rec.process_id:
                process_ids.add(rec.process_id)
            elif getattr(rec, '_origin', False) and getattr(rec._origin, 'process_id', False):
                process_ids.add(rec._origin.process_id)

        project_ids = list(project_ids)
        process_ids = list(process_ids)
        if not project_ids:
            return
        
        # Get ALL records for these projects/processes (not just self) to compute correctly
        domain = [('project_id', 'in', project_ids)]
        if process_ids:
            domain.append(('process_id', 'in', process_ids))
        
        # Use context to prevent recursion
        all_project_records = self.env['product_module.arkite.process.step'].with_context(computing_hierarchical_level=True).search(domain)
        
        # Group by project and process
        by_project_process = {}
        for record in all_project_records:
            if record.project_id and record.process_id:
                key = (record.project_id.id, record.process_id)
                if key not in by_project_process:
                    by_project_process[key] = []
                by_project_process[key].append(record)
        
        computed_levels = {}  # (project_id, process_id, origin_id) -> level

        for (project_id, process_id), records in by_project_process.items():
            record_ids = {r.id for r in records}

            # Overrides from self for this project/process, keyed by origin id
            overrides = {}
            for r in self.filtered(lambda x: (
                ((x.project_id and x.project_id.id == project_id) or (x._origin and x._origin.project_id and x._origin.project_id.id == project_id))
                and str((x.process_id or (x._origin.process_id if x._origin else ''))) == str(process_id)
            )):
                origin_id = r._origin.id if r._origin else r.id
                if not origin_id:
                    continue
                parent_origin_id = r.parent_id._origin.id if r.parent_id and r.parent_id._origin else (r.parent_id.id if r.parent_id else False)
                overrides[origin_id] = {
                    'sequence': r.sequence or 0,
                    'parent_origin_id': parent_origin_id or False,
                }

            children_map = {}
            roots = []
            effective_seq = {}

            for rec in records:
                oid = rec.id
                ov = overrides.get(oid, {})
                seq = ov.get('sequence', rec.sequence or 0)
                pid = ov.get('parent_origin_id', rec.parent_id.id if rec.parent_id else False)
                if pid and pid not in record_ids:
                    pid = False
                effective_seq[oid] = seq
                if not pid:
                    roots.append(oid)
                else:
                    children_map.setdefault(pid, []).append(oid)

            roots.sort(key=lambda oid: (effective_seq.get(oid, 0), oid))
            for i, root_id in enumerate(roots, 1):
                root_level = str(i)
                computed_levels[(project_id, process_id, root_id)] = root_level

                stack = [(root_id, root_level)]
                seen = set()
                while stack:
                    parent_id, parent_level = stack.pop()
                    if parent_id in seen:
                        continue
                    seen.add(parent_id)

                    kids = children_map.get(parent_id, [])
                    kids.sort(key=lambda oid: (effective_seq.get(oid, 0), oid))
                    for pos, child_id in enumerate(kids, 1):
                        child_level = f"{parent_level}.{pos}"
                        computed_levels[(project_id, process_id, child_id)] = child_level
                        stack.append((child_id, child_level))

            for rec in records:
                key = (project_id, process_id, rec.id)
                if key not in computed_levels:
                    computed_levels[key] = "?"

        # Assign to DB records
        for rec in all_project_records:
            key = (rec.project_id.id, rec.process_id, rec.id)
            if key in computed_levels:
                rec.with_context(computing_hierarchical_level=True).hierarchical_level = computed_levels[key]

        # Assign to self (NewId wrappers)
        for rec in self:
            if not rec.project_id and rec._origin and rec._origin.project_id:
                pid = rec._origin.project_id.id
            else:
                pid = rec.project_id.id if rec.project_id else False
            proc = rec.process_id or (rec._origin.process_id if rec._origin else False)
            oid = rec._origin.id if rec._origin else rec.id
            if pid and proc and oid:
                key = (pid, proc, oid)
                if key in computed_levels:
                    rec.with_context(computing_hierarchical_level=True).hierarchical_level = computed_levels[key]
                    continue
            if not rec.hierarchical_level:
                rec.with_context(computing_hierarchical_level=True).hierarchical_level = "?"
    
    @api.depends('hierarchical_level')
    def _compute_hierarchy_css_class(self):
        """Compute CSS class based on hierarchical level for coloring"""
        # Ensure we process all records, even if hierarchical_level is not set yet
        for record in self:
            # If hierarchical_level is not computed yet, try to compute it first
            if not record.hierarchical_level or record.hierarchical_level == "":
                try:
                    record._compute_hierarchical_level()
                except Exception:
                    pass
            
            level = record.hierarchical_level or ""
            if not level or level == "?":
                record.hierarchy_css_class = ""
            else:
                # Count dots to determine level depth
                dot_count = level.count('.')
                if dot_count == 0:
                    record.hierarchy_css_class = "hierarchy-root"
                elif dot_count == 1:
                    record.hierarchy_css_class = "hierarchy-level-1"
                elif dot_count == 2:
                    record.hierarchy_css_class = "hierarchy-level-2"
                elif dot_count == 3:
                    record.hierarchy_css_class = "hierarchy-level-3"
                elif dot_count == 4:
                    record.hierarchy_css_class = "hierarchy-level-4"
                else:
                    record.hierarchy_css_class = "hierarchy-level-5"
    
    @api.depends('hierarchical_level')
    def _compute_hierarchical_level_html(self):
        """Compute HTML for hierarchical level coloring (badge only; no icons/JS)."""
        for record in self:
            level = record.hierarchical_level or ""
            if not level or level == "?":
                record.hierarchical_level_html = f'<span>{level}</span>'
            else:
                full_level = level
                parts = full_level.split('.')
                if len(parts) <= 2:
                    short_level = full_level
                else:
                    short_level = f"{parts[0]}.{parts[1]}…{parts[-1]}"

                # Count dots to determine level depth
                dot_count = full_level.count('.')
                
                # Define colors for each level
                if dot_count == 0:
                    bg_color = "#2196F3"
                    text_color = "white"
                    font_weight = "700"
                elif dot_count == 1:
                    bg_color = "#4caf50"
                    text_color = "white"
                    font_weight = "600"
                elif dot_count == 2:
                    bg_color = "#ffc107"
                    text_color = "#333"
                    font_weight = "600"
                elif dot_count == 3:
                    bg_color = "#ff9800"
                    text_color = "white"
                    font_weight = "600"
                elif dot_count == 4:
                    bg_color = "#e91e63"
                    text_color = "white"
                    font_weight = "600"
                else:
                    bg_color = "#9c27b0"
                    text_color = "white"
                    font_weight = "600"
                record.hierarchical_level_html = (
                    f'<span style="display:inline-block;'
                    f'background-color:{bg_color};color:{text_color};'
                    f'font-weight:{font_weight};'
                    f'border-radius:6px;padding:6px 10px;'
                    f'min-width:60px;text-align:center;'
                    f'box-shadow:0 2px 4px rgba(0,0,0,0.12);'
                    f'" title="{full_level}">{short_level}</span>'
                )
    
    @api.model
    def _compute_parent_from_step_id(self, parent_step_id_str, project_id, process_id):
        """Helper to find parent step record by step_id"""
        if not parent_step_id_str or parent_step_id_str == "0" or parent_step_id_str == "":
            return False
        parent = self.search([
            ('step_id', '=', parent_step_id_str),
            ('project_id', '=', project_id),
            ('process_id', '=', process_id)
        ], limit=1)
        return parent.id if parent else False
    
    # Variants
    variant_ids = fields.Many2many(
        'product_module.arkite.variant.temp',
        'process_step_variant_rel',
        'step_id', 'variant_id',
        string='Variants'
    )
    for_all_variants = fields.Boolean(string='For All Variants', default=False)
    
    @api.model
    def create(self, vals):
        """Override create to create step in Arkite if step_id is empty (new step)"""
        # Allow creating from actions that pass defaults via context without explicit fields
        if not vals.get('project_id') and self.env.context.get('default_project_id'):
            vals['project_id'] = self.env.context.get('default_project_id')
        if not vals.get('process_id') and self.env.context.get('default_process_id'):
            vals['process_id'] = self.env.context.get('default_process_id')

        # If step_id is provided, it's a loaded step - just create the record
        if vals.get('step_id'):
            record = super().create(vals)
            # Skip recomputation when loading from Arkite (step_id already exists)
            # The fields will be computed on next read via @api.depends
            return record
        
        # Otherwise, create a new step in Arkite for the process
        process_id = vals.get('process_id')
        arkite_project_id = None
        
        # Try to get project_id and process_id from different sources
        if vals.get('wizard_id'):
            wizard = self.env['product_module.arkite.job.step.wizard'].browse(vals.get('wizard_id'))
            if wizard and wizard.project_id:
                arkite_project_id = wizard.project_id
                if not process_id and wizard.selected_process_id:
                    process_id = wizard.selected_process_id
                    vals['process_id'] = process_id
        elif vals.get('project_id'):
            project = self.env['product_module.project'].browse(vals.get('project_id'))
            if project and project.arkite_project_id:
                arkite_project_id = project.arkite_project_id
                if not process_id:
                    # selected_process_id_char / selected_arkite_process_id are Char fields (process id string)
                    process_id = project.selected_process_id_char or project.selected_arkite_process_id
                    if process_id:
                        vals['process_id'] = process_id
        
        if not arkite_project_id:
            raise UserError("Please load a project first")
        
        # Get credentials from project if available, otherwise use env vars
        api_base = os.getenv('ARKITE_API_BASE')
        api_key = os.getenv('ARKITE_API_KEY')
        
        if vals.get('project_id'):
            try:
                project = self.env['product_module.project'].browse(vals.get('project_id'))
                if project:
                    creds = project._get_arkite_credentials()
                    api_base = creds['api_base']
                    api_key = creds['api_key']
            except Exception:
                pass
        
        if not api_base or not api_key:
            raise UserError("Arkite API configuration is missing.")
        
        # Process steps must belong to a process. We no longer auto-create processes here because
        # it makes UX confusing and can fail depending on Arkite API version/requirements.
        if not process_id:
            raise UserError(_("Process ID is required. Please select a process first (or create one from the Project form)."))
        
        # First, check existing process steps to understand the structure
        # Process steps might need a ParentStepId pointing to a composite step within the process
        parent_composite_id = None
        try:
            url_check = f"{api_base}/projects/{arkite_project_id}/steps/"
            params_check = {"apiKey": api_key}
            headers_check = {"Content-Type": "application/json"}
            check_response = requests.get(url_check, params=params_check, headers=headers_check, verify=False, timeout=10)
            if check_response.ok:
                all_steps = check_response.json()
                if isinstance(all_steps, list):
                    # Find existing process steps for this process
                    existing_process_steps = [s for s in all_steps if str(s.get("ProcessId", "")) == str(process_id)]
                    if existing_process_steps:
                        # Check if any existing process step has a ParentStepId
                        for step in existing_process_steps:
                            parent_id = step.get("ParentStepId")
                            if parent_id and str(parent_id) != "0":
                                # Found a parent - check if it's a composite step
                                parent_step = next((s for s in all_steps if str(s.get("Id", "")) == str(parent_id)), None)
                                if parent_step and parent_step.get("StepType") == "COMPOSITE":
                                    parent_composite_id = str(parent_id)
                                    _logger.info("[ARKITE] Found existing composite parent for process steps: %s", parent_composite_id)
                                    break
                        # If no parent found, look for a composite step within this process
                        if not parent_composite_id:
                            composite_in_process = next((s for s in existing_process_steps if s.get("StepType") == "COMPOSITE"), None)
                            if composite_in_process:
                                parent_composite_id = str(composite_in_process.get("Id", ""))
                                _logger.info("[ARKITE] Found composite step in process to use as parent: %s", parent_composite_id)
        except Exception as e:
            _logger.warning("[ARKITE] Error checking existing process steps: %s", e)
        
        # Build step payload for process step
        step_data = {
            "Type": "Process",  # Process steps have Type="Process"
            "Name": vals.get('step_name', 'Unnamed Step'),
            "StepType": vals.get('step_type', 'WORK_INSTRUCTION'),
            "ProcessId": str(process_id),  # Process ID (not "0" like job steps)
            "Index": vals.get('sequence', 0) if vals.get('sequence', 0) > 0 else 0,
            "ForAllVariants": vals.get('for_all_variants', False),
            "VariantIds": [],
            "TextInstruction": {},
            "ImageInstructionId": "0",
            "ChildStepOrder": "None" if vals.get('step_type') != "COMPOSITE" else "Sequential",
            "StepControlflow": "None",
            "StepConditions": [],
            "Comment": None
        }
        
        # Only add ParentStepId if we found a valid composite parent
        # If no parent found, omit ParentStepId entirely (let Arkite handle it)
        if parent_composite_id and str(parent_composite_id) != "0":
            step_data["ParentStepId"] = str(parent_composite_id)
            _logger.info("[ARKITE] Setting ParentStepId to composite: %s", parent_composite_id)
        else:
            _logger.info("[ARKITE] No composite parent found, omitting ParentStepId")
            # Explicitly ensure ParentStepId is not in the payload
            if "ParentStepId" in step_data:
                del step_data["ParentStepId"]
        
        _logger.info("[ARKITE] Creating process step - Name: %s, ProcessId: %s, Payload keys: %s", 
                     step_data.get("Name"), step_data.get("ProcessId"), list(step_data.keys()))
        
        # Create step in Arkite (API expects an array)
        url = f"{api_base}/projects/{arkite_project_id}/steps/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}
        
        # Final verification: ensure ParentStepId is never "0"
        if "ParentStepId" in step_data and (step_data["ParentStepId"] == "0" or step_data["ParentStepId"] == 0):
            _logger.error("[ARKITE] ERROR: ParentStepId is '0'! Removing it...")
            del step_data["ParentStepId"]
        
        try:
            payload = [step_data]
            _logger.info("[ARKITE] Sending POST request to: %s", url)
            _logger.info("[ARKITE] Final payload: %s", payload)
            
            response = requests.post(url, params=params, json=payload, headers=headers, verify=False, timeout=10)
            
            _logger.info("[ARKITE] Response status: %s", response.status_code)
            _logger.info("[ARKITE] Response text: %s", response.text[:500] if response.text else "No response text")
            
            # IMPORTANT: Arkite API has a bug - it creates the step successfully but returns 500 error
            step_created = False
            created_step_id = None
            
            if response.ok:
                created_steps = response.json()
                if isinstance(created_steps, list) and created_steps:
                    created_step_id = created_steps[0].get("Id", "Unknown")
                    step_created = True
                elif isinstance(created_steps, dict):
                    created_step_id = created_steps.get("Id", "Unknown")
                    step_created = True
            else:
                # Even if we get an error, check if step was created (API bug)
                _logger.warning("[ARKITE] API returned error, but checking if step was created anyway...")
                time.sleep(1)
                
                # Verify by fetching steps
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    all_steps = verify_response.json()
                    matching_steps = [s for s in all_steps 
                                     if s.get("Name") == step_data["Name"] 
                                     and str(s.get("ProcessId", "")) == str(process_id)]
                    if matching_steps:
                        created_step_id = matching_steps[0].get("Id", "Unknown")
                        step_created = True
                        _logger.info("[ARKITE] Step was created successfully despite API error (ID: %s)", created_step_id)
            
            if step_created:
                vals['step_id'] = str(created_step_id)
                # Get the actual index from the created step
                verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if verify_response.ok:
                    steps = verify_response.json()
                    new_step = next((s for s in steps if str(s.get("Id", "")) == str(created_step_id)), None)
                    if new_step:
                        # Safety check: ensure Arkite actually associated the step with the intended ProcessId.
                        # We've observed Arkite sometimes creating the step but forcing ProcessId="0" (job step),
                        # which makes Odoo look like it created a process step even though Arkite didn't.
                        actual_process_id = str(new_step.get("ProcessId", "") or "")
                        intended_process_id = str(process_id or "")
                        if intended_process_id and actual_process_id and actual_process_id != intended_process_id:
                            _logger.warning(
                                "[ARKITE] Created step %s but Arkite returned ProcessId=%s (expected %s). Rolling back by deleting the step.",
                                created_step_id, actual_process_id, intended_process_id
                            )
                            try:
                                del_url = f"{api_base}/projects/{arkite_project_id}/steps/{created_step_id}"
                                requests.delete(del_url, params=params, headers=headers, verify=False, timeout=10)
                            except Exception as e:
                                _logger.warning("[ARKITE] Could not delete mismatched step %s after creation: %s", created_step_id, e)
                            raise UserError(_(
                                "Arkite created the step, but did not attach it to the selected process.\n\n"
                                "Expected ProcessId: %s\n"
                                "Arkite returned ProcessId: %s\n\n"
                                "This Arkite server does not support creating new processes from Odoo via API. "
                                "Please select an existing process from 'Load Process List' (or create the process in Arkite UI first)."
                            ) % (intended_process_id, actual_process_id))
                        vals['index'] = new_step.get("Index", vals.get('sequence', 0))
            else:
                error_text = response.text[:500] if response.text else "Unknown error"
                raise UserError(f"Failed to create step: HTTP {response.status_code}\n{error_text}")
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error creating process step in Arkite: %s", e)
            raise UserError(f"Error creating step: {str(e)}")
        
        record = super().create(vals)
        # Force recomputation of hierarchical_level and hierarchy_css_class after creation
        if record.project_id:
            domain = [('project_id', '=', record.project_id.id)]
            if record.process_id:
                domain.append(('process_id', '=', record.process_id))
            all_records = self.env['product_module.arkite.process.step'].search(domain)
            # Invalidate first, then recompute
            all_records.invalidate_recordset(['hierarchical_level', 'parent_step_name', 'hierarchy_css_class', 'hierarchical_level_html'])
            all_records.with_context(computing_hierarchical_level=True)._compute_hierarchical_level()
            all_records._compute_parent_step_name()
            all_records._compute_hierarchy_css_class()
            all_records._compute_hierarchical_level_html()
        return record
    
    # NOTE: action_move_up/action_move_down/action_indent/action_outdent are implemented
    # near the top of this file for use in the Project form embedded one2many list.
    # Do NOT reintroduce wizard-specific overrides with the same names, or the buttons
    # will call the wrong method and raise "Step not found in list".
    
    def write(self, vals):
        """Override write to save changes to Arkite API"""
        # Normalize StepType coming from Arkite/UI so it always matches selection keys.
        if 'step_type' in vals and vals.get('step_type'):
            original = vals.get('step_type')
            normalized, raw = self._normalize_step_type_value(original)
            vals['step_type'] = normalized
            if raw:
                vals['step_type_raw'] = raw

        # During hierarchy computation we write display fields; never call Arkite from that path.
        if self.env.context.get('computing_hierarchical_level'):
            return super().write(vals)

        # Always persist changes locally first.
        if self.env.context.get('skip_arkite_sync'):
            return super().write(vals)

        result = super().write(vals)

        # If order/parent changed, normalize sibling sequences so drag order doesn't "snap back"
        # when multiple siblings share the same sequence.
        if 'sequence' in vals or 'parent_id' in vals:
            groups = set()
            for rec in self:
                groups.add((rec.project_id.id, rec.process_id or '', rec.parent_id.id if rec.parent_id else None))
            for project_id, process_id, parent_rec_id in groups:
                domain = [('project_id', '=', project_id)]
                if process_id:
                    domain.append(('process_id', '=', process_id))
                domain.append(('parent_id', '=', parent_rec_id or False))
                siblings = self.env['product_module.arkite.process.step'].search(domain, order='sequence,id')
                # Write sequences directly to avoid recursion/side effects.
                seq = 10
                for s in siblings:
                    self.env.cr.execute(
                        "UPDATE product_module_arkite_process_step SET sequence=%s WHERE id=%s",
                        [seq, s.id],
                    )
                    seq += 10
            self.invalidate_recordset(['sequence'])

        # If the user is editing in "deferred sync" mode (hierarchy/diagram screens), mark project dirty
        # and stop here (do NOT call Arkite yet).
        if self.env.context.get('defer_arkite_sync'):
            if 'sequence' in vals or 'parent_id' in vals:
                project_ids = list(set(self.mapped('project_id').ids))
                if project_ids:
                    self.env.cr.execute(
                        "UPDATE product_module_project SET arkite_process_steps_dirty = TRUE, arkite_hierarchy_dirty = TRUE WHERE id = ANY(%s)",
                        [project_ids],
                    )
                    self.env['product_module.project'].browse(project_ids).invalidate_recordset(['arkite_hierarchy_dirty'])
            return result

        # Recompute hierarchy fields after write (this is what keeps the UI from showing '?' after reorder)
        if 'sequence' in vals or 'parent_id' in vals:
            project_ids = list(set(self.mapped('project_id').ids))
            process_ids = list(set(self.mapped('process_id')))
            if project_ids:
                domain = [('project_id', 'in', project_ids)]
                if process_ids:
                    domain.append(('process_id', 'in', process_ids))
                all_records = self.env['product_module.arkite.process.step'].search(domain)
                all_records.invalidate_recordset(['hierarchical_level', 'parent_step_name', 'hierarchy_css_class', 'hierarchical_level_html'])
                try:
                    all_records.with_context(computing_hierarchical_level=True)._compute_hierarchical_level()
                    all_records._compute_parent_step_name()
                    all_records._compute_hierarchy_css_class()
                    all_records._compute_hierarchical_level_html()
                except Exception as e:
                    _logger.warning("[HIERARCHY] Could not recompute levels during write: %s", e)
        
        for record in self:
            # Get project ID from either wizard, project, or job's project
            project_id = None
            if record.wizard_id and record.wizard_id.project_id:
                project_id = record.wizard_id.project_id
            elif record.project_id and record.project_id.arkite_project_id:
                project_id = record.project_id.arkite_project_id
            elif record.job_id:
                # Try to get from job's project
                project = self.env['product_module.project'].search([
                    ('job_ids', 'in', [record.job_id.id])
                ], limit=1)
                if project and project.arkite_project_id:
                    project_id = project.arkite_project_id
            
            if not project_id:
                continue
            
            # Skip if step_id is not set (new step being created)
            if not record.step_id:
                continue
            
            # Get credentials from project if available
            api_base = os.getenv('ARKITE_API_BASE')
            api_key = os.getenv('ARKITE_API_KEY')
            
            if record.project_id:
                try:
                    creds = record.project_id._get_arkite_credentials()
                    api_base = creds['api_base']
                    api_key = creds['api_key']
                except Exception:
                    pass
            
            if not api_base or not api_key:
                continue
            
            try:
                url = f"{api_base}/projects/{project_id}/steps/{record.step_id}"
                params = {"apiKey": api_key}
                headers = {"Content-Type": "application/json"}
                
                # Get current step
                response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                if not response.ok:
                    continue
                
                step_data = response.json()
                updated = False
                
                # Update step name if changed
                if 'step_name' in vals and step_data.get("Name") != record.step_name:
                    step_data["Name"] = record.step_name
                    updated = True
                
                # Update step type if changed
                if 'step_type' in vals and step_data.get("StepType") != record.step_type:
                    step_data["StepType"] = record.step_type
                    # Update ChildStepOrder for composite steps
                    if record.step_type == "COMPOSITE":
                        step_data["ChildStepOrder"] = "Sequential"
                    else:
                        step_data["ChildStepOrder"] = "None"
                    updated = True
                
                # Update sequence/index if changed
                if 'sequence' in vals:
                    # Convert sequence to Index (sequence is typically multiples of 10, Index is the actual order)
                    new_index = record.sequence // 10 if record.sequence > 0 else 0
                    old_index = step_data.get("Index", 0)
                    _logger.info("[ARKITE] Process step %s sequence changed: %s -> Index %s (was %s)", record.step_id, record.sequence, new_index, old_index)
                    if old_index != new_index:
                        step_data["Index"] = new_index
                        updated = True
                    else:
                        _logger.debug("[ARKITE] Process step %s Index already %s, skipping update", record.step_id, new_index)
                
                # Update variants if changed
                if 'variant_ids' in vals or 'for_all_variants' in vals:
                    if record.for_all_variants:
                        step_data["ForAllVariants"] = True
                        step_data["VariantIds"] = []
                    else:
                        step_data["ForAllVariants"] = False
                        step_data["VariantIds"] = [v.variant_id for v in record.variant_ids]
                    updated = True
                
                # Update parent step if changed
                if 'parent_id' in vals:
                    # Validate that parent is a COMPOSITE step
                    if record.parent_id:
                        if record.parent_id.step_type != 'COMPOSITE':
                            raise UserError(_("Only COMPOSITE steps can be parent steps. Please select a COMPOSITE step as the parent."))
                        
                        # Prevent circular reference (step cannot be its own parent or ancestor)
                        if record.parent_id.id == record.id:
                            raise UserError(_("A step cannot be its own parent."))
                        
                        # Check for circular references (parent cannot be a descendant of this step)
                        ancestor = record.parent_id
                        while ancestor.parent_id:
                            if ancestor.parent_id.id == record.id:
                                raise UserError(_("Circular reference detected. A step cannot be an ancestor of its parent."))
                            ancestor = ancestor.parent_id
                        
                        # Update parent_step_id to match the parent record's step_id
                        parent_step_id = record.parent_id.step_id
                        if parent_step_id and str(parent_step_id) != "0":
                            step_data["ParentStepId"] = str(parent_step_id)
                            record.parent_step_id = str(parent_step_id)
                            _logger.info("[ARKITE] Updating ParentStepId to: %s", parent_step_id)
                        else:
                            # Remove ParentStepId if parent doesn't have a valid step_id
                            if "ParentStepId" in step_data:
                                del step_data["ParentStepId"]
                            record.parent_step_id = ""
                            _logger.info("[ARKITE] Removing ParentStepId (parent has no step_id)")
                    else:
                        # No parent - remove ParentStepId
                        if "ParentStepId" in step_data:
                            del step_data["ParentStepId"]
                        record.parent_step_id = ""
                        _logger.info("[ARKITE] Removing ParentStepId (no parent selected)")
                    updated = True
                
                # Update step if anything changed
                if updated:
                    _logger.info("[ARKITE] Patching process step %s with data: %s", record.step_id, {k: v for k, v in step_data.items() if k in ['Name', 'StepType', 'Index', 'ParentStepId']})
                    patch_response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
                    if patch_response.ok:
                        _logger.info("[ARKITE] Successfully updated process step %s in Arkite", record.step_id)
                        # Verify update
                        time.sleep(0.3)
                        verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                        if verify_response.ok:
                            updated_data = verify_response.json()
                            if 'sequence' in vals:
                                # Get Index from Arkite and update our index field
                                arkite_index = updated_data.get("Index", 0)
                                record.index = arkite_index
                                # Also update sequence to match (multiply by 10 for consistency)
                                record.sequence = arkite_index * 10
            except Exception as e:
                _logger.error("Error updating step in Arkite: %s", e)
        
        return result

    @api.model
    def create(self, vals):
        # Normalize StepType coming from Arkite/UI so it always matches selection keys.
        if vals.get('step_type'):
            original = vals.get('step_type')
            normalized, raw = self._normalize_step_type_value(original)
            vals['step_type'] = normalized
            if raw:
                vals['step_type_raw'] = raw
        return super().create(vals)

    @api.model
    def _normalize_step_type_value(self, value):
        """Return (normalized, raw_if_unknown)."""
        if not value:
            return 'WORK_INSTRUCTION', False

        raw = str(value).strip()
        if not raw:
            return 'WORK_INSTRUCTION', False

        s = raw
        s = re.sub(r"\s+", "_", s)
        s = s.replace("-", "_")
        s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
        s = s.upper()
        if s.endswith("_STEP"):
            s = s[:-5]
        if s.endswith("STEP"):
            s = s[:-4]
        s = re.sub(r"_+", "_", s).strip("_")

        allowed = {k for k, _label in (self._fields['step_type'].selection or [])}
        if s in allowed:
            return s, False

        aliases = {
            'WORKINSTRUCTION': 'WORK_INSTRUCTION',
            'TOOLPLACING': 'TOOL_PLACING',
            'TOOLTAKING': 'TOOL_TAKING',
            'OBJECTPLACING': 'OBJECT_PLACING',
            'OBJECTTAKING': 'OBJECT_TAKING',
            'PICKINGBINPLACING': 'PICKING_BIN_PLACING',
            'PICKINGBINTAKING': 'PICKING_BIN_TAKING',
            'CHECKNOCHANGEZONE': 'CHECK_NO_CHANGE_ZONE',
            'CHECKVARIABLE': 'CHECK_VARIABLE',
            'VIRTUALBUTTONPRESS': 'VIRTUAL_BUTTON_PRESS',
            'MATERIALGRAB': 'MATERIAL_GRAB',
        }
        if s in aliases and aliases[s] in allowed:
            return aliases[s], False

        _logger.warning("[ARKITE] Unknown StepType '%s' (normalized '%s') for process step; falling back to WORK_INSTRUCTION", raw, s)
        return 'WORK_INSTRUCTION', raw

    def action_discard_changes(self):
        """Discard local hierarchy changes by reloading from Arkite for the current process."""
        self.ensure_one()
        if not self.project_id:
            return False
        # Ensure selected process is set so reload pulls the correct steps
        if self.process_id:
            self.project_id.write({'selected_process_id_char': self.process_id, 'selected_arkite_process_id': self.process_id})
        self.project_id.action_load_process_steps()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_sync_to_arkite(self):
        """Apply current local order/parent changes to Arkite."""
        self.ensure_one()
        if not self.project_id:
            return False

        domain = [('project_id', '=', self.project_id.id)]
        if self.process_id:
            domain.append(('process_id', '=', self.process_id))
        elif self.env.context.get('default_process_id'):
            domain.append(('process_id', '=', self.env.context.get('default_process_id')))

        records = self.env['product_module.arkite.process.step'].search(domain)
        # Sync by re-writing each record with defer disabled; write() already patches Arkite fields.
        for rec in records.sorted(lambda r: (r.sequence or 0, r.id)):
            rec.with_context(defer_arkite_sync=False).write({
                'sequence': rec.sequence,
                'parent_id': rec.parent_id.id if rec.parent_id else False,
            })
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': _('Saved'), 'message': _('Saved hierarchy changes to Arkite.'), 'type': 'success', 'sticky': False}}

    @api.model
    def pm_action_save_all(self):
        """Save ALL staged process-step changes to Arkite for the project/process in context.

        Called from hierarchy control panel buttons (no record selection).
        """
        project_id = self.env.context.get('default_project_id')
        if not project_id:
            return False
        domain = [('project_id', '=', project_id)]
        process_id = self.env.context.get('default_process_id')
        if process_id:
            domain.append(('process_id', '=', process_id))
        records = self.env['product_module.arkite.process.step'].search(domain)
        for rec in records.sorted(lambda r: (r.sequence or 0, r.id)):
            rec.with_context(defer_arkite_sync=False).write({
                'sequence': rec.sequence,
                'parent_id': rec.parent_id.id if rec.parent_id else False,
            })
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': _('Saved'), 'message': _('Saved to Arkite.'), 'type': 'success', 'sticky': False}}

    @api.model
    def pm_action_discard_all(self):
        """Discard staged process-step changes by reloading from Arkite for the project/process in context."""
        project_id = self.env.context.get('default_project_id')
        if not project_id:
            return False
        project = self.env['product_module.project'].browse(project_id)
        if not project.exists():
            return False
        # Ensure selected process matches context so reload pulls the correct steps
        process_id = self.env.context.get('default_process_id')
        if process_id:
            project.write({'selected_process_id_char': process_id, 'selected_arkite_process_id': process_id})
        project.action_load_process_steps()
        return {'type': 'ir.actions.client', 'tag': 'reload'}
    
    def unlink(self):
        """Unlink local transient records.

        IMPORTANT: This model is a TransientModel, so Odoo's auto-vacuum will unlink rows periodically.
        We must NOT delete anything in Arkite from unlink(), otherwise background cleanup can delete real
        Arkite steps unexpectedly.
        """
        return super().unlink()


class ArkiteVariantTemp(models.TransientModel):
    """Temporary model for variants"""
    _name = 'product_module.arkite.variant.temp'
    _description = 'Arkite Variant (Temporary)'
    _rec_name = 'name'
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', ondelete='cascade')
    job_id = fields.Many2one('product_module.type', string='Job', ondelete='cascade')
    project_id = fields.Many2one('product_module.project', string='Project', ondelete='cascade')
    variant_id = fields.Char(string='Variant ID', default='0')
    name = fields.Char(string='Name', required=True)
    description = fields.Text(string='Description')
