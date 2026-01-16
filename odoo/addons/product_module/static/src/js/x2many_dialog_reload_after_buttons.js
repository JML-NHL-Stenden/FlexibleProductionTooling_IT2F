/** @odoo-module **/

// Reload the current Project record after specific server-side buttons execute.
// This avoids returning act_window actions from Python (which breaks out of modals and opens full page).

import { X2ManyFieldDialog } from "@web/views/fields/relational_utils";
import { FormController } from "@web/views/form/form_controller";
import { useViewButtons } from "@web/views/view_button/view_button_hook";

const PM_RELOAD_BUTTONS = new Set([
    "action_sync_materials_from_arkite",
    "action_fetch_material_images_from_arkite",
    "action_sync_staged_hierarchy_to_arkite",
]);

// X2Many dialog (Product -> Projects)
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
    // keep UI stable
}

// Standard full-page form
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
    // keep UI stable
}
