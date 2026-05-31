import json

from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import FormView, ListView

from pretix.base.models import SeatingPlan
from pretix.control.permissions import OrganizerPermissionRequiredMixin

from .forms import SeatingPlanImportForm


class SeatingPlanList(OrganizerPermissionRequiredMixin, ListView):
    model = SeatingPlan
    context_object_name = "plans"
    permission = "can_change_organizer_settings"
    template_name = "pretix_seatingsale/control/list.html"

    def get_queryset(self):
        return SeatingPlan.objects.filter(
            organizer=self.request.organizer
        ).order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        plans = []
        for p in ctx["plans"]:
            try:
                data = p.layout_data
                seats = sum(
                    len(r.get("seats", []))
                    for z in data.get("zones", [])
                    for r in z.get("rows", [])
                )
                cats = len(data.get("categories", []))
            except (ValueError, KeyError):
                seats, cats = 0, 0
            plans.append({"obj": p, "seats": seats, "categories": cats})
        ctx["plans_info"] = plans
        return ctx


class SeatingPlanImport(OrganizerPermissionRequiredMixin, FormView):
    form_class = SeatingPlanImportForm
    permission = "can_change_organizer_settings"
    template_name = "pretix_seatingsale/control/import.html"

    def get_success_url(self):
        return reverse(
            "plugins:pretix_seatingsale:list",
            kwargs={"organizer": self.request.organizer.slug},
        )

    def form_valid(self, form):
        plan = form.save(self.request.organizer)
        messages.success(
            self.request,
            _('Seating plan "{name}" has been imported.').format(name=plan.name),
        )
        return redirect(self.get_success_url())
