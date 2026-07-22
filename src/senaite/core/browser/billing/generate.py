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
from senaite.core.content.billing import get_exchange_rate
from senaite.core.content.billing import recatalog
from senaite.core.content.billing import to_decimal


class BillSampleView(BrowserView):
    """Snapshot the billable items of a Sample into line items of the current
    Invoice (context), then recalculate the invoice totals.

    Usage: POST/GET .../senaite/invoices/<invoice>/bill_sample?sample_uid=<uid>

    This is the server-side price-snapshot: it reads the *real* prices from the
    sample's billable analyses/profiles (getBillableItems) so the invoice never
    has to recompute them later.
    """

    def __call__(self):
        self.request.response.setHeader("Content-Type", "application/json")
        sample_uid = self.request.get("sample_uid")
        if not sample_uid:
            return self._error("Missing sample_uid")

        try:
            sample = api.get_object_by_uid(sample_uid)
        except Exception:  # noqa: broad - invalid uid
            return self._error("Invalid sample_uid: {}".format(sample_uid))

        sample_id = api.get_id(sample)
        # billing scheme of this invoice (cash | insurance)
        price_group = self.context.accessor("price_group")(self.context)
        # currency conversion: prices are stored in the base currency; convert
        # to the invoice currency and freeze the rate on the invoice
        currency = self.context.accessor("currency")(self.context)
        rate = get_exchange_rate(currency)
        self.context.mutator("exchange_rate")(
            self.context, u"{}".format(rate))
        created = []
        for obj in sample.getBillableItems():
            # profiles carry their own fixed price/VAT; analyses price via the
            # service. Detect by portal_type so it works for both the Dexterity
            # (senaite.core) and legacy (bika.lims) AnalysisProfile types.
            if api.get_portal_type(obj) == "AnalysisProfile":
                title = obj.Title()
                base_price = to_decimal(obj.getAnalysisProfilePrice())
                vat_pct = to_decimal(obj.getAnalysisProfileVAT())
            else:
                title = obj.Title()
                base_price = self._unit_price(obj, price_group)
                vat_pct = to_decimal(obj.getVAT())

            unit_price = base_price * rate
            line_total = unit_price  # quantity 1
            line = api.create(
                self.context, "BillingLineItem",
                title=u"{} ({})".format(title, sample_id),
                source_uid=api.get_uid(obj),
                sample_id=sample_id,
                quantity=u"1",
                unit_price=u"{:.2f}".format(unit_price),
                vat_percentage=u"{:.2f}".format(vat_pct),
                line_total=u"{:.2f}".format(line_total),
            )
            created.append(api.get_id(line))

        total = self.context.recalculate()
        recatalog(self.context)

        return json.dumps({
            "success": True,
            "invoice": api.get_id(self.context),
            "sample": sample_id,
            "line_items_created": created,
            "subtotal": str(self.context.accessor("subtotal")(self.context)),
            "vat": str(self.context.accessor("vat")(self.context)),
            "total": u"{:.2f}".format(total),
        })

    def _unit_price(self, analysis, price_group):
        """Return the unit price for an analysis under the given price group.

        For the "insurance" group the service's InsurancePrice is used when set
        (> 0); otherwise it falls back to the standard analysis price.
        """
        if price_group == "insurance":
            service = analysis.getService()
            if service is not None:
                insurance = to_decimal(service.getInsurancePrice())
                if insurance > 0:
                    return insurance
        return to_decimal(analysis.getPrice())

    def _error(self, message):
        return json.dumps({"success": False, "message": message})
