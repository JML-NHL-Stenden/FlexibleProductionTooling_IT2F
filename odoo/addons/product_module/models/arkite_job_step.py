# product_module/models/arkite_job_step.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging
import time
import json
import re

_logger = logging.getLogger(__name__)


class ArkiteJobStep(models.TransientModel):
    """Temporary model for displaying job steps in tree view"""
    _name = 'product_module.arkite.job.step'
    _description = 'Arkite Job Step (Temporary)'
    _order = 'sequence, id'
    _rec_name = 'step_name'  # Use step_name for clean display in parent selection
    # web_hierarchy expects the parent field to be named parent_id by default.
    _parent_name = 'parent_id'
    _parent_store = False
    
    wizard_id = fields.Many2one('product_module.arkite.job.step.wizard', string='Wizard', ondelete='cascade')
    job_id = fields.Many2one('product_module.type', string='Job', ondelete='cascade')
    project_id = fields.Many2one('product_module.project', string='Project', ondelete='cascade')
    job_step_id = fields.Char(string='Job Step ID', required=True, help='Root step ID for this job')
    
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
        'product_module.arkite.job.step',
                                         string='Parent Step',
                                         ondelete='cascade',
        help='Parent step record (for nested steps)',
    )
    child_ids = fields.One2many(
        'product_module.arkite.job.step',
        'parent_id',
        string='Child Steps',
    )
    group_parent_id = fields.Many2one(
        'product_module.arkite.job.step',
        string='Group Parent',
        compute='_compute_group_parent_id',
        store=True,
        index=True,
        help='Used for grouped list hierarchy: roots group under themselves instead of "None".',
    )
    
    # Variants
    variant_ids = fields.Many2many(
        'product_module.arkite.variant.temp',
        'arkite_job_step_variant_rel',
        'job_step_id',
        'variant_id',
        string='Variants',
        help='Variants assigned to this step'
    )
    for_all_variants = fields.Boolean(string='For All Variants', default=False, help='Apply this step to all variants')
    
    # Hierarchy fields
    hierarchy_level = fields.Integer(string='Hierarchy Level', compute='_compute_hierarchy_level', store=False, help='Depth level in hierarchy (0 = root)')
    hierarchy_path = fields.Char(string='Path', compute='_compute_hierarchy_path', store=False, help='Full hierarchy path of the step')
    display_name_hierarchy = fields.Char(string='Step', compute='_compute_display_name_hierarchy', store=False, help='Step name with visual hierarchy')
    
    # New fields for improved parent display
    parent_step_name = fields.Char(string='Parent Step', compute='_compute_parent_step_name', store=False, help='Name of the parent step')
    parent_step_display = fields.Char(string='Parent', compute='_compute_parent_step_display', store=False, help='Parent step name for display (no tree)')
    hierarchical_level = fields.Char(string='Level', compute='_compute_hierarchical_level', store=False, help='Hierarchical level in format like 2.1, 2.2, etc.')
    hierarchy_css_class = fields.Char(string='CSS Class', compute='_compute_hierarchy_css_class', store=False, help='CSS class for hierarchy coloring')
    hierarchical_level_html = fields.Html(string='Level HTML', compute='_compute_hierarchical_level_html', store=False, help='Hierarchical level with inline styles for coloring')
    child_count = fields.Integer(string='Children', compute='_compute_child_count', store=False)

    @api.depends('child_ids')
    def _compute_child_count(self):
        for rec in self:
            rec.child_count = len(rec.child_ids)

    @api.depends('parent_id')
    def _compute_group_parent_id(self):
        for rec in self:
            rec.group_parent_id = rec.parent_id if rec.parent_id else rec

    # -------------------------------------------------------------------------
    # Hierarchy editing helpers (NO custom JS): indent/outdent + reorder siblings
    # -------------------------------------------------------------------------

    def _siblings_domain(self):
        self.ensure_one()
        return [
            ('project_id', '=', self.project_id.id),
            ('parent_id', '=', self.parent_id.id if self.parent_id else False),
        ]

    def _sorted_siblings(self):
        self.ensure_one()
        siblings = self.env['product_module.arkite.job.step'].search(self._siblings_domain(), order='sequence, id')
        return siblings

    def _ensure_db_record(self):
        """Resolve NewId wrappers to their persisted record when possible."""
        self.ensure_one()
        if self.id:
            return self
        if getattr(self, '_origin', False) and self._origin.id:
            return self._origin
        return self

    def _resequence_project_tree(self):
        """Assign stable preorder-based global sequences so children stay near their parent in the list."""
        self.ensure_one()
        rec = self._ensure_db_record()
        if not rec.project_id:
            return

        Step = rec.env['product_module.arkite.job.step']
        records = Step.search([('project_id', '=', rec.project_id.id)], order='sequence, id')
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

        # Use skip_arkite_sync to avoid PATCHing dozens of steps for a UI-only resequence
        for i, r in enumerate(preorder, 1):
            r.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': i * 10})

        all_records = Step.search([('project_id', '=', rec.project_id.id)])
        all_records.invalidate_recordset(['hierarchical_level', 'parent_step_name', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_display'])

    def action_move_up(self):
        """Move this step up among siblings (same parent)."""
        self = self._ensure_db_record()
        self.ensure_one()
        siblings = self._sorted_siblings()
        idx = siblings.ids.index(self.id) if self.id in siblings.ids else -1
        if idx <= 0:
            return False

        prev_rec = siblings[idx - 1]
        # Normalize sibling sequences so swaps always change ordering
        siblings = self._sorted_siblings()
        for i, rec in enumerate(siblings, 1):
            rec.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': i * 10})
        siblings = self._sorted_siblings()
        idx = siblings.ids.index(self.id)
        prev_rec = siblings[idx - 1]
        a_seq, b_seq = self.sequence, prev_rec.sequence
        self.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': b_seq})
        prev_rec.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': a_seq})

        # Invalidate computed hierarchy fields for project
        all_records = self.env['product_module.arkite.job.step'].search([('project_id', '=', self.project_id.id)])
        all_records.invalidate_recordset(['hierarchical_level', 'parent_step_name', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_display'])
        try:
            all_records._compute_hierarchical_level()
            all_records._compute_parent_step_name()
            all_records._compute_hierarchy_css_class()
            all_records._compute_hierarchical_level_html()
        except Exception:
            pass
        self._resequence_project_tree()
        # Keep dialog open and refresh list content.
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_move_down(self):
        """Move this step down among siblings (same parent)."""
        self = self._ensure_db_record()
        self.ensure_one()
        siblings = self._sorted_siblings()
        idx = siblings.ids.index(self.id) if self.id in siblings.ids else -1
        if idx < 0 or idx >= len(siblings) - 1:
            return False

        # Normalize sibling sequences so swaps always change ordering
        siblings = self._sorted_siblings()
        for i, rec in enumerate(siblings, 1):
            rec.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': i * 10})
        siblings = self._sorted_siblings()
        idx = siblings.ids.index(self.id)
        next_rec = siblings[idx + 1]
        a_seq, b_seq = self.sequence, next_rec.sequence
        self.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': b_seq})
        next_rec.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({'sequence': a_seq})

        all_records = self.env['product_module.arkite.job.step'].search([('project_id', '=', self.project_id.id)])
        all_records.invalidate_recordset(['hierarchical_level', 'parent_step_name', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_display'])
        try:
            all_records._compute_hierarchical_level()
            all_records._compute_parent_step_name()
            all_records._compute_hierarchy_css_class()
            all_records._compute_hierarchical_level_html()
        except Exception:
            pass
        self._resequence_project_tree()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_indent(self):
        """Make this step a child of the previous visible step (indent)."""
        self = self._ensure_db_record()
        self.ensure_one()
        # Find the previous step in overall order (within project)
        ordered = self.env['product_module.arkite.job.step'].search([('project_id', '=', self.project_id.id)], order='sequence, id')
        try:
            idx = ordered.ids.index(self.id)
        except ValueError:
            return False

        if idx <= 0:
            return False

        new_parent = ordered[idx - 1]
        # Avoid circular parenting
        if new_parent.id == self.id:
            return False

        # Place after last child of new_parent
        siblings = self.env['product_module.arkite.job.step'].search([
            ('project_id', '=', self.project_id.id),
            ('parent_id', '=', new_parent.id),
        ], order='sequence desc, id desc', limit=1)
        new_seq = (siblings.sequence if siblings else new_parent.sequence) + 10

        self.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({
            'parent_id': new_parent.id,
            'sequence': new_seq,
        })
        all_records = self.env['product_module.arkite.job.step'].search([('project_id', '=', self.project_id.id)])
        all_records.invalidate_recordset(['hierarchical_level', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_name', 'parent_step_display'])
        self._resequence_project_tree()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_outdent(self):
        """Move this step one level up (outdent)."""
        self = self._ensure_db_record()
        self.ensure_one()
        if not self.parent_id:
            return False

        parent = self.parent_id
        new_parent = parent.parent_id

        # Place just after the current parent
        new_seq = (parent.sequence or 0) + 5
        self.with_context(skip_arkite_sync=True, skip_hierarchy_recompute=True).write({
            'parent_id': new_parent.id if new_parent else False,
            'sequence': new_seq,
        })
        all_records = self.env['product_module.arkite.job.step'].search([('project_id', '=', self.project_id.id)])
        all_records.invalidate_recordset(['hierarchical_level', 'hierarchy_css_class', 'hierarchical_level_html', 'parent_step_name', 'parent_step_display'])
        self._resequence_project_tree()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    # Note: we previously had a list/modal-based "reorder child steps" fallback and left/right helpers.
    # Those were removed in favor of the inline reorder panel inside the diagram (more consistent UX).
    
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
    
    @api.depends('parent_id', 'parent_id.hierarchy_path', 'step_name')
    def _compute_hierarchy_path(self):
        """Build full hierarchy path (e.g., 'Root > Child > Grandchild')"""
        for record in self:
            if not record.parent_id:
                record.hierarchy_path = record.step_name or "Root"
            else:
                parent_path = record.parent_id.hierarchy_path or record.parent_id.step_name or "Root"
                record.hierarchy_path = f"{parent_path} > {record.step_name or 'Unnamed'}"
    
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
                record.display_name_hierarchy = f"{indent}â””â”€ {name}"
    
    @api.depends('parent_id', 'parent_id.step_name')
    def _compute_parent_step_name(self):
        """Get the name of the parent step"""
        for record in self:
            if record.parent_id:
                record.parent_step_name = record.parent_id.step_name or "Unnamed Parent"
            else:
                record.parent_step_name = ""
    
    @api.depends('parent_id', 'parent_id.step_name')
    def _compute_parent_step_display(self):
        """Get parent step name for simple text display (no tree structure)"""
        for record in self:
            if record.parent_id:
                # Get just the step name, no tree characters
                parent_name = record.parent_id.step_name or "Unnamed Parent"
                # Remove any tree characters that might be in the name
                parent_name = parent_name.replace('â””â”€', '').replace('â”œâ”€', '').strip()
                record.parent_step_display = parent_name
            else:
                record.parent_step_display = ""
    
    def name_get(self):
        """Override name_get to return just step name without tree characters"""
        result = []
        for record in self:
            name = record.step_name or "Unnamed Step"
            # Remove any tree characters
            name = name.replace('â””â”€', '').replace('â”œâ”€', '').strip()
            result.append((record.id, name))
        return result
    
    @api.depends('parent_id', 'sequence', 'project_id')
    def _compute_hierarchical_level(self):
        """Compute hierarchical level in format like 2.1, 2.2, etc."""
        # Important: this compute is executed during onchanges in one2many.
        # In that case records are often "NewId" wrappers (rec.id is falsy) pointing to rec._origin.
        # We MUST assign a value to hierarchical_level for every record in self.

        # Default for truly unknown records (no project and no origin)
        for rec in self.filtered(lambda r: not r.project_id and not r._origin):
            rec.hierarchical_level = "?"

        # Determine projects involved (use origin as fallback).
        # NOTE: _origin is not a field (can't be used with mapped); it's an attribute for NewId records.
        project_ids = set()
        for rec in self:
            if rec.project_id:
                project_ids.add(rec.project_id.id)
            elif getattr(rec, '_origin', False) and rec._origin.project_id:
                project_ids.add(rec._origin.project_id.id)
        project_ids = list(project_ids)
        if not project_ids:
            # Ensure every record has something
            for rec in self:
                if not rec.hierarchical_level:
                    rec.hierarchical_level = "?"
            return
        
        # Get ALL records for these projects (not just self) to compute correctly
        all_project_records = self.env['product_module.arkite.job.step'].search([
            ('project_id', 'in', project_ids)
        ])
        
        # Group by project
        by_project = {}
        for record in all_project_records:
            if record.project_id:
                project_id = record.project_id.id
                if project_id not in by_project:
                    by_project[project_id] = []
                by_project[project_id].append(record)
        
        # Compute per project using "effective" values where self overrides DB values (onchange case)
        computed_levels = {}  # origin_id -> level

        for project_id, records in by_project.items():
            # Build overrides from self for this project keyed by origin id
            overrides = {}
            for r in self.filtered(lambda x: (x.project_id and x.project_id.id == project_id) or (x._origin and x._origin.project_id and x._origin.project_id.id == project_id)):
                origin_id = r._origin.id if r._origin else r.id
                if not origin_id:
                    continue
                parent_origin_id = r.parent_id._origin.id if r.parent_id and r.parent_id._origin else (r.parent_id.id if r.parent_id else False)
                overrides[origin_id] = {
                    'sequence': r.sequence or 0,
                    'parent_origin_id': parent_origin_id or False,
                }

            record_ids = {r.id for r in records}

            # Build children map using effective parent (override if present)
            children_map = {}
            roots = []
            effective_seq = {}

            for rec in records:
                origin_id = rec.id
                ov = overrides.get(origin_id, {})
                seq = ov.get('sequence', rec.sequence or 0)
                pid = ov.get('parent_origin_id', rec.parent_id.id if rec.parent_id else False)
                if pid and pid not in record_ids:
                    pid = False
                effective_seq[origin_id] = seq
                if not pid:
                    roots.append(origin_id)
                else:
                    children_map.setdefault(pid, []).append(origin_id)

            # Sort roots by effective sequence then id
            roots.sort(key=lambda oid: (effective_seq.get(oid, 0), oid))
            for i, root_id in enumerate(roots, 1):
                root_level = str(i)
                computed_levels[root_id] = root_level

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
                        computed_levels[child_id] = child_level
                        stack.append((child_id, child_level))

            # Unassigned DB records => '?'
            for rec in records:
                if rec.id not in computed_levels:
                    computed_levels[rec.id] = "?"

        # Assign back to DB records + self (including NewId wrappers)
        for rec in all_project_records:
            if rec.id in computed_levels:
                rec.hierarchical_level = computed_levels[rec.id]

        for rec in self:
            origin_id = rec._origin.id if rec._origin else rec.id
            if origin_id and origin_id in computed_levels:
                rec.hierarchical_level = computed_levels[origin_id]
            elif not rec.hierarchical_level:
                rec.hierarchical_level = "?"
    
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
                    # UX: avoid long "1.2.3.4.5" strings in grids. Keep full value in tooltip.
                    short_level = f"{parts[0]}.{parts[1]}â€¦{parts[-1]}"

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
    def create(self, vals):
        """Override create to ensure job_step_id is always set"""
        # Ensure job_step_id is always set - it's required
        if 'job_step_id' not in vals or not vals.get('job_step_id'):
            # Try to get it from step_id as fallback
            if vals.get('step_id'):
                vals['job_step_id'] = vals['step_id']
            # If still not set, try to get from parent
            elif vals.get('parent_id'):
                try:
                    parent = self.env['product_module.arkite.job.step'].browse(vals['parent_id'])
                    if parent.exists() and parent.job_step_id:
                        vals['job_step_id'] = parent.job_step_id
                except Exception:
                    pass
            # If still not set, try to find existing job steps for this project
            elif vals.get('project_id'):
                try:
                    existing = self.env['product_module.arkite.job.step'].search([
                        ('project_id', '=', vals['project_id'])
                    ], limit=1, order='id desc')
                    if existing and existing.job_step_id:
                        vals['job_step_id'] = existing.job_step_id
                except Exception:
                    pass
        
        # If still not set and we're creating a new step (not loading from Arkite), 
        # we'll set it after creating the step in Arkite
        # Don't raise error yet - let the Arkite creation logic handle it
        
        # If step_id is not provided, create the step in Arkite first
        if not vals.get('step_id'):
            # Create new step in Arkite
            try:
                project_id = None
                if vals.get('project_id'):
                    project = self.env['product_module.project'].browse(vals['project_id'])
                    if project and project.arkite_project_id:
                        project_id = project.arkite_project_id
                
                if not project_id:
                    raise UserError("Project must have an Arkite project ID to create steps.")
                
                # Get credentials
                api_base = os.getenv('ARKITE_API_BASE')
                api_key = os.getenv('ARKITE_API_KEY')
                
                if vals.get('project_id'):
                    try:
                        project = self.env['product_module.project'].browse(vals['project_id'])
                        if project:
                            creds = project._get_arkite_credentials()
                            api_base = creds['api_base']
                            api_key = creds['api_key']
                    except Exception:
                        pass
                
                if not api_base or not api_key:
                    raise UserError("Arkite API configuration is missing.")
                
                # Determine parent step ID - job steps MUST have a valid parent
                parent_step_id = None
                
                # Helper function to validate step ID
                def is_valid_step_id(step_id):
                    """Check if step ID is valid (not None, 0, empty, or "0")"""
                    if not step_id:
                        return False
                    step_id_str = str(step_id).strip()
                    return step_id_str != "" and step_id_str != "0" and step_id_str.lower() != "none"
                
                # First, try to get parent from parent_id
                if vals.get('parent_id'):
                    try:
                        parent = self.env['product_module.arkite.job.step'].browse(vals['parent_id'])
                        if parent.exists() and parent.step_id and is_valid_step_id(parent.step_id):
                            if parent.step_type == 'COMPOSITE':
                                parent_step_id = str(parent.step_id).strip()
                                _logger.info("[ARKITE] Using COMPOSITE parent step %s for new job step", parent_step_id)
                            else:
                                _logger.warning("[ARKITE] Parent step %s is not COMPOSITE, will auto-detect", parent.step_id)
                        elif parent.exists() and parent.step_id:
                            _logger.warning("[ARKITE] Parent step ID %s is invalid, will auto-detect", parent.step_id)
                    except Exception as e:
                        _logger.warning("[ARKITE] Error getting parent step: %s", e)
                
                # If no valid parent found, auto-detect from existing steps (like the wizard does)
                if not parent_step_id or not is_valid_step_id(parent_step_id):
                    _logger.info("[ARKITE] Auto-detecting parent step from existing job steps...")
                    try:
                        url_check = f"{api_base}/projects/{project_id}/steps/"
                        params_check = {"apiKey": api_key}
                        headers_check = {"Content-Type": "application/json"}
                        check_response = requests.get(url_check, params=params_check, headers=headers_check, verify=False, timeout=10)
                        if check_response.ok:
                            all_steps = check_response.json()
                            if isinstance(all_steps, list) and all_steps:
                                # Filter for job steps (Type="Job" or ProcessId="0")
                                job_steps = [s for s in all_steps 
                                           if s.get("Type") == "Job" or 
                                           (not s.get("ProcessId") or str(s.get("ProcessId", "")) == "0")]
                                
                                if job_steps:
                                    # Priority 1: Find root COMPOSITE step (Type="Job", StepType="COMPOSITE", no parent)
                                    for step in job_steps:
                                        step_id = step.get("Id")
                                        if (step.get("Type") == "Job" and 
                                            step.get("StepType") == "COMPOSITE" and
                                            is_valid_step_id(step_id) and
                                            (not step.get("ParentStepId") or 
                                             str(step.get("ParentStepId", "")) == "0")):
                                            parent_step_id = str(step_id).strip()
                                            _logger.info("[ARKITE] Auto-detected root COMPOSITE step %s as parent", parent_step_id)
                                            break
                                    
                                    # Priority 2: If no COMPOSITE found, use any COMPOSITE step
                                    if not parent_step_id or not is_valid_step_id(parent_step_id):
                                        for step in job_steps:
                                            step_id = step.get("Id")
                                            if step.get("StepType") == "COMPOSITE" and is_valid_step_id(step_id):
                                                parent_step_id = str(step_id).strip()
                                                _logger.info("[ARKITE] Found COMPOSITE step %s to use as parent", parent_step_id)
                                                break
                                    
                                    # Priority 3: Fallback to any root job step
                                    if not parent_step_id or not is_valid_step_id(parent_step_id):
                                        for step in job_steps:
                                            step_id = step.get("Id")
                                            if (is_valid_step_id(step_id) and
                                                (not step.get("ParentStepId") or str(step.get("ParentStepId", "")) == "0")):
                                                parent_step_id = str(step_id).strip()
                                                _logger.info("[ARKITE] Using root job step %s as parent (fallback)", parent_step_id)
                                                break
                                    
                                    # Priority 4: Last resort - use any job step
                                    if not parent_step_id or not is_valid_step_id(parent_step_id):
                                        for step in job_steps:
                                            step_id = step.get("Id")
                                            if is_valid_step_id(step_id):
                                                parent_step_id = str(step_id).strip()
                                                _logger.info("[ARKITE] Using job step %s as parent (last resort)", parent_step_id)
                                                break
                                else:
                                    _logger.warning("[ARKITE] No job steps found in project")
                            else:
                                _logger.warning("[ARKITE] No steps found in project or invalid response format")
                        else:
                            _logger.warning("[ARKITE] Failed to fetch steps: HTTP %s", check_response.status_code)
                    except Exception as e:
                        _logger.error("[ARKITE] Error auto-detecting parent step: %s", e, exc_info=True)
                
                # Build step payload for job step
                step_data = {
                    "Type": "Job",  # Job steps have Type="Job"
                    "Name": vals.get('step_name', 'Unnamed Step'),
                    "StepType": vals.get('step_type', 'WORK_INSTRUCTION'),
                    "ProcessId": "0",  # Job steps have ProcessId="0"
                    "Index": vals.get('sequence', 0) // 10 if vals.get('sequence', 0) > 0 else 0,
                    "ForAllVariants": vals.get('for_all_variants', False),
                    "VariantIds": [],
                    "TextInstruction": {},
                    "ImageInstructionId": "0",
                    "ChildStepOrder": "None" if vals.get('step_type') != "COMPOSITE" else "Sequential",
                    "StepControlflow": "None",
                    "StepConditions": [],
                    "Comment": None
                }
                
                # CRITICAL: Arkite REQUIRES ParentStepId for job steps - we must ALWAYS set it to a valid ID
                # Validate that we have a valid parent step ID
                if not parent_step_id or not is_valid_step_id(parent_step_id):
                    raise UserError(_(
                        "Cannot create job step: No valid parent step found.\n\n"
                        "Please ensure:\n"
                        "1. There is at least one existing job step in the project\n"
                        "2. Or create a COMPOSITE step first in Arkite UI\n"
                        "3. Or specify a valid Parent Step ID manually"
                    ))
                
                # ALWAYS set ParentStepId - Arkite requires it for job steps
                step_data["ParentStepId"] = str(parent_step_id).strip()
                _logger.info("[ARKITE] Setting ParentStepId to %s", step_data["ParentStepId"])
                
                # Create step in Arkite
                url = f"{api_base}/projects/{project_id}/steps/"
                params = {"apiKey": api_key}
                headers = {"Content-Type": "application/json"}
                
                # Final verification - ensure ParentStepId is valid and not "0"
                if "ParentStepId" not in step_data:
                    raise UserError(_("ParentStepId is required for job steps but was not set. This should not happen."))
                
                parent_id_value = step_data["ParentStepId"]
                if not is_valid_step_id(parent_id_value):
                    raise UserError(_("Invalid ParentStepId: '%s'. Cannot create job step with invalid parent.") % parent_id_value)
                
                # Log the final payload (for debugging)
                payload_summary = {k: v for k, v in step_data.items() if k not in ["TextInstruction", "StepConditions"]}
                _logger.info("[ARKITE] Creating job step - Name: '%s', ParentStepId: '%s'", step_data.get("Name"), parent_id_value)
                _logger.debug("[ARKITE] Full payload: %s", json.dumps(payload_summary, indent=2))
                
                response = requests.post(url, params=params, json=[step_data], headers=headers, verify=False, timeout=10)
                
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
                    # Check if step was created despite error (API bug)
                    _logger.warning("[ARKITE] API returned error, checking if step was created...")
                    time.sleep(1)
                    verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                    if verify_response.ok:
                        all_steps = verify_response.json()
                        matching_steps = [s for s in all_steps 
                                         if s.get("Name") == step_data["Name"] 
                                         and str(s.get("ProcessId", "")) == "0"]
                        if matching_steps:
                            created_step_id = matching_steps[0].get("Id", "Unknown")
                            step_created = True
                            _logger.info("[ARKITE] Step was created successfully despite API error (ID: %s)", created_step_id)
                
                if step_created:
                    vals['step_id'] = str(created_step_id)
                    # Ensure required job_step_id is set when creating a new root step
                    # (fresh projects may have no existing job_step_id to inherit).
                    if not vals.get('job_step_id'):
                        vals['job_step_id'] = vals['step_id']
                    # Get actual index
                    verify_response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                    if verify_response.ok:
                        steps = verify_response.json()
                        new_step = next((s for s in steps if str(s.get("Id", "")) == str(created_step_id)), None)
                        if new_step:
                            vals['index'] = new_step.get("Index", 0)
                else:
                    error_text = response.text[:500] if response.text else "Unknown error"
                    raise UserError(f"Failed to create job step in Arkite: HTTP {response.status_code}\n{error_text}")
                    
            except UserError:
                raise
            except Exception as e:
                _logger.error("[ARKITE] Error creating job step: %s", e, exc_info=True)
                raise UserError(f"Error creating job step in Arkite: {str(e)}")
        
        # Create the record (either with existing step_id or newly created one)
        record = super().create(vals)
        
        # Force recomputation of hierarchical_level and hierarchy_css_class after creation
        if record.project_id:
            # Invalidate first, then recompute for all records in the project
            all_records = self.env['product_module.arkite.job.step'].search([
                ('project_id', '=', record.project_id.id)
            ])
            all_records.invalidate_recordset(['hierarchical_level', 'parent_step_name', 'hierarchy_css_class', 'hierarchical_level_html'])
            all_records._compute_hierarchical_level()
            all_records._compute_parent_step_name()
            all_records._compute_hierarchy_css_class()
            all_records._compute_hierarchical_level_html()
        
        return record
    
    def write(self, vals):
        """Override write to sync changes back to Arkite"""
        # Normalize StepType coming from Arkite/UI so it always matches selection keys.
        if 'step_type' in vals and vals.get('step_type'):
            original = vals.get('step_type')
            normalized, raw = self._normalize_step_type_value(original)
            vals['step_type'] = normalized
            if raw:
                vals['step_type_raw'] = raw

        result = super().write(vals)

        # If the user is editing in "deferred sync" mode (hierarchy/diagram screens), mark project dirty.
        if self.env.context.get('defer_arkite_sync') and ('sequence' in vals or 'parent_id' in vals):
            project_ids = list(set(self.mapped('project_id').ids))
            if project_ids:
                self.env.cr.execute(
                    "UPDATE product_module_project SET arkite_job_steps_dirty = TRUE, arkite_hierarchy_dirty = TRUE WHERE id = ANY(%s)",
                    [project_ids],
                )
                self.env['product_module.project'].browse(project_ids).invalidate_recordset([
                    'arkite_hierarchy_dirty',
                    'arkite_job_steps_dirty',
                ])
            # Normalize sibling sequences ONLY for diagram reorder (not list resequence).
            if self.env.context.get('pm_diagram_reorder') and not self.env.context.get('pm_list_resequence'):
                groups = set()
                for rec in self:
                    groups.add((rec.project_id.id, rec.parent_id.id if rec.parent_id else None))
                for project_id, parent_rec_id in groups:
                    siblings = self.env['product_module.arkite.job.step'].search([
                        ('project_id', '=', project_id),
                        ('parent_id', '=', parent_rec_id or False),
                    ], order='sequence,id')
                    seq = 10
                    for s in siblings:
                        self.env.cr.execute(
                            "UPDATE product_module_arkite_job_step SET sequence=%s WHERE id=%s",
                            [seq, s.id],
                        )
                        seq += 10
                self.invalidate_recordset(['sequence'])
        
        # Invalidate computed fields AFTER write to trigger recomputation on next read
        # This avoids serialization errors from concurrent updates during write
        if 'sequence' in vals or 'parent_id' in vals:
            # Invalidate for all records in affected projects to ensure consistency
            project_ids = list(set(self.mapped('project_id').ids))
            if project_ids:
                all_records = self.env['product_module.arkite.job.step'].search([
                    ('project_id', 'in', project_ids)
                ])
                # Invalidate to trigger recomputation on next read
                all_records.invalidate_recordset(['hierarchical_level', 'parent_step_name', 'hierarchy_css_class', 'hierarchical_level_html'])
                # Force recomputation immediately for current records to update UI
                try:
                    all_records._compute_hierarchical_level()
                    all_records._compute_parent_step_name()
                except Exception as e:
                    # If recomputation fails (e.g., serialization error), just invalidate
                    # The fields will be recomputed on next read
                    _logger.warning("[HIERARCHY] Could not recompute levels during write: %s", e)
        
        # Skip Arkite sync if context flag is set (to prevent infinite loops) or when user is editing in a staged UI.
        if self.env.context.get('skip_arkite_sync') or self.env.context.get('defer_arkite_sync'):
            return result
        
        # Sync to Arkite if relevant fields changed
        sync_fields = ['step_name', 'step_type', 'sequence', 'for_all_variants', 'parent_id']
        if any(field in vals for field in sync_fields):
            for record in self:
                if not record.step_id or not record.project_id:
                    continue
                
                try:
                    project = record.project_id
                    if not project.arkite_project_id:
                        continue
                    
                    creds = project._get_arkite_credentials()
                    api_base = creds['api_base']
                    api_key = creds['api_key']
                    
                    # Get current step data from Arkite
                    url = f"{api_base}/projects/{project.arkite_project_id}/steps/{record.step_id}/"
                    params = {"apiKey": api_key}
                    headers = {"Content-Type": "application/json"}
                    
                    response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)
                    if not response.ok:
                        _logger.warning("[ARKITE] Could not fetch step %s for update", record.step_id)
                        continue
                    
                    step_data = response.json()
                    
                    # Update fields that changed
                    if 'step_name' in vals:
                        step_data["Name"] = record.step_name
                    if 'step_type' in vals:
                        step_data["StepType"] = record.step_type
                        step_data["ChildStepOrder"] = "Sequential" if record.step_type == "COMPOSITE" else "None"
                    if 'sequence' in vals:
                        # Convert sequence to Index (sequence is typically multiples of 10, Index is the actual order)
                        new_index = record.sequence // 10 if record.sequence > 0 else 0
                        old_index = step_data.get("Index", 0)
                        _logger.info("[ARKITE] Job step %s sequence changed: %s -> Index %s (was %s)", record.step_id, record.sequence, new_index, old_index)
                        step_data["Index"] = new_index
                    if 'for_all_variants' in vals:
                        step_data["ForAllVariants"] = record.for_all_variants
                    if 'parent_id' in vals:
                        if record.parent_id and record.parent_id.step_id:
                            step_data["ParentStepId"] = record.parent_id.step_id
                        else:
                            # Remove ParentStepId or set to "0" for root steps
                            if "ParentStepId" in step_data:
                                del step_data["ParentStepId"]
                    
                    # Update step in Arkite
                    _logger.info("[ARKITE] Patching job step %s with data: %s", record.step_id, {k: v for k, v in step_data.items() if k in ['Name', 'StepType', 'Index', 'ParentStepId']})
                    patch_response = requests.patch(url, params=params, headers=headers, json=step_data, verify=False, timeout=10)
                    if patch_response.ok:
                        _logger.info("[ARKITE] Successfully updated job step %s in Arkite", record.step_id)
                        # Update index from response
                        updated_data = patch_response.json()
                        if isinstance(updated_data, dict) and updated_data.get("Index") is not None:
                            record.index = updated_data.get("Index", 0)
                    else:
                        _logger.warning("[ARKITE] Failed to update step %s: HTTP %s", record.step_id, patch_response.status_code)
                        
                except Exception as e:
                    _logger.warning("[ARKITE] Error syncing job step %s to Arkite: %s", record.step_id, e)
        
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
        """Return (normalized, raw_if_unknown).

        Arkite sometimes returns StepType in different formats (camelCase, spaces, hyphens).
        We normalize to our selection keys (e.g. TOOL_PLACING, CHECK_NO_CHANGE_ZONE).
        """
        if not value:
            return 'WORK_INSTRUCTION', False

        raw = str(value).strip()
        if not raw:
            return 'WORK_INSTRUCTION', False

        # Normalize: camelCase -> CAMEL_CASE, spaces/hyphens -> underscore, uppercase.
        s = raw
        s = re.sub(r"\s+", "_", s)
        s = s.replace("-", "_")
        # Insert underscores before capitals when needed: ToolPlacing -> Tool_Placing
        s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s)
        s = s.upper()
        # Common suffix cleanup
        if s.endswith("_STEP"):
            s = s[:-5]
        if s.endswith("STEP"):
            s = s[:-4]
        s = re.sub(r"_+", "_", s).strip("_")

        # Validate against selection keys
        allowed = {k for k, _label in (self._fields['step_type'].selection or [])}
        if s in allowed:
            return s, False

        # Heuristic: sometimes Arkite returns "WORKINSTRUCTION"
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

        _logger.warning("[ARKITE] Unknown StepType '%s' (normalized '%s') for job step; falling back to WORK_INSTRUCTION", raw, s)
        return 'WORK_INSTRUCTION', raw

    def action_discard_changes(self):
        """Discard local hierarchy changes by reloading from Arkite."""
        self.ensure_one()
        if not self.project_id:
            return False
        self.project_id.action_load_job_steps()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def action_sync_to_arkite(self):
        """Apply current local order/parent changes to Arkite."""
        self.ensure_one()
        if not self.project_id:
            return False

        # Sync ALL steps for this project (the button is shown per-row in list/diagram).
        records = self.env['product_module.arkite.job.step'].search([('project_id', '=', self.project_id.id)])
        # Sync by re-writing each record with defer disabled; write() already patches Arkite fields.
        for rec in records.sorted(lambda r: (r.sequence or 0, r.id)):
            rec.with_context(defer_arkite_sync=False).write({
                'sequence': rec.sequence,
                'parent_id': rec.parent_id.id if rec.parent_id else False,
            })
        return {'type': 'ir.actions.client', 'tag': 'display_notification', 'params': {'title': _('Saved'), 'message': _('Saved hierarchy changes to Arkite.'), 'type': 'success', 'sticky': False}}

    @api.model
    def pm_action_save_all(self):
        """Save ALL staged job-step changes to Arkite for the project in context.

        Called from hierarchy control panel buttons (no record selection).
        """
        project_id = self.env.context.get('default_project_id')
        if not project_id:
            return False
        records = self.env['product_module.arkite.job.step'].search([('project_id', '=', project_id)])

        # Sync only records that actually differ from Arkite's last-synced state.
        to_sync_ids = []
        for rec in records:
            desired_index = int((rec.sequence or 0) // 10) if rec.sequence else 0
            current_index = int(rec.index or 0)
            desired_parent = ''
            if rec.parent_id and rec.parent_id.step_id:
                desired_parent = str(rec.parent_id.step_id).strip()
            current_parent = str(rec.parent_step_id or '').strip()
            if desired_index != current_index or desired_parent != current_parent:
                to_sync_ids.append(rec.id)

        to_sync = records.browse(to_sync_ids)
        for rec in to_sync.sorted(lambda r: (r.sequence or 0, r.id)):
            rec.with_context(defer_arkite_sync=False).write({
                'sequence': rec.sequence,
                'parent_id': rec.parent_id.id if rec.parent_id else False,
            })

        if not to_sync:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': _('No changes'), 'message': _('No staged Job Step changes to sync.'), 'type': 'info', 'sticky': False},
            }
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': _('Saved'), 'message': _('Saved Job Steps to Arkite.'), 'type': 'success', 'sticky': False},
        }
@api.model
    def pm_action_discard_all(self):
        """Discard staged job-step changes by reloading from Arkite for the project in context."""
        project_id = self.env.context.get('default_project_id')
        if not project_id:
            return False
        project = self.env['product_module.project'].browse(project_id)
        if not project.exists():
            return False
        project.action_load_job_steps()
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    def unlink(self):
        """Unlink local transient records.

        IMPORTANT: This model is a TransientModel, so Odoo's auto-vacuum will unlink rows periodically.
        We must NOT delete anything in Arkite from unlink(), otherwise background cleanup can delete real
        Arkite steps unexpectedly.
        """
        return super().unlink()


