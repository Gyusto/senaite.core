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

from bika.lims import api
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.core.browser.billing.read import get_client
from senaite.core.browser.billing.read import serialize_invoice


class InvoicePrintView(BrowserView):
    """Printable HTML view of a single Invoice (context = BillingInvoice)
    """
    template = ViewPageTemplateFile("templates/invoice_print.pt")

    def __call__(self):
        html = self.template()
        if self.request.get("format") == "pdf":
            return self.as_pdf(html)
        return html

    def render_pdf_bytes(self):
        """Return the invoice rendered as PDF bytes (no response side-effects).
        """
        from weasyprint import HTML
        html = self.template()
        return HTML(
            string=html, base_url=self.context.absolute_url()).write_pdf()

    def as_pdf(self, html):
        """Render the invoice HTML into a PDF via WeasyPrint (the same engine
        senaite.impress uses).
        """
        from weasyprint import HTML
        pdf = HTML(string=html, base_url=self.context.absolute_url()).write_pdf()
        number = self.context.accessor("title")(self.context) or "invoice"
        response = self.request.response
        response.setHeader("Content-Type", "application/pdf")
        response.setHeader(
            "Content-Disposition",
            "inline; filename={}.pdf".format(number))
        response.setHeader("Content-Length", len(pdf))
        return pdf

    def invoice(self):
        return serialize_invoice(self.context)

    def client(self):
        return get_client(self.context)[1]

    def lab_title(self):
        lab = getattr(api.get_setup(), "laboratory", None)
        return api.get_title(lab) if lab is not None else u"SENAITE LIMS"
