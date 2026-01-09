/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { HierarchyRenderer } from "@web_hierarchy/hierarchy_renderer";

/**
 * Enable sibling reordering (A↔B) in web_hierarchy by writing `sequence` when the user drops
 * onto a non-COMPOSITE node.
 *
 * Rule:
 * - Drop onto COMPOSITE node => make dragged node a child (default web_hierarchy behavior)
 * - Drop onto non-COMPOSITE node => reorder (and reparent to the target's parent) by writing:
 *     parentFieldName + sequence
 *
 * This keeps parenting explicit (COMPOSITE only) and makes A↔B reorder possible without changing Odoo core.
 */
patch(HierarchyRenderer.prototype, "product_module.web_hierarchy.diagram_reorder", {
    async nodeDrop({ element, row, nextRow, newParentNode }) {
        try {
            // If dropped onto a node element, decide between "reorder" vs "make child".
            if (newParentNode) {
                const model = this.props.model;
                const root = model?.root;
                const dragNodeId = element?.dataset?.nodeId;
                const targetNodeId = newParentNode?.dataset?.nodeId;
                const dragNode = dragNodeId && root?.nodePerNodeId?.[dragNodeId];
                const targetNode = targetNodeId && root?.nodePerNodeId?.[targetNodeId];

                // Only COMPOSITE should act as a parent target. Everything else becomes a reorder target.
                const targetType = targetNode?.data?.step_type;
                const isCompositeTarget = targetType === "COMPOSITE";
                if (dragNode && targetNode && !isCompositeTarget) {
                    const orm = this.env?.services?.orm;
                    if (!orm) {
                        return await this._super({ element, row, nextRow, newParentNode });
                    }
                    const parentFieldName = model.parentFieldName || "parent_id";
                    const desiredParentResId = targetNode.parentResId || false;
                    const targetSeq = Number(targetNode.data?.sequence || 10);
                    // Place before target by using a slightly smaller sequence; server normalizes ties.
                    let newSeq = targetSeq - 5;
                    if (!Number.isFinite(newSeq) || newSeq <= 0) {
                        newSeq = Math.max(1, targetSeq - 1);
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
                }
            }
        } catch (e) {
            // Never brick the UI: fall back to core behavior on any error.
            // eslint-disable-next-line no-console
            console.warn("[product_module] hierarchy reorder patch failed, falling back:", e);
        }

        return await this._super({ element, row, nextRow, newParentNode });
    },
});

