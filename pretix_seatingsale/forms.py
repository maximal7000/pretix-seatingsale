import json

from django import forms
from django.utils.translation import gettext_lazy as _

from pretix.base.models import SeatingPlan
from pretix.base.models.seating import SeatingPlanLayoutValidator


class SeatingPlanImportForm(forms.Form):
    """Upload a seating plan JSON (e.g. exported from seats.pretix.eu)."""

    name = forms.CharField(
        label=_("Name"),
        max_length=190,
        required=False,
        help_text=_("Leave empty to use the name from the uploaded file."),
    )
    file = forms.FileField(
        label=_("Seating plan file (JSON)"),
        help_text=_(
            "Upload a seating plan exported from the editor at seats.pretix.eu."
        ),
    )

    def clean_file(self):
        f = self.cleaned_data["file"]
        try:
            raw = f.read().decode("utf-8")
        except UnicodeDecodeError:
            raise forms.ValidationError(_("The file is not valid UTF-8 text."))
        try:
            data = json.loads(raw)
        except ValueError:
            raise forms.ValidationError(_("The file does not contain valid JSON."))
        # Validate against pretix' own seating plan schema.
        SeatingPlanLayoutValidator()(data)
        self.cleaned_data["layout_data"] = data
        return f

    def save(self, organizer):
        data = self.cleaned_data["layout_data"]
        name = self.cleaned_data.get("name") or data.get("name") or _("Imported plan")
        plan = SeatingPlan(organizer=organizer, name=name)
        plan.layout = json.dumps(data)
        plan.full_clean()
        plan.save()
        return plan
