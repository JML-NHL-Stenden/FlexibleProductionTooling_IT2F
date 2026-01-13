/** @odoo-module **/

/**
 * IMPORTANT SAFETY RULE:
 * This file must NEVER throw at import/evaluation time. If it throws, Odoo's
 * backend_lazy bundle can abort and the "hierarchy" view won't register,
 * resulting in a blank page / "Cannot find key 'hierarchy'".
 */

let patch;
let HierarchyRenderer;
try {
    ({ patch } = await import("@web/core/utils/patch"));
    ({ HierarchyRenderer } = await import("@web_hierarchy/hierarchy_renderer"));
} catch (e) {
    // Fail closed: do nothing.
    // eslint-disable-next-line no-console
    console.warn("[product_module_hierarchy_reorder] Could not import dependencies, patch disabled.", e);
}

if (patch && HierarchyRenderer) {
    patch(HierarchyRenderer.prototype, "product_module_hierarchy_reorder.diagram_reorder", {
        async nodeDrop(params) {
            // Always fall back to original behavior on any error.
            try {
                const { element, newParentNode } = params || {};
                if (!element || !newParentNode) {
                    return await this._super(...arguments);
                }

                const model = this.props && this.props.model;
                const root = model && model.root;
                const dragNodeId = element.dataset && element.dataset.nodeId;
                const targetNodeId = newParentNode.dataset && newParentNode.dataset.nodeId;
                const dragNode = dragNodeId && root && root.nodePerNodeId && root.nodePerNodeId[dragNodeId];
                const targetNode = targetNodeId && root && root.nodePerNodeId && root.nodePerNodeId[targetNodeId];
                if (!dragNode || !targetNode) {
                    return await this._super(...arguments);
                }

                // COMPOSITE stays "make child" (default behavior).
                const targetType = targetNode.data && targetNode.data.step_type;
                const isCompositeTarget = targetType === "COMPOSITE";
                if (isCompositeTarget) {
                    return await this._super(...arguments);
                }

                const orm = this.env && this.env.services && this.env.services.orm;
                if (!orm) {
                    return await this._super(...arguments);
                }

                const parentFieldName = (model && model.parentFieldName) || "parent_id";
                const desiredParentResId = targetNode.parentResId || false;
                const targetSeq = Number((targetNode.data && targetNode.data.sequence) || 10);
                let newSeq = targetSeq - 1; // place before target
                if (!Number.isFinite(newSeq) || newSeq <= 0) {
                    newSeq = 1;
                }

                await orm.write(
                    model.resModel,
                    [dragNode.resId],
                    {
                        [parentFieldName]: desiredParentResId,
                        sequence: newSeq,
                    },
                    { context: model.context }
                );

                await model.reload();
                return;
            } catch (e) {
                // eslint-disable-next-line no-console
                console.warn("[product_module_hierarchy_reorder] reorder failed, falling back.", e);
                return await this._super(...arguments);
            }
        },
    });
}

