import json

from django import forms
from django.utils.translation import gettext_lazy as _

from pretix.base.models import SeatingPlan
from pretix.base.models.seating import SeatingPlanLayoutValidator


class SeatingPlanImportForm(forms.Form):
    """Upload a seating plan JSON (e.g. exported from seats.pretix.eu).

    When ``instance`` is given, the existing plan's layout is replaced
    (the file becomes optional, so the name can be edited on its own).
    """

    name = forms.CharField(
        label=_("Name"),
        max_length=190,
        required=False,
        help_text=_("Leave empty to use the name from the uploaded file."),
    )
    file = forms.FileField(
        label=_("Seating plan file (JSON)"),
        required=True,
        help_text=_(
            "Upload a seating plan exported from the editor at seats.pretix.eu."
        ),
    )

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance is not None:
            # Editing: keep the current layout if no new file is uploaded.
            self.fields["file"].required = False
            self.fields["file"].help_text = _(
                "Upload a new JSON file to replace the layout, or leave empty "
                "to only change the name."
            )
            self.fields["name"].required = True
            self.fields["name"].help_text = ""
            self.initial.setdefault("name", instance.name)

    def clean_file(self):
        f = self.cleaned_data.get("file")
        if not f:
            return f
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
        plan = self.instance or SeatingPlan(organizer=organizer)
        data = self.cleaned_data.get("layout_data")
        name = self.cleaned_data.get("name")
        if data is not None:
            plan.layout = json.dumps(data)
        if name:
            plan.name = name
        elif not plan.name:
            plan.name = (data or {}).get("name") or _("Imported plan")
        plan.full_clean()
        plan.save()
        return plan
