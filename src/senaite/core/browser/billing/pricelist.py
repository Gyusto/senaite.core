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

HEADER = ["item_type", "uid", "keyword", "title",
          "cash_price", "insurance_price", "vat"]


def _fmt(value):
    """Format a price/VAT value as a plain 2-decimal string."""
    if value in (None, ""):
        return u""
    try:
        return u"{:.2f}".format(float(value))
    except (TypeError, ValueError):
        return api.safe_unicode(value)

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

    def get_profiles(self):
        query = {"portal_type": "AnalysisProfile", "sort_on": "sortable_title"}
        return [api.get_object(b) for b in api.search(query, SETUP_CATALOG)]

    def items(self):
        """All available billable items (services + profiles) with prices.

        These are exactly the item types that can end up as invoice line items
        (see ``getBillableItems``), so the price template covers everything that
        can be billed - not just analysis services.
        """
        rows = []
        for svc in self.get_services():
            rows.append({
                "item_type": "service",
                "uid": api.get_uid(svc),
                "keyword": svc.getKeyword(),
                "title": svc.Title(),
                "cash_price": _fmt(svc.getPrice()),
                "insurance_price": _fmt(svc.getInsurancePrice()),
                "vat": _fmt(svc.getVAT()),
            })
        for profile in self.get_profiles():
            rows.append({
                "item_type": "profile",
                "uid": api.get_uid(profile),
                "keyword": profile.getProfileKey() or u"",
                "title": profile.Title(),
                "cash_price": _fmt(profile.getAnalysisProfilePrice()),
                # profiles have a single price, no insurance variant
                "insurance_price": u"",
                "vat": _fmt(profile.getAnalysisProfileVAT()),
            })
        return rows

    # BBB: kept for callers that only want services
    def services(self):
        return [r for r in self.items() if r["item_type"] == "service"]

    # -- CSV download -----------------------------------------------------

    def download_csv(self):
        out = BytesIO()
        writer = csv.writer(out)
        writer.writerow(HEADER)
        for row in self.items():
            writer.writerow([row[col] for col in HEADER])
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

        # index services + profiles for matching by uid (both types) and by
        # keyword (services only, for backward-compatible service-only files)
        by_uid = {}
        by_keyword = {}
        for svc in self.get_services():
            by_uid[api.get_uid(svc)] = svc
            by_keyword[svc.getKeyword()] = svc
        for profile in self.get_profiles():
            by_uid[api.get_uid(profile)] = profile

        def _cell(record, key):
            value = record.get(key)
            return value.strip() if value else u""

        updated = 0
        skipped = []
        for record in reader:
            uid = _cell(record, "uid")
            keyword = _cell(record, "keyword")
            obj = by_uid.get(uid) or by_keyword.get(keyword)
            if obj is None:
                label = uid or keyword
                if label:
                    skipped.append(label)
                continue
            cash = _cell(record, "cash_price")
            insurance = _cell(record, "insurance_price")
            vat = _cell(record, "vat")
            if api.get_portal_type(obj) == "AnalysisProfile":
                if cash:
                    obj.setAnalysisProfilePrice(cash)
                    # make sure the profile's own price is actually applied
                    obj.setUseAnalysisProfilePrice(True)
                if vat:
                    obj.setAnalysisProfileVAT(vat)
            else:
                if cash:
                    obj.setPrice(cash)
                if insurance:
                    obj.setInsurancePrice(insurance)
                if vat:
                    obj.setVAT(vat)
            obj.reindexObject()
            updated += 1

        msg = "Updated {} item(s).".format(updated)
        if skipped:
            msg += " Skipped unknown rows: {}.".format(", ".join(skipped))
        return msg
