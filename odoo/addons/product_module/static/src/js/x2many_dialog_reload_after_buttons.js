/** @odoo-module **/

/** product_module/static/src/js/x2many_dialog_reload_after_buttons.js
 *
 * Goal: When a Project is opened from an X2Many (Product -> Projects), it is rendered inside
 * `X2ManyFieldDialog`. Server-side buttons that mutate one2many content (materials) should refresh
 * the dialog record WITHOUT navigating to a full-page form and WITHOUT opening a second modal.
 *
 * Implementation: patch `X2ManyFieldDialog.setup()` to register an additional `useViewButtons`
 * handler with an `afterExecuteAction` hook. For specific button names, it calls `this.record.load()`.
 */
import { X2ManyFieldDialog } from "@web/views/fields/relational_utils";
import { FormController } from "@web/views/form/form_controller";
import { useViewButtons } from "@web/views/view_button/view_button_hook";

const PM_RELOAD_BUTTONS = new Set([
    "action_sync_materials_from_arkite",
    "action_fetch_material_images_from_arkite",
]);

try {
    if (!X2ManyFieldDialog.prototype.__pm_reload_after_buttons_patched__) {
        X2ManyFieldDialog.prototype.__pm_reload_after_buttons_patched__ = true;
        const _origSetup = X2ManyFieldDialog.prototype.setup;
        X2ManyFieldDialog.prototype.setup = function () {
            _origSetup.apply(this, arguments);
            useViewButtons(this.modalRef, {
                reload: () => this.record.load(),
                beforeExecuteAction: this.beforeExecuteActionButton.bind(this),
                afterExecuteAction: async (clickParams) => {
                    if (PM_RELOAD_BUTTONS.has(clickParams?.name)) {
                        try {
                            await this.record.load();
                        } catch {
                            // keep UI stable
                        }
                    }
                },
            });
        };
    }
} catch {
    // Defensive: if Odoo internals change, don't brick the backend UI.
}

// Also reload the standard (full-page) project form after these buttons run, since the backend
// no longer returns an act_window refresh.
try {
    if (!FormController.prototype.__pm_reload_after_buttons_patched__) {
        FormController.prototype.__pm_reload_after_buttons_patched__ = true;
        const _origAfter = FormController.prototype.afterExecuteActionButton;
        FormController.prototype.afterExecuteActionButton = async function (clickParams) {
            const res = await _origAfter.apply(this, arguments);
            if (PM_RELOAD_BUTTONS.has(clickParams?.name)) {
                try {
                    await this.model.load();
                } catch {
                    // keep UI stable
                }
            }
            return res;
        };
    }
} catch {
    // Defensive: keep UI stable if Odoo internals change.
}

