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

from datetime import timedelta

from bika.lims import api
from DateTime import DateTime


def after_issue(invoice):
    """When an invoice is issued, stamp its due date as the invoice date plus
    the configured payment terms (falling back to 30 days).
    """
    accessor = invoice.accessor("invoice_date")
    invoice_date = accessor(invoice) if accessor else None
    if not invoice_date:
        invoice_date = DateTime().asdatetime()
        invoice.mutator("invoice_date")(invoice, invoice_date)

    try:
        terms = int(getattr(
            api.get_senaite_setup(), "payment_terms_days", 30) or 30)
    except (TypeError, ValueError):
        terms = 30

    due = invoice_date + timedelta(days=terms)
    invoice.mutator("due_date")(invoice, due)

    from senaite.core.content.billing import recatalog
    recatalog(invoice)
