// Pure vanilla JavaScript - no Odoo module system
// This adds expandable rows to process step lists

(function() {
    'use strict';
    
    function initExpandableRows() {
        try {
            // Find all process step lists
            const stepLists = document.querySelectorAll('field[name="arkite_process_step_ids"] .o_list_table');
            
            stepLists.forEach(function(table) {
                if (table.dataset.expandableInitialized) {
                    return; // Already initialized
                }
                table.dataset.expandableInitialized = 'true';
                
                // Add header column
                const headerRow = table.querySelector('thead tr');
                if (headerRow && !headerRow.querySelector('.o_expand_header')) {
                    const th = document.createElement('th');
                    th.className = 'o_expand_header';
                    th.style.cssText = 'width: 36px; min-width: 36px;';
                    headerRow.insertBefore(th, headerRow.firstChild);
                }
                
                // Process rows
                const rows = table.querySelectorAll('tbody tr.o_data_row');
                rows.forEach(function(row) {
                    if (row.querySelector('.o_expand_cell')) {
                        return; // Already has expand cell
                    }
                    
                    const td = document.createElement('td');
                    td.className = 'o_expand_cell';
                    td.style.cssText = 'width: 36px; text-align: center; cursor: pointer;';
                    td.innerHTML = '<i class="fa fa-chevron-right o_expand_icon" style="color: #495057;"></i>';
                    
                    td.onclick = function(e) {
                        e.stopPropagation();
                        toggleRow(row);
                    };
                    
                    row.insertBefore(td, row.firstChild);
                });
            });
        } catch (err) {
            console.warn('Expandable rows init error:', err);
        }
    }
    
    function toggleRow(row) {
        try {
            const isOpen = row.dataset.expanded === 'true';
            const icon = row.querySelector('.o_expand_icon');
            
            if (isOpen) {
                // Collapse
                row.dataset.expanded = 'false';
                icon.className = 'fa fa-chevron-right o_expand_icon';
                icon.style.transform = '';
                
                const detailRow = row.nextElementSibling;
                if (detailRow && detailRow.classList.contains('o_expand_detail_row')) {
                    detailRow.remove();
                }
            } else {
                // Expand
                row.dataset.expanded = 'true';
                icon.className = 'fa fa-chevron-down o_expand_icon';
                icon.style.transform = '';
                
                // Get row data
                const cells = row.querySelectorAll('td');
                const stepName = cells[1]?.textContent?.trim() || 'Unnamed Step';
                const stepType = cells[2]?.textContent?.trim() || 'WORK_INSTRUCTION';
                
                const colspan = cells.length;
                
                const detailRow = document.createElement('tr');
                detailRow.className = 'o_expand_detail_row';
                detailRow.innerHTML = `
                    <td colspan="${colspan}" style="padding: 0; background: #f8f9fa;">
                        <div style="margin: 4px 12px 12px 48px; padding: 16px; background: white; border: 1px solid #dee2e6; border-radius: 8px;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e9ecef;">
                                <div>
                                    <span class="badge bg-primary" style="font-size: 11px; padding: 4px 8px;">${escapeHtml(stepType)}</span>
                                    <strong style="margin-left: 10px;">${escapeHtml(stepName)}</strong>
                                </div>
                                <button type="button" class="btn btn-sm btn-outline-secondary" onclick="this.closest('tr').previousElementSibling.click()">
                                    <i class="fa fa-chevron-up"></i> Collapse
                                </button>
                            </div>
                            <div style="font-size: 12px; color: #6c757d;">
                                Step details for: <strong>${escapeHtml(stepName)}</strong>
                            </div>
                        </div>
                    </td>
                `;
                
                row.insertAdjacentElement('afterend', detailRow);
            }
        } catch (err) {
            console.warn('Toggle row error:', err);
        }
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // Wait for Odoo to fully load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(initExpandableRows, 1000);
        });
    } else {
        setTimeout(initExpandableRows, 1000);
    }
    
    // Watch for new rows being added
    if (typeof MutationObserver !== 'undefined') {
        const observer = new MutationObserver(function() {
            setTimeout(initExpandableRows, 500);
        });
        
        // Start observing when body is available
        if (document.body) {
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        } else {
            document.addEventListener('DOMContentLoaded', function() {
                observer.observe(document.body, {
                    childList: true,
                    subtree: true
                });
            });
        }
    }
})();
