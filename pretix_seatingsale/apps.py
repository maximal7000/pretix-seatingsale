from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_seatingsale"
    verbose_name = "Seating Sale"

    class PretixPluginMeta:
        name = gettext_lazy("Seating Sale")
        author = "Max Herklotz"
        description = gettext_lazy("Interactive seat selection in the shop.")
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=4.16.0"

    def ready(self):
        from . import signals  # NOQA
