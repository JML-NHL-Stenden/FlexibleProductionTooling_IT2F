# product_module/models/arkite_project_selection.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import requests
import os
import logging

_logger = logging.getLogger(__name__)


class ArkiteProjectSelection(models.TransientModel):
    """Temporary model for selecting Arkite projects or templates"""
    _name = 'product_module.arkite.project.selection'
    _description = 'Select Arkite Project or Template'
    _rec_name = 'display_name'
    
    selection_type = fields.Selection([
        ('template', 'Template'),
        ('project', 'Project'),
    ], string='Selection Type', required=True)

    # When opening the wizard outside a Project form, the user must pick which Odoo Project
    # to link/sync the duplicated Arkite project into.
    odoo_project_id = fields.Many2one(
        'product_module.project',
        string='Odoo Project',
        required=False,
        help='The Odoo Project that will be linked to the selected / duplicated Arkite project.',
    )

    arkite_unit_id = fields.Many2one(
        'product_module.arkite.unit',
        string='Arkite Unit',
        required=False,
        help='Select the Arkite Unit (server credentials). Required when duplicating from the Dashboard.',
    )

    # For templates - store the Arkite project ID directly
    template_arkite_project_id = fields.Char(
        string='Template Project ID',
        help='Arkite project ID to use as template'
    )
    template_arkite_project_name = fields.Char(
        string='Template Project Name',
        readonly=True,
        help='Name of the selected template project'
    )
    available_template_ids = fields.One2many(
        'product_module.arkite.project.selection.template',
        'selection_id',
        string='Available Projects',
        help='List of available projects from Arkite'
    )

    # Project name for duplication
    new_project_name = fields.Char(
        string='New Project Name',
        required=False,
        help='Name for the duplicated project'
    )

    # For projects (from Arkite API)
    arkite_project_id = fields.Char(string='Arkite Project ID')
    arkite_project_name = fields.Char(string='Arkite Project Name')

    display_name = fields.Char(string='Name', compute='_compute_display_name')
    selection_ids = fields.One2many(
        'product_module.arkite.project.selection',
        'parent_id',
        string='Available Projects'
    )
    parent_id = fields.Many2one('product_module.arkite.project.selection', string='Parent')

    @api.model
    def default_get(self, fields_list):
        """Set default values - don't load templates here to avoid transaction issues"""
        res = super().default_get(fields_list)

        # Set default project name from Odoo project
        if self.env.context.get('default_selection_type') == 'template':
            active_id = self.env.context.get('active_id')
            active_model = self.env.context.get('active_model')

            if active_model == 'product_module.project' and active_id and 'odoo_project_id' in fields_list:
                res['odoo_project_id'] = active_id

            if active_id and 'new_project_name' in fields_list:
                try:
                    # Just read the name, don't do any writes
                    odoo_project = self.env['product_module.project'].browse(active_id)
                    if odoo_project.exists():
                        res['new_project_name'] = odoo_project.name
                except Exception as e:
                    _logger.debug("Error getting project name in default_get: %s", e)
                    # Don't fail - just skip setting the default

        return res


    # -----------------------
    # Arkite credentials/util
    # -----------------------

    def _pm_get_arkite_api_credentials(self, require_unit: bool = False):
        """Resolve Arkite API credentials for this wizard.

        If require_unit=True, credentials MUST come from the active Odoo Project's Arkite Unit
        (no fallback to environment variables). This prevents accidental cross-server usage and
        matches the expected UX: the wizard should not "guess" credentials.
        """
        api_base = None
        api_key = None

        # Prefer explicit wizard selection, else fall back to context active_id (Project only).
        odoo_project = self.odoo_project_id
        if not odoo_project:
            active_id = self.env.context.get('active_id')
            active_model = self.env.context.get('active_model')
            if active_model == 'product_module.project' and active_id:
                odoo_project = self.env['product_module.project'].browse(active_id)

        if odoo_project:
            if odoo_project.exists() and odoo_project.arkite_unit_id:
                unit = odoo_project.arkite_unit_id
                api_base = unit.api_base
                api_key = unit.api_key

        # If no active/selected Project, allow choosing the Unit directly (Dashboard flow).
        if (not api_base or not api_key) and self.arkite_unit_id:
            api_base = self.arkite_unit_id.api_base
            api_key = self.arkite_unit_id.api_key

        if require_unit and (not api_base or not api_key):
            raise UserError(_(
                'Please select an Arkite Unit first.\n\n'
                'If you launched this from a Project, set the Project\'s Arkite Unit.\n'
                'If you launched this from the Dashboard, select the Unit in this wizard.'
            ))

        if not api_base or not api_key:
            # Fallback for backward compatibility (only when require_unit=False)
            api_base = os.getenv('ARKITE_API_BASE')
            api_key = os.getenv('ARKITE_API_KEY')

        if not api_base or not api_key:
            raise UserError(_(
                'Arkite API configuration is missing.\n\n'
                'Fix:\n'
                '- Assign an Arkite Unit to this project (recommended), or\n'
                '- Set ARKITE_API_BASE and ARKITE_API_KEY in the environment.'
            ))

        return api_base, api_key

    @staticmethod
    def _pm_raise_auth_error(api_base):
        raise UserError(_(
            'Authentication failed (HTTP 401).\n\n'
            'This usually means the API key does not match the Arkite server.\n\n'
            'Server: %s\n\n'
            'Fix:\n'
            '- Ensure the selected Arkite Unit has the correct API Base + API Key for that server, or\n'
            '- Update ARKITE_API_BASE / ARKITE_API_KEY to the correct pair.'
        ) % (api_base,))

    def action_load_available_projects(self):
        """Load available projects from Arkite API to show as templates"""
        self.ensure_one()

        api_base, api_key = self._pm_get_arkite_api_credentials(require_unit=True)

        url = f"{api_base}/projects/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)

            if response.status_code == 401:
                self._pm_raise_auth_error(api_base)

            if not response.ok:
                raise UserError(_('Failed to fetch projects from Arkite: HTTP %s') % response.status_code)

            projects = response.json()

            if not isinstance(projects, list):
                raise UserError(_('Invalid response from Arkite API. Expected a list of projects.'))

            if not projects:
                raise UserError(_('No projects found in Arkite. Please create projects in Arkite first.'))

            # Clear existing template records
            self.available_template_ids.unlink()

            # Create temporary records for each project
            template_model = self.env['product_module.arkite.project.selection.template']
            for proj in projects:
                project_id = proj.get("Id") or proj.get("ProjectId")
                project_name = proj.get("Name") or proj.get("ProjectName", "Unnamed")
                if project_id:
                    template_model.create({
                        'selection_id': self.id,
                        'project_id': str(project_id),
                        'project_name': project_name,
                    })

            # Commit so the dialog immediately sees the newly created one2many rows
            self.env.cr.commit()

            # Toast + reopen the same wizard (forces modal refresh so the list is visible)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Projects Loaded'),
                    'message': _('Found %d project(s) in Arkite. Select one from the list below.') % len(projects),
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'product_module.arkite.project.selection',
                        'res_id': self.id,
                        'view_mode': 'form',
                        # Reopen the TEMPLATE selection wizard (not the project-link wizard).
                        'view_id': self.env.ref('product_module.view_arkite_template_selection').id,
                        'views': [(self.env.ref('product_module.view_arkite_template_selection').id, 'form')],
                        'target': 'new',
                        'context': dict(self.env.context),
                    },
                }
            }
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error loading projects: %s", e)
            raise UserError(_('Error loading projects: %s') % str(e))

    def action_load_arkite_projects(self):
        """Load available projects from Arkite API for project selection (linking)"""
        self.ensure_one()

        api_base, api_key = self._pm_get_arkite_api_credentials(require_unit=True)

        url = f"{api_base}/projects/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}

        try:
            _logger.info("Loading projects from Arkite API: %s", url)
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)

            if response.status_code == 401:
                self._pm_raise_auth_error(api_base)

            if not response.ok:
                error_text = response.text[:500] if response.text else "No error details"
                _logger.error("Arkite API returned error: HTTP %s - %s", response.status_code, error_text)
                raise UserError(_('Failed to fetch projects from Arkite: HTTP %s\n\nError: %s\n\nPlease check:\n1. API Base URL is correct: %s\n2. API Key is valid\n3. Arkite server is accessible') % (response.status_code, error_text, api_base))

            projects = response.json()

            if not isinstance(projects, list):
                _logger.error("Invalid response type from Arkite API: %s", type(projects))
                raise UserError(_('Invalid response from Arkite API. Expected a list of projects, got: %s\n\nResponse: %s') % (type(projects).__name__, str(projects)[:200]))

            if not projects:
                raise UserError(_('No projects found in Arkite. Please create projects in Arkite first.'))

            # Ensure self has an ID (save if needed)
            if not self.id:
                vals = {
                    'selection_type': self.env.context.get('default_selection_type', 'project'),
                }
                self = self.create(vals)

            # Clear existing selection records
            self.selection_ids.unlink()

            # Create temporary records for each project
            created_count = 0
            for proj in projects:
                if not isinstance(proj, dict):
                    _logger.warning("Skipping non-dict project item: %s", type(proj))
                    continue

                project_id = proj.get("Id") or proj.get("ProjectId")
                project_name = proj.get("Name") or proj.get("ProjectName", "Unnamed")
                if project_id:
                    try:
                        self.env['product_module.arkite.project.selection'].create({
                            'parent_id': self.id,
                            'selection_type': 'project',
                            'arkite_project_id': str(project_id),
                            'arkite_project_name': str(project_name) if project_name else "Unnamed",
                        })
                        created_count += 1
                    except Exception as e:
                        _logger.error("Error creating selection record for project %s: %s", project_id, e, exc_info=True)
                        # Continue with next project
                        continue

            # Commit the changes to ensure they're visible
            self.env.cr.commit()

            # Toast + reopen the same wizard (forces modal refresh so the list is visible)
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Projects Loaded'),
                    'message': _('Found %d project(s) in Arkite. Select one from the list below.') % created_count,
                    'type': 'success',
                    'sticky': False,
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'product_module.arkite.project.selection',
                        'res_id': self.id,
                        'view_mode': 'form',
                        'view_id': self.env.ref('product_module.view_arkite_project_selection').id,
                        'views': [(self.env.ref('product_module.view_arkite_project_selection').id, 'form')],
                        'target': 'new',
                        'context': dict(self.env.context),
                    },
                }
            }
        except requests.exceptions.ConnectionError as e:
            _logger.error("Connection error to Arkite API: %s", e, exc_info=True)
            raise UserError(_('Connection error: Cannot reach Arkite API at %s\n\nPlease check:\n1. API Base URL is correct: %s\n2. Arkite server is running and accessible\n3. Network connectivity\n\nError: %s') % (api_base, api_base, str(e)))
        except requests.exceptions.Timeout as e:
            _logger.error("Timeout error connecting to Arkite API: %s", e, exc_info=True)
            raise UserError(_('Timeout error: Arkite API did not respond in time\n\nPlease check:\n1. API Base URL is correct: %s\n2. Arkite server is running\n3. Network connectivity\n\nError: %s') % (api_base, str(e)))
        except requests.exceptions.RequestException as e:
            _logger.error("Request error to Arkite API: %s", e, exc_info=True)
            raise UserError(_('Connection error: %s\n\nPlease check:\n1. API Base URL is correct: %s\n2. API Key is valid\n3. Arkite server is accessible\n\nError: %s') % (str(e), api_base, str(e)))
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error loading projects: %s", e, exc_info=True)
            raise UserError(_('Error loading projects: %s\n\nPlease check your API configuration and try again.') % str(e))

    def action_select_template_project(self):
        """Select a project from the available list as template"""
        self.ensure_one()
        template_record_id = self.env.context.get('template_record_id')

        # If called from template model, use the calling record
        if not template_record_id:
            # Try to get from active_id if called from template button
            active_id = self.env.context.get('active_id')
            if active_id:
                template_record = self.env['product_module.arkite.project.selection.template'].browse(active_id)
                if template_record.exists() and template_record.selection_id == self:
                    template_record_id = active_id

        if not template_record_id:
            raise UserError(_('No project selected.'))

        template_record = self.env['product_module.arkite.project.selection.template'].browse(template_record_id)
        if not template_record.exists() or template_record.selection_id != self:
            raise UserError(_('Invalid project selection.'))

        self.write({
            'template_arkite_project_id': template_record.project_id,
            'template_arkite_project_name': template_record.project_name,
        })

        # IMPORTANT: Do not return `tag: reload` here.
        # In Odoo 18, that often reloads the entire underlying action (looks like a full page refresh)
        # and can close/lose the wizard state. Reopen the same wizard record instead.
        view_id = self.env.ref('product_module.view_arkite_template_selection').id
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product_module.arkite.project.selection',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': view_id,
            'views': [(view_id, 'form')],
            'target': 'new',
            'context': dict(self.env.context),
        }

    def _get_project_id_by_name(self, project_name):
        """Get Arkite project ID by name"""
        api_base, api_key = self._pm_get_arkite_api_credentials(require_unit=True)

        url = f"{api_base}/projects/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)

            if response.status_code == 401:
                self._pm_raise_auth_error(api_base)
            if response.ok:
                projects = response.json()
                if isinstance(projects, list):
                    for proj in projects:
                        proj_name = proj.get("Name") or proj.get("ProjectName", "")
                        if proj_name == project_name:
                            return proj.get("Id") or proj.get("ProjectId")
        except Exception:
            pass

        return None

    def _duplicate_project(self, template_id, new_project_name):
        """Duplicate a project from template"""
        api_base, api_key = self._pm_get_arkite_api_credentials(require_unit=True)

        # Check if project with same name already exists
        existing_id = self._get_project_id_by_name(new_project_name)
        if existing_id:
            # Update existing project instead of creating new
            return str(existing_id)

        # Duplicate the template project
        url = f"{api_base}/projects/{template_id}/duplicate/"
        params = {"apiKey": api_key}
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.post(url, params=params, headers=headers, verify=False, timeout=60)
            if response.status_code == 401:
                self._pm_raise_auth_error(api_base)
            if response.ok:
                result = response.json()
                new_project_id = result.get("Id") or result.get("ProjectId")

                if new_project_id:
                    # Update the name of the duplicated project
                    patch_url = f"{api_base}/projects/{new_project_id}"
                    patch_payload = {"Name": new_project_name}
                    patch_response = requests.patch(
                        patch_url,
                        params=params,
                        json=patch_payload,
                        headers=headers,
                        verify=False,
                        timeout=10
                    )

                    if patch_response.status_code == 401:
                        self._pm_raise_auth_error(api_base)

                    if patch_response.status_code in (200, 204):
                        return str(new_project_id)
                    else:
                        # Duplication succeeded but name update failed - still return the ID
                        _logger.warning("Project duplicated but name update failed: %s", patch_response.text)
                        return str(new_project_id)
                else:
                    raise UserError(_('Duplication succeeded but no project ID returned'))
            else:
                error_msg = "Unknown error"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("ErrorMessage", error_msg)
                except:
                    error_msg = response.text or error_msg
                raise UserError(_('Failed to duplicate project: %s') % error_msg)
        except requests.exceptions.RequestException as e:
            raise UserError(_('Error connecting to Arkite API: %s') % str(e))

    def action_select_and_duplicate(self):
        """Selected a template, now duplicate directly"""
        self.ensure_one()
        raise UserError("Duplicate button executed (backend reached action_select_and_duplicate).")
        if not self.template_arkite_project_id:
            raise UserError(_('Please select a project to use as template.'))

        # Get project name
        project_name = self.new_project_name
        if not project_name:
            # Use Odoo project name as default
            odoo_project_id = self.env.context.get('active_id')
            if odoo_project_id:
                odoo_project = self.env['product_module.project'].browse(odoo_project_id)
                project_name = odoo_project.name
            else:
                raise UserError(_('Please enter a project name.'))

        # Check if project with same name already exists
        existing_id = self._get_project_id_by_name(project_name)
        if existing_id:
            # Update the record to show warning
            self.write({
                'new_project_name': project_name,
            })
            # Return warning action
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Warning: Project Already Exists'),
                    'message': _('A project with the name "%s" already exists in Arkite (ID: %s). Please use "Update Existing" to link to it, or change the project name.') % (project_name, existing_id),
                    'type': 'warning',
                    'sticky': True,
                }
            }

        # Duplicate the project
        template_arkite_id = self.template_arkite_project_id
        if not template_arkite_id:
            raise UserError(_('Template project ID is missing.'))

        try:
            project_id = self._duplicate_project(template_arkite_id, project_name)

            # Link to Odoo project OR create a new one when launched from the Dashboard.
            active_id = self.env.context.get('active_id')
            active_model = self.env.context.get('active_model')

            odoo_project = None
            if self.odoo_project_id:
                odoo_project = self.odoo_project_id
            elif active_model == 'product_module.project' and active_id:
                odoo_project = self.env['product_module.project'].browse(active_id)
            elif active_model == 'product_module.page' and active_id:
                # Dashboard flow: create a new Odoo Project under the current Page.
                create_vals = {
                    'name': project_name,
                    'page_id': active_id,
                }
                if self.arkite_unit_id:
                    create_vals['arkite_unit_id'] = self.arkite_unit_id.id
                odoo_project = self.env['product_module.project'].create(create_vals)
            else:
                raise UserError(_('Please select an Odoo Project (or use the Dashboard button next to "Add New Project").'))

            if odoo_project and odoo_project.exists():
                    # Get project name from Arkite
                    api_base, api_key = self._pm_get_arkite_api_credentials()
                    final_project_name = project_name
                    if api_base and api_key:
                        try:
                            url = f"{api_base}/projects/{project_id}"
                            params = {"apiKey": api_key}
                            headers = {"Content-Type": "application/json"}
                            response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)

                            if response.status_code == 401:
                                self._pm_raise_auth_error(api_base)
                            if response.ok:
                                proj_data = response.json()
                                final_project_name = proj_data.get("Name") or project_name
                        except Exception:
                            pass

                    odoo_project.write({
                        'arkite_project_id': str(project_id),
                        'arkite_project_name': final_project_name,
                    })

                    # Auto-load everything so the user immediately sees processes/steps/materials.
                    # This uses the Project's Arkite Unit credentials (enforced above).
                    odoo_project.action_load_arkite_project()
                    odoo_project.action_sync_from_arkite()

            # After duplication:
            # - Dashboard flow: open the newly created Project immediately (modal).
            # - Project flow: open the Project form.
            next_action = None
            if active_model == 'product_module.page' and active_id:
                next_action = {
                    'type': 'ir.actions.act_window',
                    'name': _('Project'),
                    'res_model': 'product_module.project',
                    'res_id': odoo_project.id,
                    'view_mode': 'form',
                    'views': [(self.env.ref('product_module.view_project_form').id, 'form')],
                    # Keep the dashboard behind it; user can close and see the new card later.
                    'target': 'new',
                    'context': dict(self.env.context, pm_project_modal=1),
                }
            else:
                next_action = {
                    'type': 'ir.actions.act_window',
                    'name': _('Project'),
                    'res_model': 'product_module.project',
                    'res_id': odoo_project.id,
                    'view_mode': 'form',
                    'views': [(self.env.ref('product_module.view_project_form').id, 'form')],
                    'target': 'current',
                    'context': dict(self.env.context),
                }

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Success'),
                    'message': _('Project "%s" duplicated and synced from Arkite.') % (project_name,),
                    'type': 'success',
                    'sticky': False,
                    'next': next_action,
                }
            }
        except UserError:
            raise
        except Exception as e:
            _logger.error("Error duplicating project: %s", e)
            raise UserError(_('Error duplicating project: %s') % str(e))

    def action_confirm_update_existing(self):
        """Confirm updating existing project instead of creating new"""
        self.ensure_one()

        project_name = self.new_project_name
        if not project_name:
            odoo_project_id = self.env.context.get('active_id')
            if odoo_project_id:
                odoo_project = self.env['product_module.project'].browse(odoo_project_id)
                project_name = odoo_project.name
            else:
                raise UserError(_('Please enter a project name.'))

        # Check if project exists
        existing_id = self._get_project_id_by_name(project_name)
        if not existing_id:
            raise UserError(_('Project with name "%s" not found. It may have been deleted.') % project_name)

        # Link to Odoo project
        odoo_project_id = self.env.context.get('active_id')
        if odoo_project_id:
            odoo_project = self.env['product_module.project'].browse(odoo_project_id)
            if odoo_project.exists():
                # Get project name from Arkite
                api_base, api_key = self._pm_get_arkite_api_credentials()
                final_project_name = project_name
                if api_base and api_key:
                    try:
                        url = f"{api_base}/projects/{existing_id}"
                        params = {"apiKey": api_key}
                        headers = {"Content-Type": "application/json"}
                        response = requests.get(url, params=params, headers=headers, verify=False, timeout=10)

                        if response.status_code == 401:
                            self._pm_raise_auth_error(api_base)
                        if response.ok:
                            proj_data = response.json()
                            final_project_name = proj_data.get("Name") or project_name
                    except Exception:
                        pass

                odoo_project.write({
                    'arkite_project_id': str(existing_id),
                    'arkite_project_name': final_project_name,
                })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('Linked to existing project "%s" (ID: %s)') % (final_project_name, existing_id),
                'type': 'success',
            }
        }

    def action_select_this_project(self):
        """Select this project from the list and link it immediately"""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_('No project ID found.'))

        # Get parent selection record
        parent = self.parent_id
        if not parent:
            raise UserError(_('No parent selection found.'))

        # Set the selected project on parent
        parent.write({
            'arkite_project_id': self.arkite_project_id,
            'arkite_project_name': self.arkite_project_name,
        })

        # Get the Odoo project to link (wizard field preferred, else context)
        odoo_project_id = (self.odoo_project_id.id or self.env.context.get('active_id'))
        if odoo_project_id:
            try:
                odoo_project = self.env['product_module.project'].browse(odoo_project_id)
                if odoo_project.exists():
                    # Link the project immediately
                    odoo_project.write({
                        'arkite_project_id': self.arkite_project_id,
                        'arkite_project_name': self.arkite_project_name or '',
                        # Linking != loading; require explicit load/sync after linking
                        'arkite_project_loaded': False,
                    })
                    # Do not navigate/reopen the project form from inside the wizard.
                    # Just close the modal; the user remains where they were.
                    return {'type': 'ir.actions.act_window_close'}
            except Exception as e:
                _logger.error("Error linking project: %s", e)

        # If we can't resolve the calling project, just close the modal (no navigation).
        return {'type': 'ir.actions.act_window_close'}

    def action_select_and_link(self):
        """Selected an Arkite project, now link it"""
        self.ensure_one()
        if not self.arkite_project_id:
            raise UserError(_('Please select a project. Click "Load Projects from Arkite" and then click "Select" on a project.'))

        # Get the Odoo project to link (wizard field preferred, else context)
        odoo_project_id = (self.odoo_project_id.id or self.env.context.get('active_id'))
        if not odoo_project_id:
            raise UserError(_('No project context found.'))

        odoo_project = self.env['product_module.project'].browse(odoo_project_id)

        # Link the project
        odoo_project.write({
            'arkite_project_id': self.arkite_project_id,
            'arkite_project_name': self.arkite_project_name or '',
            # Linking != loading; require explicit load/sync after linking
            'arkite_project_loaded': False,
        })

        # Do not navigate/reopen the project form from inside the wizard.
        # Just close the modal; the caller can refresh if needed.
        return {'type': 'ir.actions.act_window_close'}

    @api.depends('template_arkite_project_name', 'arkite_project_name', 'selection_type')
    def _compute_display_name(self):
        for record in self:
            try:
                if record.selection_type == 'template' and record.template_arkite_project_name:
                    record.display_name = record.template_arkite_project_name
                elif record.selection_type == 'project' and record.arkite_project_name:
                    record.display_name = record.arkite_project_name
                else:
                    record.display_name = 'Unknown'
            except Exception:
                record.display_name = 'Unknown'


class ArkiteProjectSelectionTemplate(models.TransientModel):
    """Temporary model for displaying available template projects"""
    _name = 'product_module.arkite.project.selection.template'
    _description = 'Available Template Project'
    _rec_name = 'project_name'

    selection_id = fields.Many2one(
        'product_module.arkite.project.selection',
        string='Selection',
        required=True,
        ondelete='cascade'
    )
    project_id = fields.Char(
        string='Arkite Project ID',
        required=True
    )
    project_name = fields.Char(
        string='Project Name',
        required=True
    )

    def action_select_template_project(self):
        """Select this template project - calls parent method"""
        self.ensure_one()
        if not self.selection_id:
            raise UserError(_('No parent selection found.'))

        # Pass the selected row id back to the parent wizard so it knows which project was picked.
        return self.selection_id.with_context(template_record_id=self.id).action_select_template_project()
