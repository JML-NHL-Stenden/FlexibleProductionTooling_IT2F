# product_module/models/instruction_import_wizard.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import csv
from io import StringIO


class InstructionImportWizard(models.TransientModel):
    _name = 'product_module.instruction.import.wizard'
    _description = 'Import Instructions from CSV'

    product_id = fields.Many2one('product_module.product', string='Product', required=True, readonly=True)
    csv_file = fields.Binary(string='CSV File', help='Upload a CSV file with columns: Product Name, Product Code, Step #, Title, Description', attachment=False)
    csv_filename = fields.Char(string='Filename')
    replace_existing = fields.Boolean(string='Replace instructions', default=True, 
                                      help='If checked, existing instructions will be deleted before import')
    update_product_info = fields.Boolean(string='Update name & code', default=False,
                                         help='If checked, product name and code will be updated from CSV')

    @api.constrains('csv_file', 'csv_filename')
    def _check_file_type(self):
        """Validate that uploaded file is CSV"""
        for wizard in self:
            if wizard.csv_file and wizard.csv_filename:
                if not wizard.csv_filename.lower().endswith('.csv'):
                    raise UserError(_('Invalid file type. Please upload a CSV file.'))

    def action_import(self):
        """Import instructions from uploaded CSV file"""
        self.ensure_one()
        
        if not self.csv_file:
            raise UserError(_('Please select a CSV file to import.'))
        
        # Validate file type
        if not self.csv_filename or not self.csv_filename.lower().endswith('.csv'):
            raise UserError(_('Invalid file type. Please upload a CSV file.'))
        
        try:
            # Decode CSV file
            csv_data = base64.b64decode(self.csv_file).decode('utf-8')
            csv_reader = csv.DictReader(StringIO(csv_data))
            
            # Validate CSV format by checking headers
            required_headers = ['Product Name', 'Product Code', 'Step #', 'Title', 'Description']
            if csv_reader.fieldnames is None or not all(header in csv_reader.fieldnames for header in required_headers):
                raise UserError(_('Invalid CSV format. Required columns: Product Name, Product Code, Step #, Title, Description'))
            
            # Update product info if checkbox is checked
            first_row = True
            product_name = None
            product_code = None
            
            # Delete existing instructions if replace option is checked
            if self.replace_existing:
                self.product_id.instruction_ids.unlink()
            
            # Import new instructions
            instruction_obj = self.env['product_module.instruction']
            row_count = 0
            for row in csv_reader:
                row_count += 1
                
                # Get product info from first row
                if first_row:
                    product_name = row.get('Product Name', '').strip()
                    product_code = row.get('Product Code', '').strip()
                    first_row = False
                    
                    # Update product if checkbox is checked
                    if self.update_product_info:
                        update_vals = {}
                        if product_name:
                            update_vals['name'] = product_name
                        if product_code:
                            update_vals['product_code'] = product_code
                        if update_vals:
                            self.product_id.write(update_vals)
                
                try:
                    sequence = int(row.get('Step #', 10))
                except ValueError:
                    raise UserError(_(f'Invalid CSV format. Row {row_count}: "Step #" must be a number.'))
                
                instruction_obj.create({
                    'product_id': self.product_id.id,
                    'sequence': sequence,
                    'title': row.get('Title', '').strip(),
                    'description': row.get('Description', '').strip(),
                })
            
            return {'type': 'ir.actions.act_window_close'}
            
        except UnicodeDecodeError:
            raise UserError(_('Invalid CSV format. File encoding must be UTF-8.'))
        except csv.Error:
            raise UserError(_('Invalid CSV format. Please check your file structure.'))

