# -*- coding: utf-8 -*-
#
# This file is part of SENAITE.CORE.
#
# SENAITE.CORE is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, version 2.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc., 51
# Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# Copyright 2018-2025 by it's authors.
# Some rights reserved, see README and LICENSE.

import collections

from bika.lims import _
from bika.lims import api
from bika.lims.utils import get_link_for
from senaite.core.browser.listing.base import ListingView
from senaite.core.catalog import SETUP_CATALOG


class InvoicesView(ListingView):
    """Listing view for Invoices (BillingInvoice) inside the Invoices container
    """

    def __init__(self, context, request):
        super(InvoicesView, self).__init__(context, request)

        self.catalog = SETUP_CATALOG
        self.contentFilter = {
            "portal_type": "BillingInvoice",
            "path": {
                "query": api.get_path(context),
                "depth": 1,
            },
            "sort_on": "created",
            "sort_order": "descending",
        }

        self.title = self.context.translate(_("Invoices"))
        self.description = ""
        self.show_select_column = True
        self.form_id = "invoices"
        self.context_actions = {
            _("Summary"): {
                "url": "summary",
                "icon": "{}/{}".format(
                    self.portal_url, "senaite_theme/icon/dashboard"),
            },
            _("Price schemes"): {
                "url": "pricing",
                "icon": "{}/{}".format(
                    self.portal_url, "senaite_theme/icon/coin"),
            },
        }
        self.icon = "{}{}".format(
            self.portal_url, "/senaite_theme/icon/invoice")
        self.url = api.get_url(self.context)

        self.columns = collections.OrderedDict((
            ("number", {
                "title": _("Invoice #"),
                "index": "sortable_title"}),
            ("client", {
                "title": _("Client")}),
            ("invoice_date", {
                "title": _("Date")}),
            ("price_group", {
                "title": _("Price group")}),
            ("payment_method", {
                "title": _("Payment")}),
            ("total", {
                "title": _("Total")}),
            ("balance_due", {
                "title": _("Balance")}),
            ("state_title", {
                "title": _("State"),
                "sortable": True,
                "index": "review_state"}),
        ))

        all_columns = list(self.columns.keys())
        self.review_states = [
            {"id": "default", "title": _("All"),
             "contentFilter": {}, "columns": all_columns},
            {"id": "draft", "title": _("Draft"),
             "contentFilter": {"review_state": "draft"},
             "columns": all_columns},
            {"id": "issued", "title": _("Issued"),
             "contentFilter": {"review_state": "issued"},
             "columns": all_columns},
            {"id": "paid", "title": _("Paid"),
             "contentFilter": {"review_state": "paid"},
             "columns": all_columns},
            {"id": "cancelled", "title": _("Cancelled"),
             "contentFilter": {"review_state": "cancelled"},
             "columns": all_columns},
        ]

    def folderitem(self, obj, item, index):
        """Populate each invoice row from the woken object (the setup catalog
        has no invoice-specific metadata columns).
        """
        item = super(InvoicesView, self).folderitem(obj, item, index)
        if not item:
            return None

        invoice = api.get_object(obj)
        get = invoice.accessor

        number = get("title")(invoice)
        item["number"] = number
        item["replace"]["number"] = get_link_for(invoice, value=number)

        client_acc = invoice.accessor("client", raw=True)
        client_uid = client_acc(invoice) if client_acc else None
        if isinstance(client_uid, (list, tuple)):
            client_uid = client_uid[0] if client_uid else None
        client = api.get_object_by_uid(client_uid, default=None) \
            if client_uid else None
        item["client"] = client.Title() if client else ""
        if client:
            item["replace"]["client"] = get_link_for(client)

        invoice_date = get("invoice_date")(invoice)
        item["invoice_date"] = self.ulocalized_time(invoice_date, long_format=0) \
            if invoice_date else ""

        item["price_group"] = (get("price_group")(invoice) or "").title()
        item["payment_method"] = (
            get("payment_method")(invoice) or "").replace("_", " ").title()

        currency = get("currency")(invoice) or ""
        item["total"] = u"{} {}".format(currency, get("total")(invoice) or "0.00")
        item["balance_due"] = u"{} {:.2f}".format(
            currency, invoice.get_balance_due())

        # flag overdue invoices in red
        if invoice.is_overdue():
            item["state_title"] = "Overdue"
            item["replace"]["state_title"] = (
                '<span class="badge badge-danger">Overdue</span>')

        return item
