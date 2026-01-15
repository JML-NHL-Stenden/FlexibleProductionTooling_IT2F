{
    'name': 'Product Module',
    'version': '1.2',
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
    'depends': ['base', 'web', 'web_hierarchy'],
    'data': [
        'security/ir.model.access.csv',
        'data/page_data.xml',
        'views/instruction_import_wizard_view.xml',
        'views/instruction_form_wizard_views.xml',
        # NOTE: ordering matters:
        # - the wizard view must exist before the action can reference it
        # - the action XMLID must exist before product_views.xml references it via %(...)d
        'views/arkite_project_selection_views.xml',
        'views/arkite_duplicate_menu.xml',
        'views/product_views.xml',  # Defines menu_product_module_root used by many later view files
        'views/arkite_unit_views.xml',  # Load after product_views.xml (needs menu_product_module_root), defines action_arkite_unit
        'views/project_views.xml',  # Load after arkite_unit_views.xml (needs action_arkite_unit), defines action_project
        'views/arkite_step_server_actions.xml',
        'views/variant_views.xml',
        'views/material_views.xml',
        'views/material_link_wizard_views.xml',
        'views/progress_views.xml',
        'views/arkite_project_wizard_view.xml',
        'views/arkite_job_step_wizard_view.xml',
        'views/arkite_process_create_wizard_view.xml',
        'data/arkite_security_data.xml',
        'views/menu_cleanup.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'product_module/static/src/css/product_module.css',
            # 'product_module/static/src/js/hierarchy_simple.js',  # Disabled: was causing blank page
        ],
        'web.assets_backend_lazy': [
            (
                'after',
                'web_hierarchy/static/src/hierarchy_card.xml',
                'product_module/static/src/xml/hierarchy_inline_reorder.xml',
            ),
            (
                'after',
                'web_hierarchy/static/src/hierarchy_card.js',
                'product_module/static/src/js/hierarchy_inline_reorder.js',
            ),
            # Reload Project form after specific buttons (modal-safe)
            'product_module/static/src/js/x2many_dialog_reload_after_buttons.js',
        ],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
}