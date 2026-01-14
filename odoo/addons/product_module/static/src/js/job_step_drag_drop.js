/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ListRenderer } from "@web/views/list/list_renderer";

// Patch the list renderer to add drag-and-drop and color coding
patch(ListRenderer.prototype, {
    setup() {
        super.setup();
        // Use setTimeout to ensure DOM is ready after mount
        setTimeout(() => {
            const model = this.props?.list?.resModel;
            if (model === 'product_module.arkite.job.step' || model === 'product_module.arkite.process.step') {
                if (model === 'product_module.arkite.job.step') {
                    this.setupJobStepDragAndDrop();
                }
                this.applyHierarchyColors();
            }
        }, 100);
    },

    onMounted() {
        super.onMounted?.();
        // Setup after mount
        setTimeout(() => {
            const model = this.props?.list?.resModel;
            if (model === 'product_module.arkite.job.step' || model === 'product_module.arkite.process.step') {
                if (model === 'product_module.arkite.job.step') {
                    this.setupJobStepDragAndDrop();
                }
                this.applyHierarchyColors();
            }
        }, 100);
    },

    onPatched() {
        super.onPatched?.();
        // Re-setup after patch
        setTimeout(() => {
            const model = this.props?.list?.resModel;
            if (model === 'product_module.arkite.job.step' || model === 'product_module.arkite.process.step') {
                if (model === 'product_module.arkite.job.step') {
                    this.setupJobStepDragAndDrop();
                }
                this.applyHierarchyColors();
            }
        }, 100);
    },

    setupJobStepDragAndDrop() {
        if (!this.el) return;
        const listView = this.el.querySelector('.o_list_view tbody');
        if (!listView) return;

        const rows = listView.querySelectorAll('tr.o_data_row');
        rows.forEach((row) => {
            if (row.hasAttribute('data-drag-setup')) return;
            row.setAttribute('data-drag-setup', 'true');

            row.draggable = true;
            row.style.cursor = 'move';

            const self = this;
            row.addEventListener('dragstart', function(e) {
                const recordId = self.getRecordIdFromRow(row);
                if (recordId) {
                    e.dataTransfer.effectAllowed = 'move';
                    e.dataTransfer.setData('text/plain', recordId);
                    row.classList.add('dragging');
                    row.style.opacity = '0.5';
                } else {
                    e.preventDefault();
                }
            });

            row.addEventListener('dragover', function(e) {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                if (!row.classList.contains('drag-over')) {
                    row.classList.add('drag-over');
                    row.style.backgroundColor = '#e3f2fd';
                }
            });

            row.addEventListener('dragleave', function() {
                row.classList.remove('drag-over');
                row.style.backgroundColor = '';
            });

            row.addEventListener('drop', async function(e) {
                e.preventDefault();
                e.stopPropagation();
                row.classList.remove('drag-over');
                row.style.backgroundColor = '';

                const draggedRecordId = e.dataTransfer.getData('text/plain');
                if (!draggedRecordId) return;

                const draggedRow = listView.querySelector(`tr[data-id="${draggedRecordId}"]`);
                if (!draggedRow || draggedRow === row) return;

                const targetRecordId = self.getRecordIdFromRow(row);
                if (!targetRecordId) return;

                try {
                    const orm = self.env.services.orm;
                    await orm.write(
                        'product_module.arkite.job.step',
                        [parseInt(draggedRecordId)],
                        { parent_step_record: parseInt(targetRecordId) }
                    );
                    // Reload the view to refresh hierarchy
                    if (self.props?.list?.load) {
                        await self.props.list.load();
                    } else if (self.props?.list?.reload) {
                        await self.props.list.reload();
                    }
                    // Reapply colors after reload
                    setTimeout(() => {
                        self.applyHierarchyColors();
                    }, 100);
                } catch (error) {
                    console.error('Error updating parent:', error);
                    alert('Error updating parent relationship: ' + (error.message || error));
                }
            });

            row.addEventListener('dragend', function() {
                row.classList.remove('dragging');
                row.style.opacity = '';
                const allRows = listView.querySelectorAll('tr.o_data_row');
                allRows.forEach((r) => {
                    r.classList.remove('drag-over');
                    r.style.backgroundColor = '';
                });
            });
        });
    },

    getRecordIdFromRow(row) {
        const dataId = row.getAttribute('data-id');
        if (dataId) return dataId;

        const firstCell = row.querySelector('td[data-res-id]');
        if (firstCell) {
            return firstCell.getAttribute('data-res-id');
        }

        const rowId = row.id;
        if (rowId) {
            const match = rowId.match(/\d+/);
            if (match) return match[0];
        }

        return null;
    },

    applyHierarchyColors() {
        if (!this.el) return;
        const listView = this.el.querySelector('.o_list_view tbody');
        if (!listView) return;

        const rows = listView.querySelectorAll('tr.o_data_row');
        rows.forEach((row) => {
            const levelCell = row.querySelector('td[data-name="hierarchical_level"]');
            if (!levelCell) return;

            const levelText = levelCell.textContent.trim();
            if (!levelText || levelText === '?') return;

            // Remove existing hierarchy classes
            row.classList.remove('hierarchy-root', 'hierarchy-level-1', 'hierarchy-level-2', 'hierarchy-level-3', 'hierarchy-level-4', 'hierarchy-level-5');
            levelCell.classList.remove('level-root', 'level-1', 'level-2', 'level-3', 'level-4', 'level-5');

            // Count dots to determine level depth
            const dotCount = (levelText.match(/\./g) || []).length;

            if (dotCount === 0) {
                row.classList.add('hierarchy-root');
                levelCell.classList.add('level-root');
            } else if (dotCount === 1) {
                row.classList.add('hierarchy-level-1');
                levelCell.classList.add('level-1');
            } else if (dotCount === 2) {
                row.classList.add('hierarchy-level-2');
                levelCell.classList.add('level-2');
            } else if (dotCount === 3) {
                row.classList.add('hierarchy-level-3');
                levelCell.classList.add('level-3');
            } else if (dotCount === 4) {
                row.classList.add('hierarchy-level-4');
                levelCell.classList.add('level-4');
            } else {
                row.classList.add('hierarchy-level-5');
                levelCell.classList.add('level-5');
            }
        });
    },
});
