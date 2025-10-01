{
    'name': 'Product Module',
    'version': '1.0',
    'summary': 'Smart table for tracking and managing product information.',
    'description': 'This module provides a smart table interface to record, organize, and manage product details efficiently.',
    'author': 'II- F Information Technology  (NHL Stenden)',
    'category': 'Productivity',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/page_data.xml',
        'views/product_assemble_views.xml',   # form (blank) + action + menus (root app)
    ],
    'images': ['static/description/icon.png'],  # optional app icon (add the file if you want an icon)
    'installable': True,
    'application': True,   # <-- makes it a top-level app
}
