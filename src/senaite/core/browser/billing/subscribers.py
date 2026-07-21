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

from senaite.core.content.billing import recatalog


def on_billing_object_event(obj, event):
    """Ensure billing objects (Invoice/LineItem/Payment) are catalogued in the
    SENAITE setup catalog when created or modified. The default multi-catalog
    behaviour gate skips freshly-created Dexterity objects, which would leave
    them out of the listing and summary; this force-catalogs them.
    """
    recatalog(obj)
