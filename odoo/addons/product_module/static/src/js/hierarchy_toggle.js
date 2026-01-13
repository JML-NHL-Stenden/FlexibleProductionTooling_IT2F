/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        this.hierarchyInitialized = false;
    },

    onMounted() {
        super.onMounted?.();
        try {
            this._initializeHierarchy();
        } catch (e) {
            console.debug('Hierarchy toggle onMounted error:', e);
        }
    },

    onPatched() {
        super.onPatched?.();
        try {
            this._initializeHierarchy();
        } catch (e) {
            console.debug('Hierarchy toggle onPatched error:', e);
        }
    },

    _initializeHierarchy() {
        const model = this.props?.list?.resModel;
        if (model !== 'product_module.arkite.job.step' && model !== 'product_module.arkite.process.step') {
            return;
        }

        // Wait for DOM to be ready
        setTimeout(() => {
            this._hideChildrenByDefault();
            this._attachToggleHandlers();
        }, 200);
    },

    _hideChildrenByDefault() {
        try {
            // Access the table element - try multiple ways
            let tbody = null;
            if (this.el) {
                tbody = this.el.querySelector('tbody');
            }
            if (!tbody && this.props?.list?.el) {
                tbody = this.props.list.el.querySelector('tbody');
            }
            if (!tbody) {
                // Try to find by field name
                const fieldEl = document.querySelector('field[name="arkite_job_step_ids"] .o_list_view tbody, field[name="arkite_process_step_ids"] .o_list_view tbody');
                if (fieldEl) tbody = fieldEl;
            }
            if (!tbody) return;

            const rows = Array.from(tbody.querySelectorAll('tr'));
            if (rows.length === 0) return;

            const levelMap = new Map();

            // First pass: collect all hierarchy levels
            rows.forEach((row, index) => {
                const levelCell = row.querySelector('td[data-name="hierarchical_level_html"]');
                if (!levelCell) return;

                const container = levelCell.querySelector('.hierarchy-level-container');
                if (!container) return;

                let level = container.getAttribute('data-level');
                if (!level) {
                    // Try to extract from text content
                    const match = levelCell.textContent.match(/(\d+(?:\.\d+)*)/);
                    if (match) level = match[1];
                }

                if (level && level !== '?') {
                    levelMap.set(index, level);
                    row.dataset.hierarchyLevel = level;
                }
            });

            // Second pass: hide children (depth > 0)
            rows.forEach((row, index) => {
                const level = levelMap.get(index);
                if (!level) return;

                const depth = level.split('.').length;
                if (depth > 0) {
                    // This is a child - hide it by default
                    row.style.display = 'none';
                    row.dataset.hierarchyHidden = 'true';
                }
            });
        } catch (e) {
            console.debug('Hierarchy initialization error:', e);
        }
    },

    _attachToggleHandlers() {
        try {
            // Access the table element - try multiple ways
            let tbody = null;
            if (this.el) {
                tbody = this.el.querySelector('tbody');
            }
            if (!tbody && this.props?.list?.el) {
                tbody = this.props.list.el.querySelector('tbody');
            }
            if (!tbody) {
                // Try to find by field name
                const fieldEl = document.querySelector('field[name="arkite_job_step_ids"] .o_list_view tbody, field[name="arkite_process_step_ids"] .o_list_view tbody');
                if (fieldEl) tbody = fieldEl;
            }
            if (!tbody) return;

            // Remove old handlers
            tbody.querySelectorAll('.hierarchy-toggle-icon').forEach(icon => {
                const newIcon = icon.cloneNode(true);
                icon.parentNode.replaceChild(newIcon, icon);
            });

            // Attach click handlers to toggle icons
            tbody.querySelectorAll('.hierarchy-toggle-icon').forEach(icon => {
                icon.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this._toggleHierarchy(icon);
                });
            });

            // Also attach to level badges
            tbody.querySelectorAll('.hierarchy-level-badge').forEach(badge => {
                badge.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const container = badge.closest('.hierarchy-level-container');
                    if (container) {
                        const icon = container.querySelector('.hierarchy-toggle-icon');
                        if (icon) {
                            this._toggleHierarchy(icon);
                        }
                    }
                });
            });
        } catch (e) {
            console.debug('Error attaching toggle handlers:', e);
        }
    },

    _toggleHierarchy(iconElement) {
        try {
            const row = iconElement.closest('tr');
            if (!row) return;

            const tbody = row.closest('tbody');
            if (!tbody) return;

            const level = row.dataset.hierarchyLevel || iconElement.getAttribute('data-level');
            if (!level || level === '?') return;

            const rows = Array.from(tbody.querySelectorAll('tr'));
            const currentIndex = rows.indexOf(row);
            const levelDepth = level.split('.').length;
            const currentLevel = level;

            // Find all direct child rows
            const childRows = [];
            for (let i = currentIndex + 1; i < rows.length; i++) {
                const nextRow = rows[i];
                const nextLevel = nextRow.dataset.hierarchyLevel;
                
                if (!nextLevel || nextLevel === '?') continue;

                const nextDepth = nextLevel.split('.').length;

                // If we hit a sibling or parent, stop
                if (nextDepth <= levelDepth) break;

                // Check if this is a direct child (starts with current level + '.' and depth is exactly +1)
                if (nextLevel.startsWith(currentLevel + '.') && nextDepth === levelDepth + 1) {
                    childRows.push(nextRow);
                } else if (nextDepth > levelDepth + 1) {
                    // This is a grandchild - include it if parent is visible
                    const parentRow = childRows[childRows.length - 1];
                    if (parentRow && parentRow.style.display !== 'none') {
                        const grandParentLevel = nextLevel.substring(0, nextLevel.lastIndexOf('.'));
                        if (grandParentLevel.startsWith(currentLevel + '.')) {
                            childRows.push(nextRow);
                        }
                    }
                }
            }

            if (childRows.length === 0) return;

            // Toggle visibility
            const isHidden = childRows[0].style.display === 'none';

            childRows.forEach(childRow => {
                childRow.style.display = isHidden ? '' : 'none';
                childRow.dataset.hierarchyHidden = isHidden ? 'false' : 'true';
            });

            // Update icon
            const isExpanded = !isHidden;
            iconElement.textContent = isExpanded ? '▼' : '▶';
            iconElement.setAttribute('data-expanded', isExpanded);

            // Recursively collapse grandchildren if collapsing
            if (isHidden) {
                childRows.forEach(childRow => {
                    const childToggle = childRow.querySelector('.hierarchy-toggle-icon');
                    if (childToggle && childToggle.getAttribute('data-expanded') === 'true') {
                        const childLevel = childRow.dataset.hierarchyLevel;
                        if (childLevel) {
                            this._toggleHierarchy(childToggle);
                        }
                    }
                });
            }
        } catch (e) {
            console.debug('Hierarchy toggle error:', e);
        }
    }
});
