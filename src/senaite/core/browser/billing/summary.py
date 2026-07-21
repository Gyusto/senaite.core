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

from collections import OrderedDict
from decimal import Decimal

from bika.lims import api
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.core.content.billing import to_decimal


class BillingSummaryView(BrowserView):
    """Billing overview: outstanding / overdue / collected, grouped by currency
    """
    template = ViewPageTemplateFile("templates/summary.pt")

    def __call__(self):
        return self.template()

    def rows(self):
        data = OrderedDict()

        def bucket(currency):
            return data.setdefault(currency, {
                "currency": currency,
                "count": 0,
                "outstanding": Decimal("0"),
                "overdue": Decimal("0"),
                "overdue_count": 0,
                "collected": Decimal("0"),
            })

        invoices = [obj for obj in self.context.objectValues()
                    if getattr(obj, "portal_type", None) == "BillingInvoice"]
        for inv in invoices:
            currency = inv.accessor("currency")(inv) or "?"
            row = bucket(currency)
            row["count"] += 1
            state = api.get_review_status(inv)
            if state == "paid":
                row["collected"] += to_decimal(inv.accessor("total")(inv))
            elif state == "issued":
                row["outstanding"] += inv.get_balance_due()
                if inv.is_overdue():
                    row["overdue"] += inv.get_balance_due()
                    row["overdue_count"] += 1

        # stringify decimals for the template
        result = []
        for row in data.values():
            result.append({
                "currency": row["currency"],
                "count": row["count"],
                "outstanding": u"{:.2f}".format(row["outstanding"]),
                "overdue": u"{:.2f}".format(row["overdue"]),
                "overdue_count": row["overdue_count"],
                "collected": u"{:.2f}".format(row["collected"]),
            })
        return result
