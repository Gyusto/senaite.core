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

import json

from bika.lims import api
from Products.Five.browser import BrowserView


def field(obj, name):
    """Read a schema field value via the SENAITE accessor
    """
    accessor = obj.accessor(name)
    if accessor is None:
        return None
    value = accessor(obj)
    # normalise DateTime / references / vocab tokens to strings
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return api.safe_unicode(str(value))


def get_client(invoice):
    """Resolve the Client object referenced by the invoice (or None)
    """
    accessor = invoice.accessor("client", raw=True)
    if accessor is None:
        return None, None
    uid = accessor(invoice)
    if isinstance(uid, (list, tuple)):
        uid = uid[0] if uid else None
    if not uid:
        return None, None
    client = api.get_object_by_uid(uid, default=None)
    return uid, client


def serialize_invoice(invoice):
    """Return a plain-dict view of an invoice and its line items
    """
    client_uid, client = get_client(invoice)
    line_items = []
    for line in invoice.get_line_items():
        line_items.append({
            "id": api.get_id(line),
            "description": field(line, "title"),
            "sample_id": field(line, "sample_id"),
            "quantity": field(line, "quantity"),
            "unit_price": field(line, "unit_price"),
            "vat_percentage": field(line, "vat_percentage"),
            "line_total": field(line, "line_total"),
        })
    payments = []
    for p in invoice.get_payments():
        payments.append({
            "id": api.get_id(p),
            "reference": field(p, "title"),
            "amount": field(p, "amount"),
            "method": field(p, "method"),
            "payment_date": field(p, "payment_date"),
        })
    return {
        "id": api.get_id(invoice),
        "uid": api.get_uid(invoice),
        "number": field(invoice, "title"),
        "client_uid": client_uid,
        "client_title": client.Title() if client is not None else u"",
        "invoice_date": field(invoice, "invoice_date"),
        "due_date": field(invoice, "due_date"),
        "currency": field(invoice, "currency"),
        "exchange_rate": field(invoice, "exchange_rate"),
        "price_group": field(invoice, "price_group"),
        "payment_method": field(invoice, "payment_method"),
        "subtotal": field(invoice, "subtotal"),
        "discount": field(invoice, "discount"),
        "vat": field(invoice, "vat"),
        "total": field(invoice, "total"),
        "amount_paid": field(invoice, "amount_paid"),
        "balance_due": u"{:.2f}".format(invoice.get_balance_due()),
        "is_overdue": invoice.is_overdue(),
        "review_state": api.get_review_status(invoice),
        "line_items": line_items,
        "payments": payments,
    }


class InvoiceInfoView(BrowserView):
    """JSON detail of a single Invoice (context = BillingInvoice)
    """

    def __call__(self):
        self.request.response.setHeader("Content-Type", "application/json")
        return json.dumps(serialize_invoice(self.context))


class InvoicesListView(BrowserView):
    """JSON list of all Invoices (context = BillingInvoices folder)
    """

    def __call__(self):
        self.request.response.setHeader("Content-Type", "application/json")
        invoices = [serialize_invoice(inv)
                    for inv in self.context.objectValues()
                    if getattr(inv, "portal_type", None) == "BillingInvoice"]
        return json.dumps({"count": len(invoices), "invoices": invoices})
