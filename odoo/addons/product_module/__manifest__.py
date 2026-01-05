{
    'name': 'Product Module',
    'version': '1.1',
    'summary': 'Product registration with QR codes and assembly instructions',
    'description': '''
        Product Assembly Management Module
        ===================================
        
        Features:
        ---------
        * Register products with name, ID, variant, and optional photo
        * Automatic QR code generation based on product ID
        * Manage assembly instructions for each product
        * List view with QR codes and instruction tracking
        * Step-by-step assembly instructions with images
    ''',
    'author': 'II- F Information Technology (NHL Stenden)',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/page_data.xml',
        'views/instruction_import_wizard_view.xml',
        'views/instruction_form_wizard_views.xml',
        'views/product_views.xml',  # Load first to define menu_product_module_root (but menu items referencing actions from other files should be in those files)
        'views/arkite_unit_views.xml',  # Load after product_views.xml (needs menu_product_module_root), defines action_arkite_unit
        'views/project_views.xml',  # Load after arkite_unit_views.xml (needs action_arkite_unit), defines action_project
        'views/variant_views.xml',
        'views/material_views.xml',
        'views/material_link_wizard_views.xml',
        'views/progress_views.xml',
        'views/arkite_project_wizard_view.xml',
        'views/arkite_job_step_wizard_view.xml',
        'views/arkite_project_selection_views.xml',
        'data/arkite_security_data.xml',
        'views/test_menu_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'product_module/static/src/css/product_module.css',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
}