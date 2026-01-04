# -*- coding: utf-8 -*-

def migrate(cr, version):
    """
    Migration script to fix selected_process_id field type change from Many2one to Char
    """
    # Delete any stale field definitions
    cr.execute("""
        DELETE FROM ir_model_fields 
        WHERE model = 'product_module.arkite.job.step.wizard' 
        AND name = 'selected_process_id' 
        AND ttype != 'char'
    """)
    
    # Delete any stale ir_model_data records
    cr.execute("""
        DELETE FROM ir_model_data 
        WHERE model = 'ir.model.field' 
        AND module = 'product_module'
        AND res_id IN (
            SELECT id FROM ir_model_fields 
            WHERE model = 'product_module.arkite.job.step.wizard' 
            AND name = 'selected_process_id' 
            AND ttype != 'char'
        )
    """)
    
    # Ensure the field is Char type
    cr.execute("""
        UPDATE ir_model_fields 
        SET ttype = 'char', 
            relation = NULL, 
            on_delete = NULL
        WHERE model = 'product_module.arkite.job.step.wizard' 
        AND name = 'selected_process_id'
    """)
