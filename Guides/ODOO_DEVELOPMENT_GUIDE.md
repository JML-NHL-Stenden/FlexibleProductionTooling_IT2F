# Complete Odoo Development Guide

## Table of Contents
1. [Odoo Architecture Overview](#odoo-architecture-overview)
2. [Module Structure](#module-structure)
3. [Models (Python)](#models-python)
4. [Views (XML)](#views-xml)
5. [Controllers (HTTP)](#controllers-http)
6. [Security & Access Control](#security--access-control)
7. [API Patterns](#api-patterns)
8. [Best Practices](#best-practices)
9. [Limitations & Constraints](#limitations--constraints)
10. [Common Pitfalls](#common-pitfalls)

---

## Odoo Architecture Overview

### Core Components

**Odoo** is a modular ERP system built on:
- **Python** for business logic (models, controllers)
- **PostgreSQL** for data storage
- **XML** for view definitions
- **JavaScript** (OWL framework) for frontend interactions
- **QWeb** templating engine for dynamic views

### Key Concepts

1. **Models (ORM)**: Python classes that represent database tables
2. **Views**: XML definitions that control UI rendering
3. **Controllers**: Handle HTTP requests for custom pages/APIs
4. **Records**: Database entries managed through models
5. **Inheritance**: Extend existing models/views without modifying core code

---

## Module Structure

### Standard Module Directory Layout

```
your_module/
├── __init__.py              # Module initialization
├── __manifest__.py          # Module metadata (dependencies, data files, etc.)
├── README.md                # Documentation
├── controllers/             # HTTP controllers
│   ├── __init__.py
│   └── main.py
├── models/                  # Python models (database tables)
│   ├── __init__.py
│   ├── model1.py
│   └── model2.py
├── views/                   # XML view definitions
│   ├── model1_views.xml
│   └── model2_views.xml
├── security/                # Access control
│   └── ir.model.access.csv
├── data/                    # Initial/default data
│   └── default_data.xml
├── static/                  # Static assets (CSS, JS, images)
│   └── src/
│       ├── css/
│       └── js/
└── wizards/                 # Transient models (dialogs)
    ├── __init__.py
    └── wizard.py
```

### __manifest__.py Structure

```python
{
    'name': 'Your Module Name',
    'version': '1.0',
    'summary': 'Brief description',
    'description': '''
        Detailed description
    ''',
    'author': 'Your Name',
    'category': 'Category',
    'license': 'LGPL-3',
    'depends': ['base', 'other_module'],  # Dependencies
    'data': [
        'security/ir.model.access.csv',
        'views/your_views.xml',
        'data/default_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'your_module/static/src/css/style.css',
            'your_module/static/src/js/script.js',
        ],
    },
    'installable': True,
    'application': True,  # Shows in Apps menu
}
```

---

## Models (Python)

### Basic Model Definition

```python
from odoo import models, fields, api, _
from odoo.exceptions import UserError

class YourModel(models.Model):
    _name = 'your_module.model_name'
    _description = 'Model Description'
    _order = 'name, id'  # Default ordering
    _rec_name = 'name'   # Field used for display
    
    # Field Definitions
    name = fields.Char(string='Name', required=True, size=100)
    active = fields.Boolean(string='Active', default=True)
    sequence = fields.Integer(string='Sequence', default=10)
```

### Field Types

#### Basic Fields

```python
# Text Fields
name = fields.Char(string='Name', required=True, size=100)
description = fields.Text(string='Description')
html_content = fields.Html(string='HTML Content')

# Numeric Fields
quantity = fields.Integer(string='Quantity', default=0)
price = fields.Float(string='Price', digits=(16, 2))
percentage = fields.Float(string='Percentage', digits=(16, 4))

# Boolean
is_active = fields.Boolean(string='Active', default=True)

# Date/Time
date_field = fields.Date(string='Date')
datetime_field = fields.Datetime(string='Date Time')
```

#### Selection Fields

```python
state = fields.Selection([
    ('draft', 'Draft'),
    ('confirmed', 'Confirmed'),
    ('done', 'Done'),
], string='State', default='draft', required=True)
```

#### Binary Fields (Files/Images)

```python
image = fields.Binary(string='Image', attachment=True)
document = fields.Binary(string='Document', attachment=True)
filename = fields.Char(string='Filename')
```

#### Relationship Fields

```python
# Many2one (Foreign Key)
partner_id = fields.Many2one('res.partner', string='Partner', required=True, ondelete='cascade')
category_id = fields.Many2one('your_module.category', string='Category', ondelete='set null')

# One2many (Reverse of Many2one)
line_ids = fields.One2many('your_module.line', 'parent_id', string='Lines')

# Many2many (Many-to-Many)
tag_ids = fields.Many2many('your_module.tag', string='Tags')
product_ids = fields.Many2many(
    'product.product',
    'rel_table_name',      # Relation table name
    'column1',            # Column 1 name
    'column2',            # Column 2 name
    string='Products'
)
```

#### Computed Fields

```python
total_amount = fields.Float(string='Total', compute='_compute_total', store=True)
full_name = fields.Char(string='Full Name', compute='_compute_full_name', store=False)

@api.depends('line_ids', 'line_ids.amount')
def _compute_total(self):
    for record in self:
        record.total_amount = sum(record.line_ids.mapped('amount'))

@api.depends('first_name', 'last_name')
def _compute_full_name(self):
    for record in self:
        record.full_name = f"{record.first_name} {record.last_name}"
```

#### Related Fields

```python
partner_name = fields.Char(related='partner_id.name', string='Partner Name', store=True)
partner_email = fields.Char(related='partner_id.email', readonly=True)
```

### Model Attributes

```python
class YourModel(models.Model):
    _name = 'your_module.model'
    _description = 'Description'
    _order = 'sequence, name'  # SQL ORDER BY
    _rec_name = 'name'         # Field for name_get()
    _inherit = ['mail.thread', 'mail.activity.mixin']  # Mixins
    _check_company_auto = True  # Auto-check company consistency
```

### CRUD Operations

```python
# Create
record = self.env['your_module.model'].create({
    'name': 'New Record',
    'field1': 'value1',
})

# Read
records = self.env['your_module.model'].search([('field', '=', 'value')])
record = self.env['your_module.model'].browse(1)
record.name  # Access field

# Update
record.write({'name': 'Updated Name'})
records.write({'field': 'value'})  # Bulk update

# Delete
record.unlink()
records.unlink()  # Bulk delete
```

### Search & Filtering

```python
# Search with domain
records = self.env['your_module.model'].search([
    ('name', '=', 'value'),           # Exact match
    ('name', '!=', 'value'),          # Not equal
    ('name', 'ilike', '%value%'),     # Case-insensitive like
    ('name', 'like', '%value%'),      # Case-sensitive like
    ('quantity', '>', 10),            # Greater than
    ('quantity', '>=', 10),           # Greater or equal
    ('quantity', '<', 100),           # Less than
    ('quantity', '<=', 100),          # Less or equal
    ('state', 'in', ['draft', 'done']), # In list
    ('state', 'not in', ['cancelled']), # Not in list
    ('date', '>=', fields.Date.today()), # Date comparison
    '|',  # OR operator
    ('field1', '=', 'value1'),
    ('field2', '=', 'value2'),
    '&',  # AND operator (default)
])

# Search with limit and order
records = self.env['your_module.model'].search(
    [('active', '=', True)],
    limit=10,
    order='name desc',
    offset=0
)

# Search count
count = self.env['your_module.model'].search_count([('active', '=', True)])

# Search read (returns dicts)
records = self.env['your_module.model'].search_read(
    [('active', '=', True)],
    ['name', 'field1', 'field2'],
    limit=10
)
```

### Constraints

```python
from odoo.exceptions import ValidationError

@api.constrains('field1', 'field2')
def _check_constraint(self):
    for record in self:
        if record.field1 and record.field2:
            if record.field1 > record.field2:
                raise ValidationError(_('Field1 cannot be greater than Field2'))

@api.constrains('name')
def _check_name(self):
    for record in self:
        if len(record.name) > 100:
            raise ValidationError(_('Name cannot exceed 100 characters'))
```

### Model Methods

```python
# Standard Methods
def name_get(self):
    """Custom display name"""
    result = []
    for record in self:
        name = f"{record.name} ({record.code})"
        result.append((record.id, name))
    return result

@api.model
def name_search(self, name='', args=None, operator='ilike', limit=100):
    """Custom search"""
    args = args or []
    if name:
        args = ['|', ('name', operator, name), ('code', operator, name)] + args
    return self.search(args, limit=limit).name_get()

# Action Methods (return actions)
def action_do_something(self):
    self.ensure_one()  # Ensure only one record
    return {
        'type': 'ir.actions.act_window',
        'name': 'Window Title',
        'res_model': 'your_module.model',
        'view_mode': 'form',
        'res_id': self.id,
        'target': 'new',  # or 'current'
    }

def action_open_related(self):
    return {
        'type': 'ir.actions.act_window',
        'name': 'Related Records',
        'res_model': 'related.model',
        'view_mode': 'tree,form',
        'domain': [('parent_id', '=', self.id)],
    }
```

### Transient Models (Wizards)

```python
class YourWizard(models.TransientModel):
    _name = 'your_module.wizard'
    _description = 'Wizard Description'
    
    field1 = fields.Char(string='Field 1')
    field2 = fields.Many2one('res.partner', string='Partner')
    
    def action_confirm(self):
        # Process wizard data
        self.ensure_one()
        # Do something
        return {'type': 'ir.actions.act_window_close'}
```

### API Decorators

```python
@api.model
def method_for_model(self):
    """Called on model, not on recordset"""
    pass

@api.multi  # Deprecated, use api.model or no decorator
def method_for_records(self):
    """Called on recordset (one or more records)"""
    pass

@api.one  # Deprecated
def method_for_one_record(self):
    """Called for each record in recordset"""
    pass

@api.depends('field1', 'field2')
def _compute_field(self):
    """Recompute when dependencies change"""
    pass

@api.onchange('field1')
def _onchange_field1(self):
    """Triggered when field1 changes in form"""
    if self.field1:
        self.field2 = self.field1 * 2
        return {'warning': {'title': 'Warning', 'message': 'Field2 updated'}}

@api.constrains('field1')
def _check_field1(self):
    """Validation constraint"""
    pass

@api.model_create_multi
def create(self, vals_list):
    """Optimized create for multiple records"""
    return super().create(vals_list)
```

---

## Views (XML)

### View Types

#### Form View

```xml
<record id="view_model_form" model="ir.ui.view">
    <field name="name">your.module.form</field>
    <field name="model">your_module.model</field>
    <field name="arch" type="xml">
        <form string="Model Form">
            <header>
                <button name="action_confirm" type="object" string="Confirm" class="btn-primary"/>
                <field name="state" widget="statusbar"/>
            </header>
            <sheet>
                <group>
                    <group>
                        <field name="name"/>
                        <field name="code"/>
                    </group>
                    <group>
                        <field name="date"/>
                        <field name="partner_id"/>
                    </group>
                </group>
                <notebook>
                    <page string="Details">
                        <field name="description"/>
                    </page>
                    <page string="Lines">
                        <field name="line_ids">
                            <tree editable="bottom">
                                <field name="product_id"/>
                                <field name="quantity"/>
                                <field name="price"/>
                            </tree>
                        </field>
                    </page>
                </notebook>
            </sheet>
            <chatter/>
        </form>
    </field>
</record>
```

#### List/Tree View

```xml
<record id="view_model_list" model="ir.ui.view">
    <field name="name">your.module.list</field>
    <field name="model">your_module.model</field>
    <field name="arch" type="xml">
        <tree string="Records" decoration-info="state=='draft'" decoration-success="state=='done'">
            <field name="sequence" widget="handle"/>
            <field name="name"/>
            <field name="code"/>
            <field name="partner_id"/>
            <field name="amount_total" sum="Total"/>
            <field name="state" widget="badge" decoration-info="state=='draft'"/>
        </tree>
    </field>
</record>
```

#### Kanban View

```xml
<record id="view_model_kanban" model="ir.ui.view">
    <field name="name">your.module.kanban</field>
    <field name="model">your_module.model</field>
    <field name="arch" type="xml">
        <kanban default_group_by="state" class="o_kanban_small_column">
            <field name="name"/>
            <field name="state"/>
            <field name="partner_id"/>
            <templates>
                <t t-name="kanban-box">
                    <div class="oe_kanban_card">
                        <div class="oe_kanban_content">
                            <strong><field name="name"/></strong>
                            <div><field name="partner_id"/></div>
                        </div>
                    </div>
                </t>
            </templates>
        </kanban>
    </field>
</record>
```

#### Search View

```xml
<record id="view_model_search" model="ir.ui.view">
    <field name="name">your.module.search</field>
    <field name="model">your_module.model</field>
    <field name="arch" type="xml">
        <search string="Search Records">
            <field name="name" string="Name"/>
            <field name="code" string="Code"/>
            <field name="partner_id" string="Partner"/>
            <filter string="Active" name="active" domain="[('active', '=', True)]"/>
            <filter string="Draft" name="draft" domain="[('state', '=', 'draft')]"/>
            <separator/>
            <filter string="My Records" name="my_records" domain="[('user_id', '=', uid)]"/>
            <group expand="0" string="Group By">
                <filter string="State" name="group_state" context="{'group_by': 'state'}"/>
                <filter string="Partner" name="group_partner" context="{'group_by': 'partner_id'}"/>
            </group>
        </search>
    </field>
</record>
```

### View Inheritance

```xml
<!-- Inherit existing view -->
<record id="base_view_inherit" model="ir.ui.view">
    <field name="name">base.view.inherit</field>
    <field name="model">base.model</field>
    <field name="inherit_id" ref="base_module.view_base_form"/>
    <field name="arch" type="xml">
        <!-- Add field after existing field -->
        <field name="existing_field" position="after">
            <field name="new_field"/>
        </field>
        
        <!-- Replace field -->
        <field name="old_field" position="replace">
            <field name="new_field"/>
        </field>
        
        <!-- Add field inside group -->
        <group name="group_name" position="inside">
            <field name="new_field"/>
        </group>
        
        <!-- Add button in header -->
        <header position="inside">
            <button name="action_new" type="object" string="New Action"/>
        </header>
    </field>
</record>
```

### Actions

```xml
<record id="action_model" model="ir.actions.act_window">
    <field name="name">Your Model</field>
    <field name="res_model">your_module.model</field>
    <field name="view_mode">tree,form,kanban</field>
    <field name="view_id" ref="view_model_list"/>
    <field name="search_view_id" ref="view_model_search"/>
    <field name="domain">[('active', '=', True)]</field>
    <field name="context">{'default_field': value}</field>
    <field name="limit">80</field>
</record>
```

### Menus

```xml
<menuitem id="menu_root"
          name="Your Module"
          sequence="10"/>

<menuitem id="menu_model"
          name="Records"
          parent="menu_root"
          action="action_model"
          sequence="10"/>
```

---

## Controllers (HTTP)

### Basic Controller

```python
from odoo import http
from odoo.http import request

class YourController(http.Controller):
    
    @http.route('/your_module/page', type='http', auth='public', website=True)
    def your_page(self, **kw):
        return request.render('your_module.template', {
            'data': 'value',
        })
    
    @http.route('/your_module/api', type='json', auth='user')
    def your_api(self, **kw):
        return {'status': 'success', 'data': 'value'}
    
    @http.route('/your_module/data', type='http', auth='user', methods=['POST'])
    def your_data(self, **kw):
        # Process POST data
        return request.make_response('OK', headers=[('Content-Type', 'text/plain')])
```

### Route Types

- `type='http'`: Standard HTTP request/response
- `type='json'`: JSON-RPC request/response
- `auth='public'`: No authentication required
- `auth='user'`: Requires logged-in user
- `auth='none'`: No authentication, no session
- `website=True`: Available on website (public frontend)

---

## Security & Access Control

### Access Rights (ir.model.access.csv)

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_model_user,model.user,model_your_module_model,base.group_user,1,1,1,1
access_model_manager,model.manager,model_your_module_model,base.group_system,1,1,1,1
```

### Record Rules (security/ir.rule.xml)

```xml
<record id="model_user_rule" model="ir.rule">
    <field name="name">User: Own Records Only</field>
    <field name="model_id" ref="model_your_module_model"/>
    <field name="domain_force">[('user_id', '=', user.id)]</field>
    <field name="groups" eval="[(4, ref('base.group_user'))]"/>
</record>
```

---

## API Patterns

### XML-RPC API

```python
import xmlrpc.client

url = 'http://localhost:8069'
db = 'your_database'
username = 'admin'
password = 'admin'

common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
uid = common.authenticate(db, username, password, {})

models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
result = models.execute_kw(
    db, uid, password,
    'your_module.model', 'search_read',
    [[('active', '=', True)]],
    {'fields': ['name', 'code'], 'limit': 10}
)
```

### JSON-RPC API

```python
import requests
import json

url = 'http://localhost:8069/jsonrpc'
headers = {'Content-Type': 'application/json'}

# Login
data = {
    'jsonrpc': '2.0',
    'method': 'call',
    'params': {
        'db': 'your_database',
        'login': 'admin',
        'password': 'admin',
    },
    'id': 1,
}
response = requests.post(f'{url}/web/session/authenticate', headers=headers, json=data)
session_id = response.cookies.get('session_id')

# Search records
data = {
    'jsonrpc': '2.0',
    'method': 'call',
    'params': {
        'model': 'your_module.model',
        'method': 'search_read',
        'args': [[('active', '=', True)]],
        'kwargs': {'fields': ['name', 'code'], 'limit': 10},
    },
    'id': 2,
}
response = requests.post(f'{url}/web/dataset/call_kw', headers=headers, json=data, cookies={'session_id': session_id})
```

---

## Best Practices

### 1. Module Development

✅ **DO:**
- Create standalone modules, don't modify core files
- Use inheritance instead of overrides
- Follow Odoo naming conventions
- Document your code
- Write tests for critical functionality
- Use proper access rights

❌ **DON'T:**
- Modify core Odoo modules directly
- Create circular dependencies
- Hardcode values that should be configurable
- Ignore security rules
- Create overly complex customizations

### 2. Performance

✅ **DO:**
- Use `read_group` for aggregations
- Use `search_read` instead of `search` + `read`
- Use `prefetch` for related records
- Index frequently searched fields
- Batch operations when possible
- Use `store=True` for frequently accessed computed fields

❌ **DON'T:**
- Use `for` loops for database queries
- Load unnecessary data
- Create N+1 query problems
- Compute fields unnecessarily
- Store large binary data in database

### 3. Code Quality

✅ **DO:**
- Use meaningful variable names
- Follow PEP 8 style guide
- Add docstrings to methods
- Handle exceptions properly
- Use `_()` for translatable strings
- Validate user input

❌ **DON'T:**
- Use magic numbers/strings
- Ignore error handling
- Create overly long methods
- Duplicate code
- Hardcode business logic

### 4. Database

✅ **DO:**
- Use proper field types
- Add constraints for data integrity
- Use `ondelete` appropriately
- Clean up orphaned records
- Regular database maintenance

❌ **DON'T:**
- Store computed data unnecessarily
- Create too many indexes
- Ignore foreign key constraints
- Store sensitive data unencrypted

---

## Limitations & Constraints

### 1. Performance Limitations

**Large Datasets:**
- Odoo can struggle with very large datasets (millions of records)
- Complex queries with many joins can be slow
- Real-time operations on large record sets may timeout

**Solutions:**
- Implement pagination
- Use background jobs for heavy operations
- Optimize database queries
- Consider read replicas for reporting

### 2. Scalability Constraints

**Monolithic Architecture:**
- Difficult to scale individual components
- One module's load affects entire system
- Vertical scaling often required

**Solutions:**
- Use load balancers
- Implement caching strategies
- Use background workers
- Consider microservices for heavy operations

### 3. Customization Limits

**Upgrade Challenges:**
- Major version upgrades may break customizations
- Extensive customizations complicate maintenance
- Third-party modules may conflict

**Solutions:**
- Minimize customizations
- Use inheritance properly
- Test upgrades in staging
- Keep custom code documented

### 4. API Limitations

**REST API:**
- Limited compared to custom APIs
- May not support all use cases
- Rate limiting on Odoo.sh

**Solutions:**
- Use XML-RPC/JSON-RPC for complex operations
- Create custom controllers for specific needs
- Implement proper error handling

### 5. Field Type Constraints

**Text Fields:**
- `Char` fields have size limits (typically 256 chars)
- `Text` fields can be large but may impact performance
- Binary fields should use attachments

**Solutions:**
- Use appropriate field types
- Store large files as attachments
- Consider external storage for very large files

### 6. Transaction Limitations

**Database Transactions:**
- Long-running transactions can lock tables
- Computed fields recalculate on every write
- Cascading operations can be slow

**Solutions:**
- Keep transactions short
- Use `@api.depends` efficiently
- Batch operations when possible
- Use `sudo()` carefully (bypasses security)

### 7. View Limitations

**Complex Views:**
- Very complex views can be slow to render
- Many nested groups impact performance
- Large kanban views may lag

**Solutions:**
- Simplify view structures
- Use pagination
- Limit visible fields
- Optimize QWeb templates

### 8. Multi-Company Limitations

**Company Isolation:**
- Must explicitly handle multi-company scenarios
- Some operations don't respect company boundaries
- Data leakage risks if not configured properly

**Solutions:**
- Use `_check_company_auto = True`
- Set `company_id` fields properly
- Test multi-company scenarios

### 9. Localization Constraints

**Internationalization:**
- Some features may not work in all locales
- Date/time formatting varies
- Currency handling can be complex

**Solutions:**
- Test in target locales
- Use Odoo's localization features
- Handle timezone conversions properly

### 10. Integration Challenges

**Third-Party Systems:**
- Complex integrations may require custom development
- API rate limits
- Data synchronization challenges

**Solutions:**
- Use Odoo's built-in connectors
- Implement proper error handling
- Use message queues for async operations
- Document integration points

---

## Common Pitfalls

### 1. Over-Customization
**Problem:** Too many customizations make upgrades difficult
**Solution:** Use standard Odoo features when possible, customize only when necessary

### 2. N+1 Query Problem
**Problem:** Looping through records and accessing related data
```python
# BAD
for record in records:
    print(record.partner_id.name)  # One query per record

# GOOD
records.read(['partner_id'])  # Prefetch related data
for record in records:
    print(record.partner_id.name)
```

### 3. Missing Access Rights
**Problem:** Forgetting to define access rights
**Solution:** Always define `ir.model.access.csv` for new models

### 4. Incorrect Field Types
**Problem:** Using wrong field types (e.g., Char instead of Text)
**Solution:** Understand field type limitations and use appropriately

### 5. Not Handling Exceptions
**Problem:** Code crashes without proper error messages
**Solution:** Use try/except and raise UserError/ValidationError

### 6. Computed Fields Without Dependencies
**Problem:** Computed fields not updating when they should
**Solution:** Always use `@api.depends` with all relevant fields

### 7. Hardcoding Values
**Problem:** Business logic values hardcoded in code
**Solution:** Use configuration fields or system parameters

### 8. Ignoring Security
**Problem:** Using `sudo()` unnecessarily, bypassing security
**Solution:** Only use `sudo()` when absolutely necessary, document why

### 9. Not Testing Upgrades
**Problem:** Customizations break after Odoo upgrades
**Solution:** Test upgrades in staging environment first

### 10. Poor Database Design
**Problem:** Inefficient relationships, missing indexes
**Solution:** Plan database structure, add indexes for frequently searched fields

---

## Additional Resources

### Official Documentation
- Odoo Developer Documentation: https://www.odoo.com/documentation/
- Odoo API Reference: https://www.odoo.com/documentation/16.0/developer/reference/backend/orm.html

### Community Resources
- Odoo Community Forum: https://www.odoo.com/forum
- Odoo GitHub: https://github.com/odoo/odoo

### Learning Path
1. Start with basic models and views
2. Learn inheritance patterns
3. Understand security and access control
4. Master API patterns
5. Study performance optimization
6. Learn advanced topics (workflows, reports, etc.)

---

## Summary

Odoo is a powerful ERP framework, but requires understanding of:
- **Python ORM patterns** for models
- **XML view definitions** for UI
- **Security models** for access control
- **Performance optimization** for scalability
- **Best practices** for maintainability

Key takeaways:
- Always use inheritance over modification
- Follow Odoo conventions
- Test thoroughly
- Document your code
- Plan for upgrades
- Optimize for performance
- Respect security models

This guide should serve as a comprehensive reference for Odoo development. Refer to specific sections as needed during development.
