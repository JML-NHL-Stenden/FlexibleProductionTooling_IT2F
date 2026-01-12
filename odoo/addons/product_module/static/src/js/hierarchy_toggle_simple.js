// Simple approach: Use MutationObserver to watch for hierarchy fields
// This doesn't patch anything, just adds functionality when DOM is ready
// NO @odoo-module comment - this is plain JavaScript

(function() {
    'use strict';
    
    let initialized = false;
    
    function initializeHierarchy() {
        if (initialized) return;
        
        const tables = document.querySelectorAll(
            'field[name="arkite_job_step_ids"] .o_list_view tbody, ' +
            'field[name="arkite_process_step_ids"] .o_list_view tbody'
        );
        
        if (tables.length === 0) return;
        
        tables.forEach(function(tbody) {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            if (rows.length === 0) return;
            
            const levelMap = new Map();
            
            // First pass: collect all hierarchy levels
            rows.forEach(function(row, index) {
                const levelCell = row.querySelector('td[data-name="hierarchical_level_html"]');
                if (!levelCell) return;
                
                const container = levelCell.querySelector('.hierarchy-level-container');
                if (!container) return;
                
                let level = container.getAttribute('data-level');
                if (!level) {
                    const match = levelCell.textContent.match(/(\d+(?:\.\d+)*)/);
                    if (match) level = match[1];
                }
                
                if (level && level !== '?') {
                    levelMap.set(index, level);
                    row.dataset.hierarchyLevel = level;
                }
            });
            
            // Second pass: hide children (depth > 0)
            rows.forEach(function(row, index) {
                const level = levelMap.get(index);
                if (!level) return;
                
                const depth = level.split('.').length;
                if (depth > 0) {
                    row.style.display = 'none';
                    row.dataset.hierarchyHidden = 'true';
                }
            });
            
            // Third pass: attach click handlers using event delegation
            tbody.addEventListener('click', function(e) {
                const icon = e.target.closest('.hierarchy-toggle-icon');
                const badge = e.target.closest('.hierarchy-level-badge');
                
                if (icon || badge) {
                    e.stopPropagation();
                    e.preventDefault();
                    
                    const container = (icon || badge).closest('.hierarchy-level-container');
                    if (!container) return;
                    
                    const row = container.closest('tr');
                    if (!row) return;
                    
                    const level = row.dataset.hierarchyLevel || container.getAttribute('data-level');
                    if (!level || level === '?') return;
                    
                    toggleHierarchy(row, level, tbody);
                }
            });
        });
        
        initialized = true;
    }
    
    function toggleHierarchy(row, level, tbody) {
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
            
            // Check if this is a direct child
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
        
        childRows.forEach(function(childRow) {
            childRow.style.display = isHidden ? '' : 'none';
            childRow.dataset.hierarchyHidden = isHidden ? 'false' : 'true';
        });
        
        // Update icon
        const icon = row.querySelector('.hierarchy-toggle-icon');
        if (icon) {
            const isExpanded = !isHidden;
            icon.textContent = isExpanded ? '▼' : '▶';
            icon.setAttribute('data-expanded', isExpanded);
        }
        
        // Recursively collapse grandchildren if collapsing
        if (isHidden) {
            childRows.forEach(function(childRow) {
                const childToggle = childRow.querySelector('.hierarchy-toggle-icon');
                if (childToggle && childToggle.getAttribute('data-expanded') === 'true') {
                    const childLevel = childRow.dataset.hierarchyLevel;
                    if (childLevel) {
                        toggleHierarchy(childRow, childLevel, tbody);
                    }
                }
            });
        }
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            setTimeout(initializeHierarchy, 500);
        });
    } else {
        setTimeout(initializeHierarchy, 500);
    }
    
    // Watch for dynamic content
    if (typeof MutationObserver !== 'undefined') {
        const observer = new MutationObserver(function(mutations) {
            let shouldInit = false;
            mutations.forEach(function(mutation) {
                if (mutation.addedNodes.length > 0) {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1) {
                            if (node.matches && (
                                node.matches('field[name="arkite_job_step_ids"]') ||
                                node.matches('field[name="arkite_process_step_ids"]') ||
                                node.querySelector('field[name="arkite_job_step_ids"]') ||
                                node.querySelector('field[name="arkite_process_step_ids"]')
                            )) {
                                shouldInit = true;
                            }
                        }
                    });
                }
            });
            if (shouldInit) {
                initialized = false; // Reset to allow re-initialization
                setTimeout(initializeHierarchy, 300);
            }
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }
})();
