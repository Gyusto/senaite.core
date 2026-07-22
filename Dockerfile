# SENAITE with the Billing add-on baked in.
#
# Starts from the official image (which already contains senaite.core, senaite.lims
# and their dependencies installed via buildout) and overlays this fork's source over
# the installed senaite.core package. The egg-info is left untouched so z3c.autoinclude
# still discovers the package. The site itself is created on first boot by the stock
# entrypoint, driven by the SITE / PROFILES / PASSWORD environment variables.
FROM senaite/senaite:edge

# Overlay the billing fork on top of the installed senaite.core source.
COPY --chown=senaite:senaite src/bika    /home/senaite/senaitelims/src/senaite.core/src/bika
COPY --chown=senaite:senaite src/senaite /home/senaite/senaitelims/src/senaite.core/src/senaite

EXPOSE 8080
