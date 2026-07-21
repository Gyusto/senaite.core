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

import csv
from io import BytesIO

from bika.lims import api
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.content.billing import get_base_currency
from senaite.core.content.billing import get_exchange_rates

HEADER = ["keyword", "title", "cash_price", "insurance_price", "vat"]

# The available price schemes (price groups)
SCHEMES = [
    {"id": "cash", "title": "Cash",
     "description": "Standard self-pay price (service Price field)"},
    {"id": "insurance", "title": "Insurance",
     "description": "Insurance price (service InsurancePrice field)"},
]


class PricingView(BrowserView):
    """Price scheme manager: list analysis-service prices per scheme, download a
    CSV price template, and upload a filled template to bulk-update prices.
    """
    template = ViewPageTemplateFile("templates/pricing.pt")

    def __call__(self):
        form = self.request.form
        if form.get("download"):
            return self.download_csv()
        posted = self.request.get("REQUEST_METHOD") == "POST"
        if posted and form.get("csvfile"):
            self.message = self.import_csv(form.get("csvfile"))
        elif posted and form.get("save_rates"):
            self.message = self.save_rates(form)
        else:
            self.message = self.request.get("message", "")
        return self.template()

    # -- currency / exchange rates ---------------------------------------

    def base_currency(self):
        return get_base_currency()

    def exchange_rates_text(self):
        setup = api.get_senaite_setup()
        return getattr(setup, "exchange_rates", None) or u""

    def exchange_rates(self):
        base = self.base_currency()
        return [{"code": code, "rate": str(rate)}
                for code, rate in sorted(get_exchange_rates().items())]

    def currencies(self):
        factory = api.get_tool("portal_vocabularies", default=None)  # noqa
        # simple list of common codes for the base-currency selector
        return ["USD", "EUR", "GBP", "TZS", "KES", "UGX", "NGN", "ZAR", "INR"]

    def save_rates(self, form):
        setup = api.get_senaite_setup()
        setup.exchange_rates = api.safe_unicode(form.get("exchange_rates", u""))
        base = form.get("base_currency")
        if base:
            setup.currency = base
        setup.reindexObject()
        return "Currency settings saved."

    # -- data -------------------------------------------------------------

    def schemes(self):
        return SCHEMES

    def get_services(self):
        query = {"portal_type": "AnalysisService", "sort_on": "sortable_title"}
        return [api.get_object(b) for b in api.search(query, SETUP_CATALOG)]

    def services(self):
        rows = []
        for svc in self.get_services():
            rows.append({
                "keyword": svc.getKeyword(),
                "title": svc.Title(),
                "cash_price": svc.getPrice(),
                "insurance_price": svc.getInsurancePrice(),
                "vat": svc.getVAT(),
            })
        return rows

    # -- CSV download -----------------------------------------------------

    def download_csv(self):
        out = BytesIO()
        writer = csv.writer(out)
        writer.writerow(HEADER)
        for row in self.services():
            writer.writerow([
                row["keyword"], row["title"], row["cash_price"],
                row["insurance_price"], row["vat"]])
        data = out.getvalue()
        self.request.response.setHeader("Content-Type", "text/csv")
        self.request.response.setHeader(
            "Content-Disposition",
            "attachment; filename=senaite-price-template.csv")
        return data

    # -- CSV upload -------------------------------------------------------

    def import_csv(self, fileupload):
        raw = fileupload.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        lines = raw.splitlines()
        reader = csv.DictReader(lines)

        # index services by keyword
        by_keyword = {}
        for svc in self.get_services():
            by_keyword[svc.getKeyword()] = svc

        updated = 0
        skipped = []
        for record in reader:
            keyword = (record.get("keyword") or "").strip()
            svc = by_keyword.get(keyword)
            if svc is None:
                if keyword:
                    skipped.append(keyword)
                continue
            if record.get("cash_price") not in (None, ""):
                svc.setPrice(record["cash_price"].strip())
            if record.get("insurance_price") not in (None, ""):
                svc.setInsurancePrice(record["insurance_price"].strip())
            if record.get("vat") not in (None, ""):
                svc.setVAT(record["vat"].strip())
            svc.reindexObject()
            updated += 1

        msg = "Updated {} service(s).".format(updated)
        if skipped:
            msg += " Skipped unknown keywords: {}.".format(", ".join(skipped))
        return msg
