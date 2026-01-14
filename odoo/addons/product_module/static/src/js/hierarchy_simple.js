// Simple hierarchy toggle - no OWL, no modules, just plain JavaScript
(function() {
    'use strict';
    
    function initHierarchy() {
        var tbodies = document.querySelectorAll(
            'field[name="arkite_job_step_ids"] .o_list_view tbody, ' +
            'field[name="arkite_process_step_ids"] .o_list_view tbody'
        );
        
        if (tbodies.length === 0) return false;
        
        tbodies.forEach(function(tbody) {
            // Skip if already initialized
            if (tbody.dataset.hierarchyInitialized === 'true') return;
            tbody.dataset.hierarchyInitialized = 'true';
            
            // Event delegation for clicks
            tbody.addEventListener('click', function(e) {
                var target = e.target;
                var icon = target.closest('.hierarchy-toggle-icon[data-has-children="true"]');
                var badge = target.closest('.hierarchy-level-badge');
                
                if (icon && icon.dataset.hasChildren === 'true') {
                    e.stopPropagation();
                    e.preventDefault();
                    toggleRow(icon, tbody);
                } else if (badge) {
                    var container = badge.closest('.hierarchy-level-container');
                    if (container) {
                        var icon = container.querySelector('.hierarchy-toggle-icon[data-has-children="true"]');
                        if (icon) {
                            e.stopPropagation();
                            e.preventDefault();
                            toggleRow(icon, tbody);
                        }
                    }
                }
            });
            
            // Hide children by default
            hideChildren(tbody);
        });
        
        return true;
    }
    
    function hideChildren(tbody) {
        var rows = Array.from(tbody.querySelectorAll('tr'));
        rows.forEach(function(row) {
            var cell = row.querySelector('td[data-name="hierarchical_level_html"]');
            if (!cell) return;
            var cont = cell.querySelector('.hierarchy-level-container');
            if (!cont) return;
            var level = cont.getAttribute('data-level');
            if (!level) {
                var match = cell.textContent.match(/(\d+(?:\.\d+)*)/);
                if (match) level = match[1];
            }
            if (level && level !== '?' && level.split('.').length > 0) {
                row.style.display = 'none';
                row.dataset.hierarchyHidden = 'true';
            }
        });
    }
    
    function toggleRow(icon, tbody) {
        var row = icon.closest('tr');
        if (!row) return;
        
        var level = icon.getAttribute('data-level');
        if (!level || level === '?') return;
        
        var rows = Array.from(tbody.querySelectorAll('tr'));
        var currentIndex = rows.indexOf(row);
        var levelDepth = level.split('.').length;
        var currentLevel = level;
        
        // Find all child rows
        var childRows = [];
        for (var i = currentIndex + 1; i < rows.length; i++) {
            var nextRow = rows[i];
            var nextCell = nextRow.querySelector('td[data-name="hierarchical_level_html"]');
            if (!nextCell) continue;
            
            var nextCont = nextCell.querySelector('.hierarchy-level-container');
            var nextLevel = nextCont ? nextCont.getAttribute('data-level') : '';
            if (!nextLevel) {
                var match = nextCell.textContent.match(/(\d+(?:\.\d+)*)/);
                if (match) nextLevel = match[1];
            }
            if (!nextLevel || nextLevel === '?') continue;
            
            var nextDepth = nextLevel.split('.').length;
            if (nextDepth <= levelDepth) break;
            
            if (nextLevel.startsWith(currentLevel + '.') && nextDepth === levelDepth + 1) {
                childRows.push(nextRow);
            } else if (nextDepth > levelDepth + 1) {
                var parentRow = childRows[childRows.length - 1];
                if (parentRow && parentRow.style.display !== 'none') {
                    var grandParentLevel = nextLevel.substring(0, nextLevel.lastIndexOf('.'));
                    if (grandParentLevel.startsWith(currentLevel + '.')) {
                        childRows.push(nextRow);
                    }
                }
            }
        }
        
        if (childRows.length === 0) return;
        
        var isHidden = childRows[0].style.display === 'none';
        
        childRows.forEach(function(childRow) {
            childRow.style.display = isHidden ? '' : 'none';
            childRow.dataset.hierarchyHidden = isHidden ? 'false' : 'true';
        });
        
        icon.textContent = isHidden ? '▼' : '▶';
        icon.setAttribute('data-expanded', isHidden);
        
        // Recursively collapse grandchildren
        if (isHidden) {
            childRows.forEach(function(childRow) {
                var childToggle = childRow.querySelector('.hierarchy-toggle-icon[data-expanded="true"]');
                if (childToggle) {
                    toggleRow(childToggle, tbody);
                }
            });
        }
    }
    
    // Initialize
    function runInit() {
        var attempts = 0;
        var maxAttempts = 20;
        var interval = setInterval(function() {
            attempts++;
            if (initHierarchy() || attempts >= maxAttempts) {
                clearInterval(interval);
            }
        }, 300);
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runInit);
    } else {
        runInit();
    }
    
    // Watch for dynamic content
    if (typeof MutationObserver !== 'undefined') {
        var observer = new MutationObserver(function(mutations) {
            var shouldInit = false;
            mutations.forEach(function(mutation) {
                if (mutation.addedNodes.length > 0) {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1) {
                            var hasField = (node.matches && (
                                node.matches('field[name="arkite_job_step_ids"]') ||
                                node.matches('field[name="arkite_process_step_ids"]')
                            )) || (node.querySelector && (
                                node.querySelector('field[name="arkite_job_step_ids"]') ||
                                node.querySelector('field[name="arkite_process_step_ids"]')
                            ));
                            if (hasField) {
                                shouldInit = true;
                            }
                        }
                    });
                }
            });
            if (shouldInit) {
                setTimeout(function() {
                    var tbodies = document.querySelectorAll(
                        'field[name="arkite_job_step_ids"] .o_list_view tbody, ' +
                        'field[name="arkite_process_step_ids"] .o_list_view tbody'
                    );
                    tbodies.forEach(function(tbody) {
                        tbody.dataset.hierarchyInitialized = 'false';
                    });
                    initHierarchy();
                }, 500);
            }
        });
        observer.observe(document.body, {childList: true, subtree: true});
    }
})();
