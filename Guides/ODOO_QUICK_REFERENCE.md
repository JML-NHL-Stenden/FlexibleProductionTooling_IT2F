# Odoo Quick Reference Cheat Sheet

## Model Field Types Quick Reference

```python
# Text
fields.Char(string='Name', required=True, size=100)
fields.Text(string='Description')
fields.Html(string='Content')

# Numbers
fields.Integer(string='Quantity', default=0)
fields.Float(string='Price', digits=(16, 2))
fields.Monetary(string='Amount', currency_field='currency_id')

# Boolean & Selection
fields.Boolean(string='Active', default=True)
fields.Selection([('val1', 'Label1'), ('val2', 'Label2')], string='State')

# Dates
fields.Date(string='Date')
fields.Datetime(string='Date Time')

# Binary
fields.Binary(string='File', attachment=True)
fields.Binary(string='Image', attachment=True)

# Relationships
fields.Many2one('res.partner', string='Partner', ondelete='cascade')
fields.One2many('model.line', 'parent_id', string='Lines')
fields.Many2many('model.tag', string='Tags')

# Computed
fields.Char(compute='_compute_field', store=True)
fields.Float(compute='_compute_total', store=True)

# Related
fields.Char(related='partner_id.name', string='Partner Name')
```

## Common Domain Operators

```python
# Comparison
('field', '=', value)        # Equal
('field', '!=', value)       # Not equal
('field', '>', value)        # Greater than
('field', '>=', value)        # Greater or equal
('field', '<', value)         # Less than
('field', '<=', value)        # Less or equal

# Text
('field', 'like', '%value%')      # Case-sensitive like
('field', 'ilike', '%value%')     # Case-insensitive like
('field', '=like', 'pattern%')    # SQL LIKE pattern

# Lists
('field', 'in', [val1, val2])     # In list
('field', 'not in', [val1, val2]) # Not in list

# Null checks
('field', '=', False)        # Is null/empty
('field', '!=', False)       # Is not null/empty

# Logical operators
['&', (cond1), (cond2)]      # AND
['|', (cond1), (cond2)]      # OR
['!', (cond)]                # NOT
```

## Common API Decorators

```python
@api.model                    # Model-level method
@api.multi                    # Recordset method (deprecated, use no decorator)
@api.depends('field1', 'field2')  # Computed field dependencies
@api.onchange('field1')      # Form field change handler
@api.constrains('field1')     # Validation constraint
@api.model_create_multi       # Optimized multi-create
```

## Search Patterns

```python
# Basic search
records = self.env['model'].search([('field', '=', 'value')])

# Search with limit and order
records = self.env['model'].search(
    [('active', '=', True)],
    limit=10,
    order='name desc',
    offset=0
)

# Search count
count = self.env['model'].search_count([('active', '=', True)])

# Search read (returns dicts)
records = self.env['model'].search_read(
    [('active', '=', True)],
    ['name', 'field1'],
    limit=10
)

# Browse by ID
record = self.env['model'].browse(1)
records = self.env['model'].browse([1, 2, 3])
```

## CRUD Operations

```python
# Create
record = self.env['model'].create({'name': 'New', 'field': 'value'})
records = self.env['model'].create([
    {'name': 'Record 1'},
    {'name': 'Record 2'},
])

# Read
record.name                   # Access field
record.read(['name', 'field']) # Read specific fields
records.mapped('name')        # Get list of field values
records.filtered(lambda r: r.active)  # Filter recordset

# Update
record.write({'name': 'Updated'})
records.write({'field': 'value'})  # Bulk update

# Delete
record.unlink()
records.unlink()  # Bulk delete
```

## Action Return Patterns

```python
# Open form view
return {
    'type': 'ir.actions.act_window',
    'name': 'Title',
    'res_model': 'model',
    'view_mode': 'form',
    'res_id': self.id,
    'target': 'new',  # or 'current'
}

# Open list view
return {
    'type': 'ir.actions.act_window',
    'name': 'Records',
    'res_model': 'model',
    'view_mode': 'tree,form',
    'domain': [('field', '=', value)],
    'context': {'default_field': value},
}

# Download file
return {
    'type': 'ir.actions.act_url',
    'url': f'/web/content/{attachment.id}?download=true',
    'target': 'self',
}

# Show notification
return {
    'type': 'ir.actions.client',
    'tag': 'display_notification',
    'params': {
        'title': 'Success',
        'message': 'Operation completed',
        'type': 'success',
        'sticky': False,
    }
}

# Reload view
return {
    'type': 'ir.actions.client',
    'tag': 'reload',
}
```

## View XML Patterns

### Form View Structure
```xml
<form>
    <header>
        <button name="action" type="object" string="Action"/>
        <field name="state" widget="statusbar"/>
    </header>
    <sheet>
        <group>
            <group>
                <field name="field1"/>
            </group>
            <group>
                <field name="field2"/>
            </group>
        </group>
        <notebook>
            <page string="Tab">
                <field name="field3"/>
            </page>
        </notebook>
    </sheet>
    <chatter/>
</form>
```

### Tree View
```xml
<tree string="Records" decoration-info="state=='draft'">
    <field name="sequence" widget="handle"/>
    <field name="name"/>
    <field name="amount" sum="Total"/>
</tree>
```

### Kanban View
```xml
<kanban default_group_by="state">
    <field name="name"/>
    <field name="state"/>
    <templates>
        <t t-name="kanban-box">
            <div class="oe_kanban_card">
                <strong><field name="name"/></strong>
            </div>
        </t>
    </templates>
</kanban>
```

### Search View
```xml
<search>
    <field name="name"/>
    <filter string="Active" name="active" domain="[('active', '=', True)]"/>
    <group expand="0" string="Group By">
        <filter name="group_state" context="{'group_by': 'state'}"/>
    </group>
</search>
```

## View Inheritance Patterns

```xml
<!-- Add field after existing -->
<field name="existing_field" position="after">
    <field name="new_field"/>
</field>

<!-- Replace field -->
<field name="old_field" position="replace">
    <field name="new_field"/>
</field>

<!-- Add inside group -->
<group name="group_name" position="inside">
    <field name="new_field"/>
</group>

<!-- Add button -->
<header position="inside">
    <button name="action_new" type="object" string="New"/>
</header>
```

## Common Exceptions

```python
from odoo.exceptions import UserError, ValidationError, AccessError

# User-friendly error
raise UserError(_('Operation failed: %s') % reason)

# Validation error
raise ValidationError(_('Invalid value: %s') % value)

# Access error (usually automatic)
raise AccessError(_('You cannot access this record'))
```

## Security Patterns

### Access Rights (ir.model.access.csv)
```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_model_user,model.user,model_your_module_model,base.group_user,1,1,1,1
```

### Record Rules (security/ir.rule.xml)
```xml
<record id="model_rule" model="ir.rule">
    <field name="name">User: Own Records</field>
    <field name="model_id" ref="model_your_module_model"/>
    <field name="domain_force">[('user_id', '=', user.id)]</field>
    <field name="groups" eval="[(4, ref('base.group_user'))]"/>
</record>
```

## Controller Patterns

```python
from odoo import http
from odoo.http import request

# HTTP route
@http.route('/path', type='http', auth='user', website=True)
def handler(self, **kw):
    return request.render('module.template', {'data': value})

# JSON route
@http.route('/api', type='json', auth='user')
def api_handler(self, **kw):
    return {'status': 'success', 'data': value}
```

## Computed Field Patterns

```python
# Simple computed
@api.depends('field1', 'field2')
def _compute_total(self):
    for record in self:
        record.total = record.field1 + record.field2

# Computed with related records
@api.depends('line_ids', 'line_ids.amount')
def _compute_total(self):
    for record in self:
        record.total = sum(record.line_ids.mapped('amount'))

# Computed with conditions
@api.depends('state')
def _compute_can_edit(self):
    for record in self:
        record.can_edit = record.state == 'draft'
```

## Onchange Patterns

```python
@api.onchange('field1')
def _onchange_field1(self):
    if self.field1:
        self.field2 = self.field1 * 2
        return {
            'warning': {
                'title': 'Warning',
                'message': 'Field2 was updated'
            }
        }
```

## Constraint Patterns

```python
@api.constrains('field1', 'field2')
def _check_fields(self):
    for record in self:
        if record.field1 and record.field2:
            if record.field1 > record.field2:
                raise ValidationError(_('Field1 cannot be greater than Field2'))
```

## Common Widgets

```xml
<!-- Status bar -->
<field name="state" widget="statusbar"/>

<!-- Image -->
<field name="image" widget="image" options="{'size': [100, 100]}"/>

<!-- Many2many tags -->
<field name="tag_ids" widget="many2many_tags"/>

<!-- Handle (drag) -->
<field name="sequence" widget="handle"/>

<!-- Badge -->
<field name="state" widget="badge" decoration-info="state=='draft'"/>

<!-- Monetary -->
<field name="amount" widget="monetary"/>

<!-- Date -->
<field name="date" widget="date"/>

<!-- Datetime -->
<field name="datetime" widget="datetime"/>
```

## Performance Tips

```python
# Use read_group for aggregations
self.env['model'].read_group(
    [('active', '=', True)],
    ['field1', 'field2:sum'],
    ['field1']
)

# Prefetch related data
records.read(['partner_id', 'category_id'])
for record in records:
    print(record.partner_id.name)  # No extra query

# Use search_read instead of search + read
records = self.env['model'].search_read(
    [('active', '=', True)],
    ['name', 'field1']
)

# Batch operations
self.env['model'].create([{...}, {...}])  # Better than loop
records.write({'field': 'value'})  # Bulk update
```

## Common Context Usage

```python
# Set default values
'context': {'default_field': value}

# Set domain
'context': {'default_field': value, 'search_default_field': value}

# Group by
'context': {'group_by': 'field'}

# Active ID
'context': {'default_parent_id': active_id}

# Active IDs
'context': {'active_ids': active_ids}
```

## Translation Pattern

```python
from odoo import _

# Translatable string
message = _('Hello World')

# With parameters
message = _('Hello %s') % name

# Plural forms
message = _('%(count)d item(s)') % {'count': count}
```

## Useful Environment Methods

```python
# Get current user
self.env.user
self.env.user.id

# Get current company
self.env.company
self.env.companies  # Multi-company

# Get language
self.env.lang

# Get context
self.env.context

# With context
self.env['model'].with_context(key=value).search([])

# With user
self.env['model'].sudo(user).search([])

# Clear cache
self.env.clear()
```

## Date/Time Helpers

```python
from odoo import fields

# Current date
fields.Date.today()

# Current datetime
fields.Datetime.now()

# Date operations
from datetime import timedelta
date = fields.Date.today() + timedelta(days=7)

# Format date
record.date.strftime('%Y-%m-%d')
```

## File Handling

```python
import base64
from io import BytesIO

# Encode file
with open('file.pdf', 'rb') as f:
    file_data = base64.b64encode(f.read())

# Decode file
file_bytes = base64.b64decode(record.file_field)

# Create attachment
attachment = self.env['ir.attachment'].create({
    'name': 'filename.pdf',
    'type': 'binary',
    'datas': file_data,
    'res_model': self._name,
    'res_id': self.id,
    'mimetype': 'application/pdf'
})
```

## Debugging Tips

```python
# Logging
import logging
_logger = logging.getLogger(__name__)
_logger.info('Message: %s', value)
_logger.warning('Warning: %s', value)
_logger.error('Error: %s', value)

# Debug mode
import pdb; pdb.set_trace()  # Python debugger

# Print recordset
print(self.env['model'].search([]))

# Check SQL query
self.env['model'].search([])._where_calc([])
```

---

## Quick Model Template

```python
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class YourModel(models.Model):
    _name = 'your_module.model'
    _description = 'Model Description'
    _order = 'name, id'
    
    name = fields.Char(string='Name', required=True)
    active = fields.Boolean(string='Active', default=True)
    
    @api.depends('field1')
    def _compute_field2(self):
        for record in self:
            record.field2 = record.field1 * 2
    
    @api.constrains('field1')
    def _check_field1(self):
        for record in self:
            if record.field1 < 0:
                raise ValidationError(_('Field1 must be positive'))
    
    def action_do_something(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Title',
            'res_model': 'model',
            'view_mode': 'form',
            'res_id': self.id,
        }
```

---

This quick reference covers the most common patterns you'll use in Odoo development. Keep it handy while coding!
