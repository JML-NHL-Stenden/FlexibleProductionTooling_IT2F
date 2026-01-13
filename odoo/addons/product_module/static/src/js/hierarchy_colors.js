/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

/**
 * Patch ListRenderer to apply hierarchy colors to level cells
 * This ensures all levels get colored even if decoration attributes don't work
 */
patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
    },

    onMounted() {
        super.onMounted?.();
        this._applyHierarchyColors();
    },

    onPatched() {
        super.onPatched?.();
        this._applyHierarchyColors();
    },

    _applyHierarchyColors() {
        try {
            // Only apply to job steps and process steps
            const resModel = this.props?.list?.resModel;
            if (resModel !== 'product_module.arkite.job.step' && 
                resModel !== 'product_module.arkite.process.step') {
                return;
            }

            // Use setTimeout to ensure DOM is ready
            setTimeout(() => {
                try {
                    // Try multiple ways to find the element
                    const el = this.el || this.root?.el || document;
                    const listContainer = el.querySelector?.('field[name="arkite_job_step_ids"], field[name="arkite_process_step_ids"]') || el;
                    const rows = listContainer.querySelectorAll?.('tbody tr');
                    
                    if (!rows || rows.length === 0) return;

                    rows.forEach(row => {
                        try {
                            const levelCell = row.querySelector('td[data-name="hierarchical_level"]');
                            if (!levelCell) return;

                            // Get the level text
                            const levelText = (levelCell.textContent || levelCell.innerText || '').trim();
                            if (!levelText || levelText === '?') return;

                            // Count dots to determine level
                            const dotCount = levelText.split('.').length - 1;
                            
                            // Remove existing hierarchy classes
                            row.classList.remove('hierarchy-root', 'hierarchy-level-1', 'hierarchy-level-2', 
                                               'hierarchy-level-3', 'hierarchy-level-4', 'hierarchy-level-5');
                            
                            // Add appropriate class based on dot count
                            if (dotCount === 0) {
                                row.classList.add('hierarchy-root');
                            } else if (dotCount === 1) {
                                row.classList.add('hierarchy-level-1');
                            } else if (dotCount === 2) {
                                row.classList.add('hierarchy-level-2');
                            } else if (dotCount === 3) {
                                row.classList.add('hierarchy-level-3');
                            } else if (dotCount === 4) {
                                row.classList.add('hierarchy-level-4');
                            } else {
                                row.classList.add('hierarchy-level-5');
                            }
                        } catch (e) {
                            // Silently ignore errors for individual rows
                            console.debug('[Hierarchy Colors] Error processing row:', e);
                        }
                    });
                } catch (e) {
                    console.debug('[Hierarchy Colors] Error in setTimeout:', e);
                }
            }, 200);
        } catch (e) {
            console.debug('[Hierarchy Colors] Error in _applyHierarchyColors:', e);
        }
    }
});
