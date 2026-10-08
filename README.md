script 1:
```py
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


LOOKUP_KINDS = [
    ("handover_scope", "Handover Scope / Package"),
    ("handover_quantity_scope", "Handover Quantity / Scope"),
    ("handover_completion_status", "Handover Completion Status"),
    ("payment_milestone", "Payment Milestone"),
    ("spec_status", "Spec Sheet Status"),
    ("spec_revision", "Spec Sheet Revision"),
    ("spec_revision_status", "Spec Sheet Revision Status"),
    ("procurement_group", "Procurement Group"),
    ("procurement_category", "Procurement Category"),
    ("procurement_subcategory", "Procurement Sub-Category"),
    ("spec_uom", "Spec Sheet Unit of Measure"),
    ("preproduction_approval", "Pre-Production Approval"),
    ("spec_approval_status", "Spec Sheet Approval Status"),
    ("installation_status", "Installation Status"),
    ("installation_task_floor", "Installation Task / Floor"),
    ("installation_line_status", "Installation Line Status"),
    ("snag_room", "Snag Room / Unit"),
    ("snag_category", "Snag Category"),
    ("snag_responsible_party", "Snag Responsible Party"),
    ("snag_progress_stage", "Snag Progress Stage"),
    ("snag_progress_status", "Snag Progress Status"),
]

SNAG_STATUS_SELECTION = [
    ("open", "Open"),
    ("assigned", "Assigned"),
    ("in_progress", "In Progress"),
    ("resolved", "Resolved"),
    ("verified", "Verified"),
    ("closed", "Closed"),
]


class TfcProjectDocumentLookup(models.Model):
    _name = "tfc.project.document.lookup"
    _inherit = "tfc.configuration.mixin"
    _description = "TFC Project Document Dropdown"

    kind = fields.Selection(LOOKUP_KINDS, required=True, index=True)
    parent_id = fields.Many2one(
        "tfc.project.document.lookup", string="Parent", ondelete="restrict"
    )

    _tfc_document_lookup_unique = models.Constraint(
        "UNIQUE(kind, name)", "A dropdown value can only appear once in its category."
    )


class TfcProjectDocumentMixin(models.AbstractModel):
    _name = "tfc.project.document.mixin"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _description = "TFC Project Document Mixin"
    _order = "id desc"

    name = fields.Char(required=True, copy=False, readonly=True, default=lambda self: _("New"))
    project_id = fields.Many2one(
        "project.project", required=True, ondelete="cascade", index=True, tracking=True
    )
    company_id = fields.Many2one(
        related="project_id.company_id", store=True, readonly=True, index=True
    )
    currency_id = fields.Many2one(related="project_id.currency_id", readonly=True)
    partner_id = fields.Many2one(
        related="project_id.partner_id", string="Client", store=True, readonly=True
    )
    project_number = fields.Char(
        related="project_id.tfc_project_number", string="Project Number", store=True, readonly=True
    )
    project_location = fields.Char(
        related="project_id.tfc_project_location", string="Project Location", readonly=True
    )

    _sequence_code = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(self._sequence_code) or _("New")
        records = super().create(vals_list)
        records._tfc_link_project_attachments()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "attachment_ids" in vals or "project_id" in vals:
            self._tfc_link_project_attachments()
        return result

    def _tfc_link_project_attachments(self):
        """Make document uploads visible in the project's standard attachment area."""
        for document in self:
            if "attachment_ids" not in document._fields or not document.project_id:
                continue
            uploads = document.attachment_ids.filtered(
                lambda attachment: not attachment.res_model
                or (
                    attachment.res_model == document._name
                    and attachment.res_id in (False, document.id)
                )
            )
            uploads.sudo().write({
                "res_model": "project.project", "res_id": document.project_id.id,
            })

    def action_print(self):
        self.ensure_one()
        return self.env.ref(self._report_xmlid).report_action(self)


class TfcPaymentCertificate(models.Model):
    _name = "tfc.payment.certificate"
    _inherit = "tfc.project.document.mixin"
    _description = "TFC Payment Certificate"
    _sequence_code = "tfc.payment.certificate"
    _report_xmlid = "tfc_crm_project.action_report_tfc_payment_certificate"

    certificate_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    attention_partner_id = fields.Many2one("res.partner", string="Attention")
    contractor_id = fields.Many2one("res.partner", string="Contractor")
    contractor_address = fields.Text(string="Contractor Address")
    contractor_telephone = fields.Char(string="Contractor Telephone")
    contractor_facsimile = fields.Char(string="Contractor Facsimile")
    contractor_vat_number = fields.Char(string="Contractor VAT Registration No.")
    contract_reference = fields.Char(string="Contract")
    contract_area = fields.Char(string="Contract Area")
    contract_sum = fields.Monetary(string="Contract Sum (Excl. VAT)")
    bbbee_score = fields.Char(string="B-BBEE Score")
    valuation_number = fields.Char(string="Valuation")
    valuation_type = fields.Char(string="Valuation Type", default="Interim")
    line_ids = fields.One2many(
        "tfc.payment.certificate.line", "certificate_id", string="Certificate Lines", copy=True
    )
    spec_sheet_ids = fields.Many2many(
        "tfc.spec.sheet", string="Spec Sheets", domain="[('project_id', '=', project_id)]"
    )
    total_claim_subtotal = fields.Monetary(
        string="Total Claim Subtotal", compute="_compute_totals"
    )
    previously_certified_subtotal = fields.Monetary(
        string="Previously Certified Subtotal", compute="_compute_totals"
    )
    subtotal = fields.Monetary(string="Due Subtotal", compute="_compute_totals")
    vat_rate = fields.Float(string="VAT %", default=15.0, required=True, readonly=True)
    vat_amount = fields.Monetary(compute="_compute_totals")
    amount_due = fields.Monetary(string="Total Amount Due", compute="_compute_totals")
    bank_name = fields.Char()
    bank_branch_code = fields.Char(string="Branch Code")
    bank_account_number = fields.Char(string="Account Number")
    tfc_signatory = fields.Char(string="TFC Signatory")
    contractor_signatory = fields.Char()
    client_signatory = fields.Char()
    commercial_mode = fields.Selection(related="project_id.tfc_commercial_mode", readonly=True)

    @api.depends(
        "line_ids.total_claim", "line_ids.previously_certified", "line_ids.amount_due", "vat_rate"
    )
    def _compute_totals(self):
        for certificate in self:
            certificate.total_claim_subtotal = sum(certificate.line_ids.mapped("total_claim"))
            certificate.previously_certified_subtotal = sum(
                certificate.line_ids.mapped("previously_certified")
            )
            certificate.subtotal = sum(certificate.line_ids.mapped("amount_due"))
            certificate.vat_amount = (
                certificate.total_claim_subtotal * certificate.vat_rate / 100.0
            )
            certificate.amount_due = certificate.total_claim_subtotal + certificate.vat_amount

    @api.constrains("vat_rate")
    def _check_vat_rate(self):
        if any(certificate.vat_rate != 15.0 for certificate in self):
            raise ValidationError(_("Payment Certificate VAT must remain fixed at 15%."))

    @api.onchange("contractor_id")
    def _onchange_contractor_id(self):
        if self.contractor_id:
            self.contractor_address = self.contractor_id.contact_address
            self.contractor_telephone = self.contractor_id.phone
            self.contractor_vat_number = self.contractor_id.vat


class TfcPaymentCertificateLine(models.Model):
    _name = "tfc.payment.certificate.line"
    _description = "TFC Payment Certificate Line"
    _order = "id"

    certificate_id = fields.Many2one(
        "tfc.payment.certificate", required=True, ondelete="cascade", index=True
    )
    project_id = fields.Many2one(related="certificate_id.project_id", store=True, index=True)
    company_id = fields.Many2one(related="certificate_id.company_id", store=True, index=True)
    currency_id = fields.Many2one(related="certificate_id.currency_id")
    invoice_id = fields.Many2one(
        "account.move",
        string="Invoice Number",
        domain="[('tfc_project_id', '=', project_id), ('move_type', 'in', ('in_invoice', 'out_invoice'))]",
    )
    purchase_order_ids = fields.Many2many(
        "purchase.order",
        "tfc_payment_certificate_line_purchase_rel",
        "line_id",
        "purchase_order_id",
        string="Order Numbers",
        domain="[('project_id', '=', project_id)]",
    )
    total_claim = fields.Monetary(string="Total Claim", required=True)
    previously_certified = fields.Monetary(
        compute="_compute_previously_certified",
        string="Previously Certified",
    )
    amount_due = fields.Monetary(
        string="Due as per This Certificate", compute="_compute_amount_due"
    )

    @api.depends(
        "certificate_id.project_id",
        "certificate_id.certificate_date",
        "invoice_id",
        "purchase_order_ids",
    )
    def _compute_previously_certified(self):
        for line in self:
            line.previously_certified = line._tfc_get_previously_certified_amount()

    def _tfc_get_previously_certified_amount(self):
        self.ensure_one()
        certificate = self.certificate_id
        if not certificate.project_id:
            return 0.0
        domain = [
            ("certificate_id.project_id", "=", certificate.project_id.id),
            ("certificate_id.id", "!=", certificate.id or 0),
        ]
        if certificate.certificate_date:
            domain += [
                "|",
                ("certificate_id.certificate_date", "<", certificate.certificate_date),
                "&",
                ("certificate_id.certificate_date", "=", certificate.certificate_date),
                ("certificate_id.id", "<", certificate.id or 0),
            ]
        elif certificate.id:
            domain.append(("certificate_id.id", "<", certificate.id))
        if self.purchase_order_ids:
            domain.append(("purchase_order_ids", "in", self.purchase_order_ids.ids))
        elif self.invoice_id:
            domain.append(("invoice_id", "=", self.invoice_id.id))
        else:
            domain += [
                ("purchase_order_ids", "=", False),
                ("invoice_id", "=", False),
            ]
        previous_lines = self.search(domain, order="certificate_id asc, id asc")
        return sum(previous_lines.mapped("amount_due"))

    @api.depends("total_claim", "previously_certified")
    def _compute_amount_due(self):
        for line in self:
            line.amount_due = line.total_claim - line.previously_certified


class TfcSpecSheet(models.Model):
    _name = "tfc.spec.sheet"
    _inherit = "tfc.project.document.mixin"
    _description = "TFC Project Specification Sheet"
    _sequence_code = "tfc.spec.sheet"
    _report_xmlid = "tfc_crm_project.action_report_tfc_spec_sheet"

    item_code = fields.Char(string="Item / Spec Code", tracking=True)
    status_id = fields.Many2one(
        "tfc.project.document.lookup", string="Spec Status",
        domain="[('kind', '=', 'spec_status')]", tracking=True,
        default=lambda self: self.env.ref(
            "tfc_crm_project.lookup_spec_status_draft", raise_if_not_found=False
        )
    )
    revision_id = fields.Many2one(
        "tfc.project.document.lookup", string="Revision No.",
        domain="[('kind', '=', 'spec_revision')]", tracking=True,
        default=lambda self: self.env.ref(
            "tfc_crm_project.lookup_revision_01", raise_if_not_found=False
        )
    )
    revision_date = fields.Date(default=fields.Date.context_today, tracking=True)
    revision_description = fields.Text(string="Revision Description / Reason", tracking=True)
    revision_status_id = fields.Many2one(
        "tfc.project.document.lookup", string="Revision Status",
        domain="[('kind', '=', 'spec_revision_status')]", tracking=True,
        default=lambda self: self.env.ref(
            "tfc_crm_project.lookup_revision_status_current", raise_if_not_found=False
        )
    )
    prepared_by_id = fields.Many2one(
        "res.users", string="Prepared By", default=lambda self: self.env.user, readonly=True
    )
    date_prepared = fields.Date(default=fields.Date.context_today)
    required_by_date = fields.Date()
    area_id = fields.Many2one(
        "tfc.project.area",
        string="Area",
        tracking=True,
        ondelete="restrict",
        domain="[('id', 'in', area_ids)]",
    )
    sub_area_id = fields.Many2one(
        "tfc.project.sub.area",
        string="Sub Area",
        tracking=True,
        ondelete="restrict",
        domain="[('area_id', '=', area_id), ('id', 'in', sub_area_ids)]",
    )
    area_ids = fields.Many2many(related="project_id.tfc_area_ids", readonly=True)
    sub_area_ids = fields.Many2many(related="project_id.tfc_sub_area_ids", readonly=True)
    room_unit_number = fields.Char(string="Room / Unit No.")
    project_comments = fields.Text(string="Project Comments")
    procurement_group_id = fields.Many2one(
        "tfc.project.document.lookup", string="Procurement Group",
        domain="[('kind', '=', 'procurement_group')]"
    )
    category_id = fields.Many2one(
        "tfc.project.document.lookup", string="Category",
        domain="[('kind', '=', 'procurement_category')]"
    )
    subcategory_id = fields.Many2one(
        "tfc.project.document.lookup", string="Sub-Category",
        domain="[('kind', '=', 'procurement_subcategory'), ('parent_id', 'in', [False, category_id])]"
    )
    product_id = fields.Many2one("product.product", string="Product", ondelete="restrict")
    quantity = fields.Float(default=1.0)
    uom_id = fields.Many2one(
        "tfc.project.document.lookup", string="UoM", domain="[('kind', '=', 'spec_uom')]"
    )
    detailed_specification = fields.Text()
    drawing_reference = fields.Char(string="Reference / Drawing No.")
    attachment_ids = fields.Many2many("ir.attachment", string="Supporting Attachments")
    notes = fields.Text(string="Notes / Special Instructions")
    approval_required_id = fields.Many2one(
        "tfc.project.document.lookup", string="Approval Required",
        domain="[('kind', '=', 'preproduction_approval')]"
    )
    approval_status_id = fields.Many2one(
        "tfc.project.document.lookup", string="Approval Status",
        domain="[('kind', '=', 'spec_approval_status')]"
    )
    approved_by_id = fields.Many2one(
        "res.users", string="Pre-Production Approved By",
        default=lambda self: self.env.user, readonly=True
    )
    approval_date = fields.Date(string="Pre-Production Approval Date")
    design_contact_id = fields.Many2one("res.partner", string="Design Queries — Contact")
    design_email = fields.Char(related="design_contact_id.email", string="Design Queries — Email")
    design_phone = fields.Char(related="design_contact_id.phone", string="Design Queries — Telephone")
    procurement_contact_id = fields.Many2one(
        "res.partner", string="Procurement Queries — Contact"
    )
    procurement_email = fields.Char(
        related="procurement_contact_id.email", string="Procurement Queries — Email"
    )
    procurement_phone = fields.Char(
        related="procurement_contact_id.phone", string="Procurement Queries — Telephone"
    )
    signoff_user_id = fields.Many2one(
        "res.users", string="Spec Sheet Approved By",
        default=lambda self: self.env.user, readonly=True
    )
    signoff_date = fields.Date(string="Spec Sheet Approval Date")
    approval_comments = fields.Text()
    disclaimer = fields.Text(
        default="This Spec Sheet must be read in conjunction with any referenced drawings or "
        "specifications. The supplier must confirm suitability for the intended use before "
        "accepting an order. This document does not constitute a Purchase Order. Any discrepancy, "
        "inconsistency or unclear information must be clarified with TFC before manufacture or supply."
    )
    revision_line_ids = fields.One2many(
        "tfc.spec.sheet.revision", "spec_sheet_id", string="Revision History", copy=True
    )
    commercial_mode = fields.Selection(related="project_id.tfc_commercial_mode", readonly=True)
    superseded_by_revision_id = fields.Many2one(
        "tfc.project.document.lookup",
        string="Superseded by Revision",
        domain="[('kind', '=', 'spec_revision')]",
        tracking=True,
    )
    superseded_by_spec_sheet_id = fields.Many2one(
        "tfc.spec.sheet",
        string="Superseded by Spec Sheet",
        domain="[('project_id', '=', project_id), ('id', '!=', id)]",
        tracking=True,
        ondelete="restrict",
    )
    purchase_order_ids = fields.Many2many(
        "purchase.order", compute="_compute_traceability", compute_sudo=True,
        string="RFQs / Purchase Orders"
    )
    sale_order_ids = fields.Many2many(
        "sale.order", compute="_compute_traceability", compute_sudo=True,
        string="Sales Orders"
    )
    invoice_ids = fields.Many2many(
        "account.move", compute="_compute_traceability", compute_sudo=True,
        string="Supplier / Customer Invoices"
    )
    picking_ids = fields.Many2many(
        "stock.picking", compute="_compute_traceability", compute_sudo=True,
        string="Deliveries / GRNs / PODs"
    )
    payment_certificate_ids = fields.Many2many(
        "tfc.payment.certificate",
        compute="_compute_traceability",
        compute_sudo=True,
        string="Payment Certificates",
    )
    payment_ids = fields.Many2many(
        "account.payment",
        compute="_compute_traceability",
        compute_sudo=True,
        string="Payments / POP",
    )
    installation_ids = fields.Many2many(
        "tfc.installation",
        compute="_compute_traceability",
        compute_sudo=True,
        string="Installations",
    )
    snag_ids = fields.Many2many(
        "tfc.snag",
        compute="_compute_traceability",
        compute_sudo=True,
        string="Snags",
    )
    handover_certificate_ids = fields.Many2many(
        "tfc.handover.certificate",
        compute="_compute_traceability",
        compute_sudo=True,
        string="Handover Certificates",
    )

    def _compute_traceability(self):
        Purchase = self.env["purchase.order"]
        Sale = self.env["sale.order"]
        Move = self.env["account.move"]
        Picking = self.env["stock.picking"]
        Certificate = self.env["tfc.payment.certificate"]
        Installation = self.env["tfc.installation"]
        Snag = self.env["tfc.snag"]
        Handover = self.env["tfc.handover.certificate"]
        for spec in self:
            spec.purchase_order_ids = Purchase.search([("tfc_spec_sheet_ids", "in", spec.id)])
            spec.sale_order_ids = Sale.search([("tfc_spec_sheet_ids", "in", spec.id)])
            spec.invoice_ids = Move.search([("tfc_spec_sheet_ids", "in", spec.id)])
            spec.picking_ids = Picking.search([("tfc_spec_sheet_ids", "in", spec.id)])
            spec.payment_certificate_ids = Certificate.search(
                [("spec_sheet_ids", "in", spec.id)]
            )
            spec.payment_ids = spec.invoice_ids.mapped("reconciled_payment_ids")
            spec.installation_ids = Installation.search(
                [("line_ids.spec_sheet_id", "=", spec.id)]
            )
            spec.snag_ids = Snag.search([("spec_sheet_id", "=", spec.id)])
            spec.handover_certificate_ids = Handover.search(
                [("spec_sheet_ids", "in", spec.id)]
            )

    @api.model_create_multi
    def create(self, vals_list):
        projects = {
            project.id: project
            for project in self.env["project.project"].browse(
                {vals.get("project_id") for vals in vals_list if vals.get("project_id")}
            ).exists()
        }
        for vals in vals_list:
            project = projects.get(vals.get("project_id"))
            if project:
                if "area_id" not in vals:
                    vals["area_id"] = project.tfc_area_id.id
                if "sub_area_id" not in vals:
                    vals["sub_area_id"] = (
                        project.tfc_sub_area_id.id
                        if vals.get("area_id") == project.tfc_area_id.id
                        else False
                    )
        records = super().create(vals_list)
        for record in records.filtered(lambda spec: not spec.item_code):
            record.item_code = record.name
        for record in records.filtered("revision_id"):
            if not record.revision_line_ids:
                self.env["tfc.spec.sheet.revision"].create({
                    "spec_sheet_id": record.id,
                    "revision": record.revision_id.name,
                    "revision_date": record.revision_date or fields.Date.context_today(record),
                    "description": record.revision_description or _("Initial Issue"),
                })
        records._tfc_sync_po_budget_line()
        return records

    def write(self, vals):
        if vals.get("project_id"):
            project = self.env["project.project"].browse(vals["project_id"])
            if "area_id" not in vals:
                vals["area_id"] = project.tfc_area_id.id
            if "sub_area_id" not in vals:
                vals["sub_area_id"] = (
                    project.tfc_sub_area_id.id
                    if vals.get("area_id") == project.tfc_area_id.id
                    else False
                )
        elif "area_id" in vals and "sub_area_id" not in vals:
            vals["sub_area_id"] = False
        previous_revisions = {record.id: record.revision_id for record in self}
        result = super().write(vals)
        if "revision_id" in vals:
            for record in self.filtered("revision_id"):
                if previous_revisions[record.id] != record.revision_id:
                    self.env["tfc.spec.sheet.revision"].create({
                        "spec_sheet_id": record.id,
                        "previous_revision": previous_revisions[record.id].name,
                        "revision": record.revision_id.name,
                        "revision_date": record.revision_date or fields.Date.context_today(record),
                        "description": record.revision_description or _("Revision updated"),
                    })
        if (
            not self.env.context.get("tfc_skip_po_budget_sync")
            and {"project_id", "area_id", "sub_area_id", "product_id", "quantity"} & set(vals)
        ):
            self._tfc_sync_po_budget_line()
        return result

    @api.onchange("project_id")
    def _onchange_project_id_set_budget_area(self):
        for spec in self:
            spec.area_id = spec.project_id.tfc_area_id
            spec.sub_area_id = spec.project_id.tfc_sub_area_id

    @api.onchange("area_id")
    def _onchange_area_id_set_budget_sub_area(self):
        for spec in self:
            if spec.sub_area_id.area_id != spec.area_id:
                spec.sub_area_id = False

    @api.constrains("project_id", "area_id", "sub_area_id")
    def _check_budget_area_selection(self):
        for spec in self:
            if spec.area_id and spec.area_id not in spec.project_id.tfc_area_ids:
                raise ValidationError(_("The selected Area is not configured on the project."))
            if spec.sub_area_id and (
                spec.sub_area_id.area_id != spec.area_id
                or spec.sub_area_id not in spec.project_id.tfc_sub_area_ids
            ):
                raise ValidationError(
                    _("The selected Sub Area must belong to the selected project Area.")
                )

    def _tfc_sync_po_budget_line(self):
        Budget = self.env["tfc.project.po.budget"]
        for spec in self:
            if not spec.project_id or not spec.product_id:
                continue
            values = {
                "project_id": spec.project_id.id,
                "product_id": spec.product_id.id,
                "area_id": spec.area_id.id or False,
                "sub_area_id": spec.sub_area_id.id or False,
                "quantity": spec.quantity,
            }
            budget = Budget.search([("spec_sheet_id", "=", spec.id)], limit=1)
            if not budget:
                budget = Budget.search([
                    ("spec_sheet_id", "=", False),
                    ("project_id", "=", spec.project_id.id),
                    ("product_id", "=", spec.product_id.id),
                    ("area_id", "=", spec.area_id.id or False),
                    ("sub_area_id", "=", spec.sub_area_id.id or False),
                ], limit=1)
            if budget:
                budget.write(dict(values, spec_sheet_id=spec.id))
            else:
                Budget.create(dict(values, spec_sheet_id=spec.id, budget_amount=0.0))
        return True

    @api.model
    def _tfc_backfill_po_budget_lines(self):
        specs = self.search([])
        for spec in specs:
            defaults = {}
            if not spec.area_id:
                defaults["area_id"] = spec.project_id.tfc_area_id.id
            if not spec.sub_area_id:
                defaults["sub_area_id"] = spec.project_id.tfc_sub_area_id.id
            if defaults:
                spec.with_context(tfc_skip_po_budget_sync=True).write(defaults)
        specs._tfc_sync_po_budget_line()
        return True

    @api.onchange("category_id")
    def _onchange_category_id(self):
        if self.subcategory_id.parent_id and self.subcategory_id.parent_id != self.category_id:
            self.subcategory_id = False


class TfcSpecSheetRevision(models.Model):
    _name = "tfc.spec.sheet.revision"
    _description = "TFC Spec Sheet Revision"
    _order = "revision_date desc, id desc"

    spec_sheet_id = fields.Many2one("tfc.spec.sheet", required=True, ondelete="cascade")
    project_id = fields.Many2one(related="spec_sheet_id.project_id", store=True, index=True)
    company_id = fields.Many2one(related="spec_sheet_id.company_id", store=True, index=True)
    revision = fields.Char(required=True)
    previous_revision = fields.Char()
    revision_date = fields.Date(default=fields.Date.context_today, required=True)
    description = fields.Char(required=True)
    changed_by_id = fields.Many2one("res.users", default=lambda self: self.env.user, readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("spec_sheet_id") and "previous_revision" not in vals:
                previous = self.search(
                    [("spec_sheet_id", "=", vals["spec_sheet_id"])],
                    order="id desc", limit=1,
                )
                vals["previous_revision"] = previous.revision or False
        return super().create(vals_list)


class TfcInstallation(models.Model):
    _name = "tfc.installation"
    _inherit = "tfc.project.document.mixin"
    _description = "TFC Installation Record"
    _sequence_code = "tfc.installation"
    _report_xmlid = "tfc_crm_project.action_report_tfc_installation"

    installation_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    status_id = fields.Many2one(
        "tfc.project.document.lookup", string="Status",
        domain="[('kind', '=', 'installation_status')]", tracking=True,
        default=lambda self: self.env.ref(
            "tfc_crm_project.lookup_installation_planned", raise_if_not_found=False
        )
    )
    task_floor_id = fields.Many2one(
        "tfc.project.document.lookup", string="Task / Floor",
        domain="[('kind', '=', 'installation_task_floor')]"
    )
    receipt_ids = fields.Many2many(
        "stock.picking", string="Related GRN / Receipt Ref(s)",
        domain="[('purchase_id.project_id', '=', project_id), ('picking_type_code', '=', 'incoming'), ('state', '=', 'done')]"
    )
    purchase_order_ids = fields.Many2many(
        "purchase.order", compute="_compute_purchase_order_ids", string="Project Purchase Orders"
    )

    @api.depends("project_id")
    def _compute_purchase_order_ids(self):
        for installation in self:
            installation.purchase_order_ids = self.env["purchase.order"].search([
                ("project_id", "=", installation.project_id.id),
                ("state", "in", ("purchase", "done")),
            ]) if installation.project_id else False

    installation_location = fields.Char(string="Delivery / Installation Location")
    supervisor_id = fields.Many2one(
        "res.users", string="TFC Installation Supervisor / Contact",
        default=lambda self: self.env.user, required=True
    )
    line_ids = fields.One2many("tfc.installation.line", "installation_id", copy=True)
    qc_checked_by_id = fields.Many2one("res.users", string="Quality Control Check By")
    qc_check_date = fields.Date(string="Quality Control Check Date")
    qc_result = fields.Selection(
        [("passed", "Passed"), ("snag_raised", "Snag Raised")], string="Quality Control Result"
    )


class TfcInstallationLine(models.Model):
    _name = "tfc.installation.line"
    _description = "TFC Installation Product Line"
    _order = "id"

    installation_id = fields.Many2one("tfc.installation", required=True, ondelete="cascade")
    project_id = fields.Many2one(related="installation_id.project_id", store=True, index=True)
    company_id = fields.Many2one(related="installation_id.company_id", store=True, index=True)
    spec_sheet_id = fields.Many2one(
        "tfc.spec.sheet", string="Spec Sheet", domain="[('project_id', '=', project_id)]"
    )
    product_id = fields.Many2one(
        "product.product", string="Product Ref. Number", required=True, ondelete="restrict"
    )
    product_reference = fields.Char(
        related="product_id.default_code", string="Internal Reference"
    )
    product_name = fields.Char(related="product_id.name", string="Product", readonly=True)
    area_id = fields.Many2one(related="project_id.tfc_area_id", readonly=True)
    sub_area_id = fields.Many2one(related="project_id.tfc_sub_area_id", readonly=True)
    room_unit_reference = fields.Char(string="Room / Unit Ref.")
    quantity_available = fields.Float(compute="_compute_quantities", string="Qty Available")
    quantity_installed = fields.Float(string="Qty Installed This Record", required=True)
    balance_remaining = fields.Float(compute="_compute_quantities")
    status_id = fields.Many2one(
        "tfc.project.document.lookup", string="Installation Status",
        domain="[('kind', '=', 'installation_line_status')]",
        default=lambda self: self.env.ref(
            "tfc_crm_project.lookup_install_line_not_started", raise_if_not_found=False
        )
    )
    snag_raised = fields.Selection([("yes", "Yes"), ("no", "No")], default="no")
    snag_id = fields.Many2one("tfc.snag", string="Snag Ref.", ondelete="set null")
    notes = fields.Text()

    @api.onchange("spec_sheet_id")
    def _onchange_spec_sheet_id(self):
        if self.spec_sheet_id.product_id:
            self.product_id = self.spec_sheet_id.product_id

    def action_create_snag(self):
        self.ensure_one()
        if self.snag_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "tfc.snag",
                "res_id": self.snag_id.id,
                "view_mode": "form",
                "target": "current",
            }
        snag = self.env["tfc.snag"].create({
            "project_id": self.project_id.id,
            "installation_id": self.installation_id.id,
            "installation_line_id": self.id,
            "spec_sheet_id": self.spec_sheet_id.id,
            "area_ids": [(6, 0, self.area_id.ids)],
            "sub_area_ids": [(6, 0, self.sub_area_id.ids)],
            "room_unit_number": self.room_unit_reference,
            "description": self.notes or self.product_name or _("Installation snag"),
        })
        self.write({"snag_raised": "yes", "snag_id": snag.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": "tfc.snag",
            "res_id": snag.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.depends(
        "project_id.tfc_purchase_order_ids.state",
        "project_id.tfc_purchase_order_ids.order_line.product_qty",
        "product_id",
        "quantity_installed",
    )
    def _compute_quantities(self):
        PurchaseLine = self.env["purchase.order.line"]
        InstallationLine = self.env["tfc.installation.line"]
        for line in self:
            purchased = sum(PurchaseLine.search([
                ("order_id.project_id", "=", line.project_id.id),
                ("order_id.state", "in", ("purchase", "done")),
                ("product_id", "=", line.product_id.id),
                ("display_type", "=", False),
            ]).mapped("product_qty")) if line.project_id and line.product_id else 0.0
            installed = sum(InstallationLine.search([
                ("project_id", "=", line.project_id.id),
                ("product_id", "=", line.product_id.id),
                ("id", "!=", line.id),
            ]).mapped("quantity_installed")) + line.quantity_installed
            line.quantity_available = purchased
            line.balance_remaining = purchased - installed

    @api.constrains("quantity_installed")
    def _check_quantity_installed(self):
        if any(line.quantity_installed < 0 for line in self):
            raise ValidationError(_("Installed quantity cannot be negative."))


class TfcSnag(models.Model):
    _name = "tfc.snag"
    _inherit = "tfc.project.document.mixin"
    _description = "TFC Project Snag"
    _sequence_code = "tfc.snag"
    _report_xmlid = "tfc_crm_project.action_report_tfc_snag"

    date_raised = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    installation_id = fields.Many2one(
        "tfc.installation", domain="[('project_id', '=', project_id)]", tracking=True
    )
    task_floor_ids = fields.Many2many(
        "tfc.project.document.lookup",
        "tfc_snag_task_floor_rel",
        "snag_id",
        "lookup_id",
        string="Task / Floor",
        domain="[('kind', '=', 'installation_task_floor')]"
    )
    area_ids = fields.Many2many("tfc.project.area", string="Areas")
    sub_area_ids = fields.Many2many("tfc.project.sub.area", string="Sub Areas")
    room_unit_number = fields.Char(string="Room / Unit No.")
    room_unit_ids = fields.Many2many(
        "tfc.project.document.lookup",
        "tfc_snag_room_unit_rel",
        "snag_id",
        "lookup_id",
        string="Room / Unit",
        domain="[('kind', '=', 'snag_room')]",
    )
    installation_line_id = fields.Many2one(
        "tfc.installation.line", string="Installation Item",
        domain="[('installation_id', '=', installation_id)]"
    )
    item_number_description = fields.Char(string="Item No. / Description")

    @api.onchange("installation_line_id")
    def _onchange_installation_line_id(self):
        if self.installation_line_id:
            line = self.installation_line_id
            self.item_number_description = line.product_reference or line.product_name

    spec_sheet_id = fields.Many2one(
        "tfc.spec.sheet", string="Spec Sheet No.", domain="[('project_id', '=', project_id)]"
    )
    raised_by_id = fields.Many2one(
        "res.users", string="Raised By", default=lambda self: self.env.user, readonly=True
    )
    description = fields.Text(string="Snag Description", required=True, tracking=True)
    required_action = fields.Text()
    category = fields.Selection([
        ("damaged", "Damaged"), ("defective", "Defective"),
        ("incorrect_specification", "Incorrect Specification"),
        ("incorrect_quantity", "Incorrect Quantity"), ("missing", "Missing"),
        ("installation", "Installation"), ("workmanship", "Workmanship"),
        ("incomplete", "Incomplete"), ("other", "Other"),
    ], string="Legacy Category", tracking=True)
    category_id = fields.Many2one(
        "tfc.project.document.lookup",
        string="Category",
        domain="[('kind', '=', 'snag_category')]",
        tracking=True,
    )

    responsible_party = fields.Selection([
        ("supplier", "Supplier"), ("installer", "Installer"), ("tfc", "TFC"),
        ("designer", "Designer"), ("client", "Client"), ("other", "Other"),
    ], string="Legacy Responsible Party", tracking=True)
    responsible_party_id = fields.Many2one(
        "tfc.project.document.lookup",
        string="Responsible Party",
        domain="[('kind', '=', 'snag_responsible_party')]",
        tracking=True,
    )
    responsible_contact_id = fields.Many2one("res.partner", string="Responsible Contact")
    required_resolution_date = fields.Date(tracking=True)
    priority = fields.Selection([
        ("critical", "Critical"), ("high", "High"),
        ("medium", "Medium"), ("low", "Low"),
    ], default="medium", tracking=True)
    status = fields.Selection(SNAG_STATUS_SELECTION, default="open", required=True, tracking=True)
    attachment_ids = fields.Many2many("ir.attachment", string="Attachments / Evidence")
    photo_required = fields.Boolean()
    resolution_notes = fields.Text(string="Resolution / Completion Notes")
    resolved_date = fields.Date()
    rectification_notes = fields.Text()
    rectification_date = fields.Date()
    verified_by_id = fields.Many2one(
        "res.users", string="Verified By", default=lambda self: self.env.user, readonly=True
    )
    verification_date = fields.Date()
    verification_comments = fields.Text()
    verification_outcome = fields.Selection([
        ("accepted", "Accepted"), ("rejected", "Rejected")
    ])
    rejection_reason = fields.Text()
    closure_notes = fields.Text()
    history_line_ids = fields.One2many("tfc.snag.history", "snag_id", copy=False)
    is_overdue = fields.Boolean(compute="_compute_is_overdue", search="_search_is_overdue")

    @api.depends("required_resolution_date", "status")
    def _compute_is_overdue(self):
        today = fields.Date.context_today(self)
        for snag in self:
            snag.is_overdue = bool(
                snag.required_resolution_date
                and snag.required_resolution_date < today
                and snag.status != "closed"
            )

    def _search_is_overdue(self, operator, value):
        domain = [
            ("required_resolution_date", "<", fields.Date.context_today(self)),
            ("status", "!=", "closed"),
        ]
        if (operator == "=" and value) or (operator == "!=" and not value):
            return domain
        return [
            "|", "|",
            ("required_resolution_date", "=", False),
            ("required_resolution_date", ">=", fields.Date.context_today(self)),
            ("status", "=", "closed"),
        ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            record._add_history(False, record.status, _("Snag raised"))
        return records

    def write(self, vals):
        if not self.env.context.get("tfc_allow_closed_write"):
            closed = self.filtered(lambda snag: snag.status == "closed")
            if closed and set(vals) != {"message_follower_ids"}:
                raise ValidationError(_("Closed snags are read-only. Reopen the snag before editing it."))
        old_statuses = {snag.id: snag.status for snag in self}
        if vals.get("verification_outcome") == "rejected":
            if not vals.get("rejection_reason") and any(not snag.rejection_reason for snag in self):
                raise ValidationError(_("A rejection reason is required when verification is rejected."))
            vals["status"] = "in_progress"
        result = super().write(vals)
        if "status" in vals and not self.env.context.get("tfc_history_from_log"):
            for snag in self:
                old_status = old_statuses.get(snag.id)
                if old_status != snag.status:
                    snag._add_history(old_status, snag.status, vals.get("closure_notes") or "")
        return result

    @api.constrains("photo_required", "attachment_ids")
    def _check_required_photo(self):
        if any(snag.photo_required and not snag.attachment_ids for snag in self):
            raise ValidationError(_("Attach evidence when Photo Required is selected."))

    def _add_history(self, old_status, new_status, notes):
        stage_xmlids = {
            "open": "lookup_snag_stage_identification",
            "assigned": "lookup_snag_stage_identification",
            "in_progress": "lookup_snag_stage_rectification",
            "resolved": "lookup_snag_stage_rectification",
            "verified": "lookup_snag_stage_verification",
            "closed": "lookup_snag_stage_closure",
        }
        status_xmlids = {
            key: "lookup_snag_progress_%s" % key for key, _label in SNAG_STATUS_SELECTION
        }
        stage = self.env.ref(
            "tfc_crm_project.%s" % stage_xmlids[new_status], raise_if_not_found=False
        )
        progress_status = self.env.ref(
            "tfc_crm_project.%s" % status_xmlids[new_status], raise_if_not_found=False
        )
        self.env["tfc.snag.history"].sudo().with_context(tfc_history_from_snag=True).create({
            "snag_id": self.id,
            "previous_status": old_status,
            "status": new_status,
            "stage_id": stage.id if stage else False,
            "status_id": progress_status.id if progress_status else False,
            "event_date": fields.Date.context_today(self),
            "change_date": fields.Datetime.now(),
            "changed_by_id": self.env.user.id,
            "notes": notes,
        })

    def action_reopen(self):
        for snag in self:
            snag.with_context(tfc_allow_closed_write=True).write({"status": "in_progress"})
        return True


class TfcSnagHistory(models.Model):
    _name = "tfc.snag.history"
    _description = "TFC Snag Status History"
    _order = "change_date desc, id desc"

    snag_id = fields.Many2one("tfc.snag", required=True, ondelete="cascade")
    project_id = fields.Many2one(related="snag_id.project_id", store=True, index=True)
    company_id = fields.Many2one(related="snag_id.company_id", store=True, index=True)
    stage_id = fields.Many2one(
        "tfc.project.document.lookup",
        string="Stage",
        domain="[('kind', '=', 'snag_progress_stage')]",
        ondelete="restrict",
    )
    status_id = fields.Many2one(
        "tfc.project.document.lookup",
        string="Status",
        domain="[('kind', '=', 'snag_progress_status')]",
        ondelete="restrict",
    )
    event_date = fields.Date(string="Date", default=fields.Date.context_today, required=True)
    previous_status = fields.Selection(SNAG_STATUS_SELECTION, string="Previous Status")
    status = fields.Selection(SNAG_STATUS_SELECTION, string="Lifecycle Status")
    change_date = fields.Datetime(required=True, default=fields.Datetime.now)
    changed_by_id = fields.Many2one(
        "res.users", required=True, default=lambda self: self.env.user, readonly=True
    )
    notes = fields.Text()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("status_id") and not self.env.context.get("tfc_history_from_snag"):
                lifecycle = self._tfc_lifecycle_from_lookup(vals["status_id"])
                if lifecycle:
                    vals["status"] = lifecycle
            if not vals.get("status") and vals.get("snag_id"):
                vals["status"] = self.env["tfc.snag"].browse(vals["snag_id"]).status
        records = super().create(vals_list)
        if not self.env.context.get("tfc_history_from_snag"):
            records._tfc_sync_snag_status()
        return records

    def write(self, vals):
        result = super().write(vals)
        if "status_id" in vals and not self.env.context.get("tfc_history_from_snag"):
            self._tfc_sync_snag_status()
        return result

    @api.model
    def _tfc_lifecycle_from_lookup(self, lookup_id):
        for key, _label in SNAG_STATUS_SELECTION:
            lookup = self.env.ref(
                "tfc_crm_project.lookup_snag_progress_%s" % key,
                raise_if_not_found=False,
            )
            if lookup and lookup.id == lookup_id:
                return key
        return False

    def _tfc_sync_snag_status(self):
        for line in self.filtered("status_id"):
            lifecycle = line._tfc_lifecycle_from_lookup(line.status_id.id)
            if lifecycle and line.snag_id.status != lifecycle:
                line.snag_id.with_context(tfc_history_from_log=True).write({"status": lifecycle})
            if lifecycle and line.status != lifecycle:
                line.with_context(tfc_history_from_snag=True).write({"status": lifecycle})


class TfcHandoverCertificate(models.Model):
    _name = "tfc.handover.certificate"
    _inherit = "tfc.project.document.mixin"
    _description = "TFC Handover Certificate"
    _sequence_code = "tfc.handover.certificate"
    _report_xmlid = "tfc_crm_project.action_report_tfc_handover_certificate"

    project_location = fields.Char(
        string="Project Location", related=False, readonly=False
    )

    handover_date = fields.Date(default=fields.Date.context_today, required=True, tracking=True)
    scope_id = fields.Many2one(
        "tfc.project.document.lookup", string="Handover Scope / Package",
        domain="[('kind', '=', 'handover_scope')]",
        default=lambda self: self.env.ref(
            "tfc_crm_project.lookup_handover_scope_project", raise_if_not_found=False
        )
    )
    area_id = fields.Many2one(related="project_id.tfc_area_id", string="Area / Package")
    quantity_scope_id = fields.Many2one(
        "tfc.project.document.lookup", string="Quantity / Scope",
        domain="[('kind', '=', 'handover_quantity_scope')]",
        default=lambda self: self.env.ref(
            "tfc_crm_project.lookup_handover_quantity_full", raise_if_not_found=False
        )
    )
    description = fields.Text()
    completion_status_id = fields.Many2one(
        "tfc.project.document.lookup", string="Completion Status",
        domain="[('kind', '=', 'handover_completion_status')]",
        default=lambda self: self.env.ref(
            "tfc_crm_project.lookup_handover_complete", raise_if_not_found=False
        )
    )
    client_representative = fields.Char(string="Client / Authorised Representative")
    organisation = fields.Char()
    acceptance_date = fields.Date()
    client_signature = fields.Binary(string="Client Signature", attachment=True)
    tfc_representative = fields.Char(string="TFC Representative")
    tfc_signature_date = fields.Date(string="TFC Date")
    tfc_signature = fields.Binary(string="TFC Signature", attachment=True)
    payment_milestone_id = fields.Many2one(
        "tfc.project.document.lookup", string="Payment Milestone",
        domain="[('kind', '=', 'payment_milestone')]",
        default=lambda self: self.env.ref(
            "tfc_crm_project.lookup_milestone_handover", raise_if_not_found=False
        )
    )
    snag_ids = fields.Many2many(
        "tfc.snag", string="Outstanding Snags", domain="[('project_id', '=', project_id), ('status', '!=', 'closed')]"
    )
    spec_sheet_ids = fields.Many2many(
        "tfc.spec.sheet", string="Spec Sheets", domain="[('project_id', '=', project_id)]"
    )
    attachment_ids = fields.Many2many("ir.attachment", string="Supporting Documents / Attachments")

    @api.onchange("project_id")
    def _onchange_project_location(self):
        if self.project_id and not self.project_location:
            self.project_location = self.project_id.tfc_project_location

    @api.model_create_multi
    def create(self, vals_list):
        projects = self.env["project.project"].browse(
            {vals.get("project_id") for vals in vals_list if vals.get("project_id")}
        )
        locations = {project.id: project.tfc_project_location for project in projects}
        for vals in vals_list:
            if vals.get("project_id") and not vals.get("project_location"):
                vals["project_location"] = locations.get(vals["project_id"])
        return super().create(vals_list)
```

script 2:
```py
from odoo import _, api, models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    @api.depends(
        "tfc_project_id.tfc_purchase_order_ids",
        "tfc_pricing_purchase_order_ids",
        "tfc_confirmation_attachment_ids",
        "tfc_contract_attachment_ids",
        "tfc_drawing_attachment_ids",
        "tfc_terms_attachment_ids",
        "tfc_previous_version_attachment_ids",
    )
    def _compute_tfc_smart_counts(self):
        super()._compute_tfc_smart_counts()
        Document = self.env["documents.document"]
        for lead in self:
            attachment_ids = (
                lead.tfc_confirmation_attachment_ids
                | lead.tfc_contract_attachment_ids
                | lead.tfc_drawing_attachment_ids
                | lead.tfc_terms_attachment_ids
                | lead.tfc_previous_version_attachment_ids
            ).ids
            lead.tfc_document_count = Document.search_count(
                [
                    "|",
                    "&", ("res_model", "=", "crm.lead"), ("res_id", "=", lead.id),
                    ("attachment_id", "in", attachment_ids),
                ]
            )

    def action_open_tfc_documents(self):
        self.ensure_one()
        attachment_ids = (
            self.tfc_confirmation_attachment_ids
            | self.tfc_contract_attachment_ids
            | self.tfc_drawing_attachment_ids
            | self.tfc_terms_attachment_ids
            | self.tfc_previous_version_attachment_ids
        ).ids
        return {
            "type": "ir.actions.act_window",
            "name": _("Documents"),
            "res_model": "documents.document",
            "view_mode": "kanban,list,form",
            "domain": [
                "|",
                "&", ("res_model", "=", "crm.lead"), ("res_id", "=", self.id),
                ("attachment_id", "in", attachment_ids),
            ],
            "context": {"default_res_model": "crm.lead", "default_res_id": self.id},
        }
```

script 3:
```xml
<?xml version="1.0" encoding="utf-8"?>
<odoo>
    <record id="purchase_order_view_form_tfc" model="ir.ui.view">
        <field name="name">purchase.order.form.tfc</field>
        <field name="model">purchase.order</field>
        <field name="inherit_id" ref="purchase.purchase_order_form"/>
        <field name="arch" type="xml">
            <xpath expr="//header" position="inside">
                <button name="action_print_tfc_request_for_po" type="object"
                        string="Print Request for PO" class="btn-secondary"
                        invisible="state not in ['draft', 'sent', 'to approve']"/>
                <button name="action_tfc_approve" type="object" string="Approve (TFC)"
                        class="btn-primary" invisible="tfc_approval_valid or not tfc_required_approver_ids or state not in ['draft', 'sent']"/>
            </xpath>
            <xpath expr="//div[@name='button_box']" position="inside">
                <button name="action_open_tfc_opportunity" type="object" class="oe_stat_button" icon="fa-star" invisible="not tfc_opportunity_id">
                    <field name="tfc_opportunity_id" widget="statinfo" string="Opportunity"/>
                </button>
                <button name="action_open_tfc_sale_order" type="object" class="oe_stat_button" icon="fa-shopping-cart" invisible="not tfc_source_sale_order_id">
                    <field name="tfc_source_sale_order_id" widget="statinfo" string="Sales"/>
                </button>
            </xpath>
            <xpath expr="//page[@name='purchase_delivery_invoice']//group[@name='other_info']" position="inside">
                <field name="tfc_source_sale_order_id" required="state in ['draft', 'sent']"/>
                <field name="project_id" required="state in ['draft', 'sent']"/>
                <field name="tfc_spec_sheet_ids" widget="many2many_tags"/>
                <field name="tfc_required_approver_id" invisible="1"/>
                <field name="tfc_required_approver_ids" widget="many2many_tags" readonly="1"/>
                <field name="tfc_approved" invisible="1"/>
                <field name="tfc_approval_valid" readonly="1"/>
                <field name="tfc_approved_by_id" invisible="1"/>
                <field name="tfc_approved_by_ids" widget="many2many_tags" readonly="1"/>
                <field name="tfc_approval_date" readonly="1" invisible="not tfc_approved_by_ids" string="Latest Approval Date"/>
            </xpath>
            <xpath expr="//notebook" position="inside">
                <page name="tfc_client_references" string="Client References">
                    <group>
                        <group>
                            <field name="tfc_client_project_code"/>
                            <field name="tfc_client_order_reference"/>
                            <field name="tfc_client_site_code"/>
                            <field name="tfc_client_business_unit_code"/>
                        </group>
                    </group>
                </page>
                <page name="tfc_delivery_address" string="Delivery Address">
                    <group>
                        <group>
                            <field name="tfc_delivery_name"/>
                            <field name="tfc_delivery_street" placeholder="Street..."/>
                            <field name="tfc_delivery_street2" placeholder="Street 2..."/>
                            <field name="tfc_delivery_city"/>
                        </group>
                        <group>
                            <field name="tfc_delivery_country_id"/>
                            <field name="tfc_delivery_state_id"
                                   context="{'default_country_id': tfc_delivery_country_id}"/>
                            <field name="tfc_delivery_zip"/>
                            <field name="tfc_delivery_phone" widget="phone"/>
                            <field name="tfc_delivery_mobile" widget="phone"/>
                            <field name="tfc_delivery_email" widget="email"/>
                            <field name="tfc_delivery_vat"/>
                            <field name="tfc_delivery_website" widget="url"/>
                            <field name="tfc_delivery_lang"/>
                            <field name="tfc_delivery_category_ids" widget="many2many_tags"/>
                        </group>
                    </group>
                </page>
                <page name="tfc_delivery_tracking" string="Delivery Tracking">
                    <button name="action_open_tfc_delivery_wizard" type="object" string="Create" class="btn-primary mb-3"/>
                    <field name="tfc_delivery_update_ids" readonly="1">
                        <list create="false" delete="false" default_order="update_date desc">
                            <field name="update_date"/>
                            <field name="stock_picking_id"/>
                            <field name="courier_name"/>
                            <field name="collection_point"/>
                            <field name="delivery_point"/>
                            <field name="eta"/>
                            <field name="status_id"/>
                            <field name="responsibility_id"/>
                            <field name="pod_name"/>
                            <field name="pod_date"/>
                            <field name="exception_id"/>
                        </list>
                        <form>
                            <group><group><field name="update_date"/><field name="stock_picking_id"/><field name="courier_name"/><field name="collection_point"/><field name="delivery_point"/><field name="eta"/></group><group><field name="status_id"/><field name="responsibility_id"/><field name="pod_name"/><field name="pod_date"/><field name="pod_attachment" filename="pod_attachment_name"/><field name="pod_attachment_name" invisible="1"/><field name="exception_id"/></group></group><field name="notes"/>
                        </form>
                    </field>
                </page>
            </xpath>
        </field>
    </record>
</odoo>
```