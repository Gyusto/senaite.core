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

from decimal import Decimal

from AccessControl import ClassSecurityInfo
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from plone.dexterity.content import Container as BaseContainer
from plone.supermodel import model
from Products.CMFCore import permissions
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.content.base import Container
from senaite.core.content.base import Item
from senaite.core.interfaces import IBillingInvoice
from senaite.core.interfaces import IBillingInvoices
from senaite.core.interfaces import IBillingLineItem
from senaite.core.interfaces import IPayment
from senaite.core.schema import DatetimeField
from senaite.core.schema import UIDReferenceField
from zope import schema
from zope.interface import implementer
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary


# Billing scheme the invoice is priced/collected under
PRICE_GROUPS = SimpleVocabulary([
    SimpleTerm(value=u"cash", token="cash", title=_(u"Cash")),
    SimpleTerm(value=u"insurance", token="insurance", title=_(u"Insurance")),
])

# How the invoice is (to be) settled
PAYMENT_METHODS = SimpleVocabulary([
    SimpleTerm(value=u"cash", token="cash", title=_(u"Cash")),
    SimpleTerm(value=u"card", token="card", title=_(u"Card")),
    SimpleTerm(value=u"bank_transfer", token="bank_transfer",
               title=_(u"Bank transfer")),
    SimpleTerm(value=u"cheque", token="cheque", title=_(u"Cheque")),
    SimpleTerm(value=u"insurance", token="insurance", title=_(u"Insurance")),
])


def to_decimal(value, default="0.0"):
    """Coerce a stored (string) money value into a Decimal
    """
    try:
        return Decimal(str(value or default))
    except (ValueError, ArithmeticError):
        return Decimal(default)


def recatalog(obj):
    """Force-catalog a billing object into its SENAITE catalog(s), bypassing
    the multi-catalog behaviour gate (which otherwise skips freshly-created
    Dexterity objects, leaving them out of senaite_catalog_setup).
    """
    try:
        catalogs = api.get_catalogs_for(obj)
    except Exception:  # noqa
        return
    for cat in catalogs:
        try:
            cat.catalog_object(obj, idxs=None, update_metadata=1)
        except Exception:  # noqa
            continue


def get_base_currency():
    """The site's base (accounting) currency
    """
    try:
        return getattr(api.get_senaite_setup(), "currency", None) or u"USD"
    except Exception:  # noqa: fall back if setup is unavailable
        return u"USD"


def default_currency():
    """Default invoice currency, taken from the site's Accounting setup
    """
    return get_base_currency()


def get_exchange_rates():
    """Parse the site's configured exchange rates into a {CODE: Decimal} map.

    Each rate expresses how many units of CODE equal one unit of the base
    (accounting) currency, e.g. with base USD a line ``TZS=2600`` means
    1 USD = 2600 TZS.
    """
    try:
        raw = getattr(api.get_senaite_setup(), "exchange_rates", None) or u""
    except Exception:  # noqa
        raw = u""
    rates = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        code, _sep, value = line.partition("=")
        try:
            rates[code.strip().upper()] = Decimal(value.strip())
        except (ValueError, ArithmeticError):
            continue
    return rates


def get_exchange_rate(currency):
    """Rate to convert an amount from the base currency into ``currency``.

    Returns Decimal(1) when the currency is the base currency or when no rate
    is configured for it.
    """
    base = get_base_currency()
    if not currency or str(currency).upper() == str(base).upper():
        return Decimal("1")
    return get_exchange_rates().get(str(currency).upper(), Decimal("1"))


# ---------------------------------------------------------------------------
#  Invoices folder (top level container at /senaite/invoices)
# ---------------------------------------------------------------------------

class IBillingInvoicesSchema(model.Schema):
    """Schema interface for the Invoices container
    """


@implementer(IBillingInvoices, IBillingInvoicesSchema)
class BillingInvoices(BaseContainer):
    """A container that holds the issued invoices
    """


# ---------------------------------------------------------------------------
#  Invoice line item (one billed analysis / sample)
# ---------------------------------------------------------------------------

class IBillingLineItemSchema(model.Schema):
    """One billable line of an invoice (a price snapshot)
    """

    title = schema.TextLine(
        title=_(u"Description"),
        required=True,
    )

    source_uid = schema.TextLine(
        title=_(u"Source UID"),
        description=_(u"UID of the billed Analysis or Sample"),
        required=False,
    )

    sample_id = schema.TextLine(
        title=_(u"Sample ID"),
        required=False,
    )

    quantity = schema.TextLine(
        title=_(u"Quantity"),
        default=u"1",
        required=False,
    )

    unit_price = schema.TextLine(
        title=_(u"Unit price"),
        default=u"0.00",
        required=False,
    )

    vat_percentage = schema.TextLine(
        title=_(u"VAT %"),
        default=u"0.00",
        required=False,
    )

    line_total = schema.TextLine(
        title=_(u"Line total"),
        default=u"0.00",
        required=False,
    )


@implementer(IBillingLineItem, IBillingLineItemSchema)
class BillingLineItem(Item):
    """A single invoice line (frozen price snapshot)
    """
    _catalogs = [SETUP_CATALOG]

    security = ClassSecurityInfo()

    @security.protected(permissions.View)
    def get_line_total(self):
        """Return the line total as a Decimal
        """
        qty = to_decimal(self.accessor("quantity")(self), default="1")
        unit = to_decimal(self.accessor("unit_price")(self))
        stored = self.accessor("line_total")(self)
        if stored:
            return to_decimal(stored)
        return qty * unit


# ---------------------------------------------------------------------------
#  Payment (a single payment recorded against an invoice)
# ---------------------------------------------------------------------------

class IPaymentSchema(model.Schema):
    """A single payment against an invoice
    """

    title = schema.TextLine(
        title=_(u"Reference"),
        required=False,
    )

    amount = schema.TextLine(
        title=_(u"Amount"),
        default=u"0.00",
        required=True,
    )

    method = schema.Choice(
        title=_(u"Payment method"),
        vocabulary=PAYMENT_METHODS,
        required=False,
        default=u"cash",
    )

    payment_date = DatetimeField(
        title=_(u"Payment date"),
        required=False,
        default=None,
    )


@implementer(IPayment, IPaymentSchema)
class Payment(Item):
    """A payment recorded against an invoice
    """
    _catalogs = [SETUP_CATALOG]

    security = ClassSecurityInfo()

    @security.protected(permissions.View)
    def get_amount(self):
        return to_decimal(self.accessor("amount")(self))


# ---------------------------------------------------------------------------
#  Invoice (folderish document that holds the line items)
# ---------------------------------------------------------------------------

class IBillingInvoiceSchema(model.Schema):
    """Invoice content interface
    """

    title = schema.TextLine(
        title=_(u"Invoice number"),
        required=True,
    )

    client = UIDReferenceField(
        title=_(u"Client"),
        description=_(u"Client this invoice is billed to"),
        allowed_types=("Client", ),
        multi_valued=False,
        required=False,
    )

    invoice_date = DatetimeField(
        title=_(u"Invoice date"),
        required=False,
        default=None,
    )

    due_date = DatetimeField(
        title=_(u"Due date"),
        required=False,
        default=None,
    )

    currency = schema.Choice(
        title=_(u"Currency"),
        vocabulary="senaite.core.vocabularies.currencies",
        required=False,
        defaultFactory=default_currency,
    )

    exchange_rate = schema.TextLine(
        title=_(u"Exchange rate"),
        description=_(u"Base-currency to invoice-currency rate, frozen when "
                     u"the sample was billed"),
        required=False,
        default=u"1",
    )

    price_group = schema.Choice(
        title=_(u"Price group"),
        description=_(u"Billing scheme this invoice is priced under"),
        vocabulary=PRICE_GROUPS,
        required=False,
        default=u"cash",
    )

    payment_method = schema.Choice(
        title=_(u"Payment method"),
        description=_(u"How this invoice is settled"),
        vocabulary=PAYMENT_METHODS,
        required=False,
        default=u"cash",
    )

    subtotal = schema.TextLine(
        title=_(u"Subtotal"),
        required=False,
        default=u"0.00",
    )

    discount = schema.TextLine(
        title=_(u"Discount"),
        required=False,
        default=u"0.00",
    )

    vat = schema.TextLine(
        title=_(u"VAT"),
        required=False,
        default=u"0.00",
    )

    total = schema.TextLine(
        title=_(u"Total"),
        required=False,
        default=u"0.00",
    )

    amount_paid = schema.TextLine(
        title=_(u"Amount paid"),
        required=False,
        default=u"0.00",
    )

    notes = schema.Text(
        title=_(u"Notes"),
        required=False,
    )


@implementer(IBillingInvoice, IBillingInvoiceSchema)
class BillingInvoice(Container):
    """An invoice: groups billed line items for a client
    """
    _catalogs = [SETUP_CATALOG]

    security = ClassSecurityInfo()

    @security.protected(permissions.View)
    def get_line_items(self):
        """Return the contained BillingLineItem objects
        """
        return [obj for obj in self.objectValues()
                if getattr(obj, "portal_type", None) == "BillingLineItem"]

    @security.protected(permissions.ModifyPortalContent)
    def recalculate(self):
        """Recompute subtotal/vat/total from the contained line items and
        store the results as a frozen snapshot on the invoice.
        """
        subtotal = Decimal("0.0")
        vat = Decimal("0.0")
        for item in self.get_line_items():
            line = item.get_line_total()
            subtotal += line
            pct = to_decimal(item.accessor("vat_percentage")(item))
            vat += line * pct / Decimal("100")
        discount = to_decimal(self.accessor("discount")(self))
        total = subtotal - discount + vat
        self.accessor("subtotal") and self.mutator("subtotal")(
            self, u"{:.2f}".format(subtotal))
        self.mutator("vat")(self, u"{:.2f}".format(vat))
        self.mutator("total")(self, u"{:.2f}".format(total))
        return total

    @security.protected(permissions.View)
    def get_balance_due(self):
        """Total minus amount paid, as a Decimal
        """
        total = to_decimal(self.accessor("total")(self))
        paid = to_decimal(self.accessor("amount_paid")(self))
        return total - paid

    @security.protected(permissions.View)
    def is_overdue(self):
        """True when the invoice is issued (unsettled) and past its due date
        """
        if api.get_review_status(self) != "issued":
            return False
        due = self.accessor("due_date")(self)
        if not due:
            return False
        from senaite.core.api.dtime import to_DT
        from DateTime import DateTime
        return to_DT(due) < DateTime()

    @security.protected(permissions.View)
    def get_payments(self):
        """Return the Payment objects recorded against this invoice
        """
        return [obj for obj in self.objectValues()
                if getattr(obj, "portal_type", None) == "Payment"]

    @security.protected(permissions.ModifyPortalContent)
    def recompute_paid(self):
        """Recompute ``amount_paid`` from the recorded payments. When the
        invoice is fully settled, auto-advance it to the ``paid`` state.
        """
        paid = sum([p.get_amount() for p in self.get_payments()], Decimal("0"))
        self.mutator("amount_paid")(self, u"{:.2f}".format(paid))
        total = to_decimal(self.accessor("total")(self))
        if total > 0 and paid >= total:
            if api.get_review_status(self) == "issued":
                api.do_transition_for(self, "pay")
        recatalog(self)
        return paid
