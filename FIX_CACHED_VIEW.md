# Fix Cached View Issue

## Problem
Odoo has a cached view in the database with an old xpath that references inline styles:
```
//div[@style='display: flex; gap: 12px;']
```

This xpath no longer exists in the current files (we converted all inline styles to CSS classes), but Odoo is trying to apply it from the cached view.

## Solution Options

### Option 1: Delete the Cached View (Recommended)

Connect to your PostgreSQL database and run:

```sql
-- Find the problematic view
SELECT id, name, model, inherit_id 
FROM ir_ui_view 
WHERE name = 'product.assemble.page.form.with.progress';

-- Delete the cached view (replace <view_id> with the actual ID from above)
DELETE FROM ir_ui_view WHERE id = <view_id>;

-- Or delete by name directly:
DELETE FROM ir_ui_view WHERE name = 'product.assemble.page.form.with.progress';
```

Then restart Odoo and try upgrading again.

### Option 2: Update via Odoo Shell

1. Access Odoo shell:
   ```bash
   docker-compose exec odoo odoo shell -d your_database_name
   ```

2. Run these commands:
   ```python
   view = env['ir.ui.view'].search([('name', '=', 'product.assemble.page.form.with.progress')])
   if view:
       view.unlink()
   env.cr.commit()
   ```

3. Restart Odoo and upgrade the module

### Option 3: Manual Fix via Odoo UI

1. Go to **Settings → Technical → User Interface → Views**
2. Search for: `product.assemble.page.form.with.progress`
3. Delete the view record
4. Restart Odoo
5. Upgrade the module

### Option 4: Uninstall and Reinstall Module

1. Go to **Apps** menu
2. Remove the app filter
3. Search for your module
4. Click **Uninstall**
5. Restart Odoo
6. Install the module again

## Verification

After applying any of the above solutions, verify the view is gone:
```sql
SELECT COUNT(*) FROM ir_ui_view WHERE name = 'product.assemble.page.form.with.progress';
-- Should return 0
```

Then upgrade the module - it should work now.
