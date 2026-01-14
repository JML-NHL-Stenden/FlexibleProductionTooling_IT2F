/** @odoo-module **/

import { registry } from "@web/core/registry";
import { X2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ListRenderer } from "@web/views/list/list_renderer";
import { useService } from "@web/core/utils/hooks";
import { Component, onMounted, onPatched, useRef } from "@odoo/owl";

/**
 * Custom List Renderer for Hierarchy Test with drag-and-drop
 */
class HierarchyTestListRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.tableRef = useRef("table");
        this.draggedRow = null;
        this.dragOverRow = null;
    }

    onMounted() {
        super.onMounted();
        this._setupDragAndDrop();
    }

    onPatched() {
        super.onPatched();
        this._setupDragAndDrop();
    }

    _setupDragAndDrop() {
        const table = this.tableRef.el;
        if (!table) return;

        const rows = table.querySelectorAll('tbody tr[data-id]');
        
        rows.forEach(row => {
            // Make row draggable
            row.draggable = true;
            row.style.cursor = 'move';
            
            // Remove existing listeners
            const newRow = row.cloneNode(true);
            row.parentNode.replaceChild(newRow, row);
            
            // Add drag event listeners
            newRow.addEventListener('dragstart', (e) => {
                this.draggedRow = newRow;
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/html', newRow.innerHTML);
                newRow.style.opacity = '0.5';
            });
            
            newRow.addEventListener('dragend', (e) => {
                newRow.style.opacity = '1';
                if (this.dragOverRow) {
                    this.dragOverRow.style.backgroundColor = '';
                }
                this.draggedRow = null;
                this.dragOverRow = null;
            });
            
            newRow.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                
                if (this.dragOverRow && this.dragOverRow !== newRow) {
                    this.dragOverRow.style.backgroundColor = '';
                }
                
                if (newRow !== this.draggedRow) {
                    this.dragOverRow = newRow;
                    newRow.style.backgroundColor = '#e3f2fd';
                }
            });
            
            newRow.addEventListener('drop', (e) => {
                e.preventDefault();
                
                if (this.draggedRow && this.draggedRow !== newRow) {
                    const draggedId = this.draggedRow.dataset.id;
                    const targetId = newRow.dataset.id;
                    
                    // Determine if we're grouping (dropping on parent) or reordering
                    const targetParent = newRow.querySelector('td[data-field="parent_id"]');
                    const isGrouping = e.ctrlKey || e.metaKey; // Hold Ctrl/Cmd to group
                    
                    if (isGrouping) {
                        // Group: set dragged row's parent to target row
                        this._updateParent(draggedId, targetId);
                    } else {
                        // Reorder: swap sequence
                        this._reorderRows(draggedId, targetId);
                    }
                }
                
                if (this.dragOverRow) {
                    this.dragOverRow.style.backgroundColor = '';
                }
            });
        });
    }

    async _updateParent(childId, parentId) {
        try {
            const childRecord = this.props.list.records.find(r => r.id === childId);
            const parentRecord = this.props.list.records.find(r => r.id === parentId);
            
            if (childRecord && parentRecord) {
                await this.props.list.model.root.updateRecord(childRecord, {
                    parent_id: parentId
                });
                await this.props.list.model.root.save();
            }
        } catch (error) {
            console.error('Error updating parent:', error);
        }
    }

    async _reorderRows(draggedId, targetId) {
        try {
            const draggedRecord = this.props.list.records.find(r => r.id === draggedId);
            const targetRecord = this.props.list.records.find(r => r.id === targetId);
            
            if (draggedRecord && targetRecord) {
                const draggedSeq = draggedRecord.data.sequence || 0;
                const targetSeq = targetRecord.data.sequence || 0;
                
                // Swap sequences
                await this.props.list.model.root.updateRecord(draggedRecord, {
                    sequence: targetSeq
                });
                await this.props.list.model.root.updateRecord(targetRecord, {
                    sequence: draggedSeq
                });
                await this.props.list.model.root.save();
            }
        } catch (error) {
            console.error('Error reordering:', error);
        }
    }
}

/**
 * Custom X2Many Field for Hierarchy Test
 */
export class HierarchyTestField extends X2ManyField {
    static components = {
        ...X2ManyField.components,
        ListRenderer: HierarchyTestListRenderer,
    };
}

registry.category("fields").add("hierarchy_test", HierarchyTestField);
