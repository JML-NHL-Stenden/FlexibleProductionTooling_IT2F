from odoo import http

class ProductModulePage(http.Controller):

    @http.route('/product_module/page', type='http', auth='public')
    def product_page(self, **kw):
        return """
        <html>
            <head><title>Product Module Page</title></head>
            <body>
                <h1>New Page</h1>
                <p>This is a new page provided by the Product Module.</p>
            </body>
        </html>
        """
