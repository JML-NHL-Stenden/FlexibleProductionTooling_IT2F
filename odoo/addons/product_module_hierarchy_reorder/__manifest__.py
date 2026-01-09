{
    "name": "Product Module - Hierarchy Diagram Reorder Patch",
    "version": "1.0",
    "category": "Hidden",
    "summary": "Enable sibling reorder (A↔B) in web_hierarchy diagram for product_module steps",
    "depends": ["web", "web_hierarchy", "product_module"],
    "data": [],
    "assets": {
        # web_hierarchy is loaded in backend_lazy; patch in same bundle and after renderer.
        "web.assets_backend_lazy": [
            (
                "after",
                "web_hierarchy/static/src/hierarchy_renderer.js",
                "product_module_hierarchy_reorder/static/src/js/hierarchy_diagram_reorder_patch.js",
            ),
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False,
}

