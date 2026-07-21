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
from plone.protect.authenticator import createToken
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.core.browser.billing.read import get_client
from senaite.core.browser.billing.read import serialize_invoice


class InvoiceDetailView(BrowserView):
    """Detail view of a single Invoice: shows the line items and the available
    workflow actions (Issue / Pay / Cancel / Reinstate) as buttons.
    """
    template = ViewPageTemplateFile("templates/invoice_detail.pt")

    def __call__(self):
        form = self.request.form
        posted = self.request.get("REQUEST_METHOD", "GET") == "POST"
        # Handle a workflow action posted from the buttons below
        if posted and form.get("workflow_action"):
            api.do_transition_for(self.context, form.get("workflow_action"))
            return self._redirect()
        # Handle a recorded payment
        if posted and form.get("record_payment"):
            self._record_payment(form)
            return self._redirect()
        # Handle emailing the invoice PDF to the client
        if posted and form.get("email_invoice"):
            self.message = self._email_invoice(form)
            return self.template()
        self.message = self.request.get("message", "")
        return self.template()

    def _redirect(self):
        self.request.response.redirect(
            "{}/view".format(api.get_url(self.context)))
        return u""

    def _record_payment(self, form):
        amount = api.safe_unicode(form.get("amount") or "0")
        method = api.safe_unicode(form.get("method") or "cash")
        reference = api.safe_unicode(form.get("reference") or "")
        payment = api.create(
            self.context, "Payment",
            title=reference or u"Payment",
            amount=amount, method=method)
        pdate = form.get("payment_date")
        if pdate:
            from senaite.core.api.dtime import to_dt
            payment.mutator("payment_date")(payment, to_dt(pdate))
        # recompute amount paid and auto-advance to 'paid' when settled
        self.context.recompute_paid()

    def invoice(self):
        return serialize_invoice(self.context)

    def client(self):
        return get_client(self.context)[1]

    def transitions(self):
        """Available workflow transitions for the current user/state
        """
        return api.get_transitions_for(self.context)

    def authenticator(self):
        return createToken()

    message = ""

    def payment_methods(self):
        from senaite.core.content.billing import PAYMENT_METHODS
        return [t.value for t in PAYMENT_METHODS]

    def default_recipient(self):
        """Best-guess recipient: the first client contact with an email
        """
        client = self.client()
        if client is None:
            return ""
        for contact in client.getContacts():
            email = contact.getEmailAddress()
            if email:
                return email
        return ""

    def _lab_email(self):
        try:
            lab = api.get_setup().laboratory
            return lab.getEmailAddress() or "noreply@senaite.lims"
        except Exception:  # noqa
            return "noreply@senaite.lims"

    def _email_invoice(self, form):
        from bika.lims.api import mail
        recipient = (form.get("recipient")
                     or self.default_recipient() or "").strip()
        if not recipient or not mail.is_valid_email_address(recipient):
            return "Please provide a valid recipient email address."

        number = self.context.accessor("title")(self.context) or "invoice"
        printview = self.context.restrictedTraverse("print")
        pdf = printview.render_pdf_bytes()
        attachment = mail.to_email_attachment(
            pdf, filename="{}.pdf".format(number),
            mime_type="application/pdf")
        body = ("Dear customer,\n\nPlease find attached invoice {}.\n\n"
                "Kind regards,\n{}".format(number, self._lab_email()))
        message = mail.compose_email(
            self._lab_email(), recipient,
            "Invoice {}".format(number), body, attachments=[attachment])
        sent = mail.send_email(message)
        if sent:
            return "Invoice {} emailed to {}.".format(number, recipient)
        return ("Invoice composed but delivery failed (is an SMTP server "
                "configured under MailHost?). Recipient: {}".format(recipient))

    def can_record_payment(self):
        return api.get_review_status(self.context) in ("issued",)
