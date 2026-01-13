/** @odoo-module **/

import { HierarchyCard } from "@web_hierarchy/hierarchy_card";
import { useState } from "@odoo/owl";

/**
 * Inline child-reorder panel inside the hierarchy diagram card.
 * Avoids view-arch OWL directives by patching the OWL component (assets XML+JS).
 */

function _getM2OId(val) {
    // Odoo read values can be: [id, display_name] or false
    return Array.isArray(val) ? val[0] : val || false;
}

try {
    if (!HierarchyCard.prototype.__pm_inline_reorder_patched__) {
        HierarchyCard.prototype.__pm_inline_reorder_patched__ = true;

        const _origSetup = HierarchyCard.prototype.setup;
        HierarchyCard.prototype.setup = function () {
            _origSetup.apply(this, arguments);
            // Ensure pm exists early so template handlers never resolve to undefined.
            this.pm = useState({
                reorderOpen: false,
                childrenLoading: false,
                children: [],
            });
        };

        HierarchyCard.prototype.pmToggleReorder = async function () {
            this.pm.reorderOpen = !this.pm.reorderOpen;
            if (!this.pm.reorderOpen) {
                return;
            }
            await this.pmLoadChildren();
        };

        HierarchyCard.prototype.pmLoadChildren = async function () {
            const orm = this.env.services.orm;
            const node = this.props.node;
            const data = (node && node.data) || {};
            const projectId = _getM2OId(data.project_id);
            const processId = data.process_id || false;

            if (!projectId) {
                return;
            }
            this.pm.childrenLoading = true;
            try {
                const domain = [["parent_id", "=", node.resId], ["project_id", "=", projectId]];
                if (processId) {
                    domain.push(["process_id", "=", processId]);
                }
                const children = await orm.searchRead(
                    node.model.resModel,
                    domain,
                    ["id", "sequence", "step_name"],
                    {
                        order: "sequence,id",
                        context: {
                            ...(node.model.context || {}),
                            defer_arkite_sync: true,
                            pm_list_resequence: true,
                        },
                    }
                );
                this.pm.children = children || [];
            } finally {
                this.pm.childrenLoading = false;
            }
        };

        HierarchyCard.prototype.pmMoveChildUp = function (ev) {
            const id = Number(ev.currentTarget?.dataset?.id);
            if (id) {
                return this.pmMoveChild(id, "up");
            }
        };

        HierarchyCard.prototype.pmMoveChildDown = function (ev) {
            const id = Number(ev.currentTarget?.dataset?.id);
            if (id) {
                return this.pmMoveChild(id, "down");
            }
        };

        HierarchyCard.prototype.pmMoveChild = async function (childId, direction) {
            const notification = this.env.services.notification;
            try {
                const orm = this.env.services.orm;
                const node = this.props.node;
                const ctx = {
                    ...(node.model.context || {}),
                    defer_arkite_sync: true,
                    pm_list_resequence: true,
                };

                const list = this.pm.children || [];
                const idx = list.findIndex((c) => c.id === childId);
                if (idx < 0) return;
                const newIdx =
                    direction === "up"
                        ? Math.max(0, idx - 1)
                        : Math.min(list.length - 1, idx + 1);
                if (newIdx === idx) return;

                // Reorder locally
                const next = list.slice();
                const [moved] = next.splice(idx, 1);
                next.splice(newIdx, 0, moved);

                // Persist: rewrite sequences in order (spaced by 10)
                let seq = 10;
                for (const rec of next) {
                    await orm.write(node.model.resModel, [rec.id], { sequence: seq }, { context: ctx });
                    seq += 10;
                }

                // Reload both the panel list and the diagram so it reflects the new order
                await this.pmLoadChildren();
                await node.model.reload();
                notification.add("Child order updated", { type: "success" });
            } catch (e) {
                // eslint-disable-next-line no-console
                console.warn("[product_module] inline child reorder failed", e);
                notification.add(
                    (e && (e.message || e.name)) || "Reorder failed (see console)",
                    { type: "danger", sticky: true }
                );
            }
        };
    }
} catch (e) {
    // eslint-disable-next-line no-console
    console.warn("[product_module] hierarchy inline reorder patch disabled.", e);
}

