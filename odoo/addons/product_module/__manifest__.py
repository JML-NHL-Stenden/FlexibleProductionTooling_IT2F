{
    'name': 'Product Module',
    'version': '1.0',
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
        'views/product_views.xml',
        'views/component_views.xml',
        'views/progress_views.xml',
        'views/arkite_project_wizard_view.xml',
        'views/arkite_job_step_wizard_view.xml',
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