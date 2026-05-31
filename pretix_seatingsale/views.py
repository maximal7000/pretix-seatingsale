import json

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.generic import DeleteView, FormView, ListView, TemplateView

from pretix.base.models import (
    Item, SeatCategoryMapping, SeatingPlan, SubEvent,
)
from pretix.base.services.seating import (
    SeatProtected, generate_seats, validate_plan_change,
)
from pretix.control.permissions import (
    EventPermissionRequiredMixin, OrganizerPermissionRequiredMixin,
)

from .forms import SeatingPlanImportForm


def _plan_stats(plan):
    try:
        data = plan.layout_data
        seats = sum(
            len(r.get("seats", []))
            for z in data.get("zones", [])
            for r in z.get("rows", [])
        )
        cats = [c["name"] for c in data.get("categories", [])]
    except (ValueError, KeyError):
        seats, cats = 0, []
    return seats, cats


# --------------------------------------------------------------------------
# Organizer level: list / import / edit / delete seating plans
# --------------------------------------------------------------------------

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
        info = []
        for p in ctx["plans"]:
            seats, cats = _plan_stats(p)
            in_use = p.events.exists() or SubEvent.objects.filter(
                seating_plan=p
            ).exists()
            info.append({
                "obj": p,
                "seats": seats,
                "categories": len(cats),
                "in_use": in_use,
            })
        ctx["plans_info"] = info
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


class SeatingPlanEdit(OrganizerPermissionRequiredMixin, FormView):
    form_class = SeatingPlanImportForm
    permission = "can_change_organizer_settings"
    template_name = "pretix_seatingsale/control/edit.html"

    def get_object(self):
        return get_object_or_404(
            SeatingPlan,
            organizer=self.request.organizer,
            pk=self.kwargs["plan"],
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.get_object()
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["plan"] = self.get_object()
        return ctx

    def get_success_url(self):
        return reverse(
            "plugins:pretix_seatingsale:list",
            kwargs={"organizer": self.request.organizer.slug},
        )

    def form_valid(self, form):
        plan = form.save(self.request.organizer)
        messages.success(
            self.request,
            _('Seating plan "{name}" has been updated.').format(name=plan.name),
        )
        return redirect(self.get_success_url())


class SeatingPlanDelete(OrganizerPermissionRequiredMixin, DeleteView):
    model = SeatingPlan
    permission = "can_change_organizer_settings"
    template_name = "pretix_seatingsale/control/delete.html"
    context_object_name = "plan"

    def get_object(self, queryset=None):
        return get_object_or_404(
            SeatingPlan,
            organizer=self.request.organizer,
            pk=self.kwargs["plan"],
        )

    def get_success_url(self):
        return reverse(
            "plugins:pretix_seatingsale:list",
            kwargs={"organizer": self.request.organizer.slug},
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        plan = ctx["plan"]
        ctx["in_use"] = plan.events.exists() or SubEvent.objects.filter(
            seating_plan=plan
        ).exists()
        return ctx

    def form_valid(self, form):
        plan = self.get_object()
        if plan.events.exists() or SubEvent.objects.filter(seating_plan=plan).exists():
            messages.error(
                self.request,
                _("This seating plan is still assigned to an event or date and "
                  "cannot be deleted."),
            )
            return redirect(self.get_success_url())
        name = plan.name
        plan.delete()
        messages.success(
            self.request,
            _('Seating plan "{name}" has been deleted.').format(name=name),
        )
        return redirect(self.get_success_url())


# --------------------------------------------------------------------------
# Event level: assign a plan to the event / each date + map categories
# --------------------------------------------------------------------------

class SeatingAssign(EventPermissionRequiredMixin, TemplateView):
    permission = "can_change_event_settings"
    template_name = "pretix_seatingsale/control/assign.html"

    @property
    def _targets(self):
        """The objects a plan can be assigned to: the event, or its dates."""
        ev = self.request.event
        if ev.has_subevents:
            return list(ev.subevents.all().order_by("date_from"))
        return [ev]

    def _target_by_key(self, key):
        ev = self.request.event
        if ev.has_subevents:
            if key.startswith("se_"):
                return ev.subevents.filter(pk=int(key[3:])).first()
            return None
        return ev if key == "event" else None

    @staticmethod
    def _target_key(target):
        return "se_%d" % target.pk if isinstance(target, SubEvent) else "event"

    def _plan_choices(self):
        return SeatingPlan.objects.filter(
            organizer=self.request.organizer
        ).order_by("name")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ev = self.request.event
        plans = list(self._plan_choices())
        items = list(ev.items.filter(active=True).prefetch_related("variations"))

        rows = []
        for target in self._targets:
            key = self._target_key(target)
            plan = target.seating_plan
            cat_names = []
            if plan:
                _, cat_names = _plan_stats(plan)
            mappings = {
                m.layout_category: m.product_id
                for m in SeatCategoryMapping.objects.filter(
                    event=ev,
                    subevent=target if isinstance(target, SubEvent) else None,
                )
            }
            categories = [
                {"name": cat, "selected_pid": mappings.get(cat)}
                for cat in cat_names
            ]
            rows.append({
                "key": key,
                "label": str(target.name) if isinstance(target, SubEvent)
                else str(ev.name),
                "is_subevent": isinstance(target, SubEvent),
                "plan": plan,
                "categories": categories,
            })

        ctx["has_subevents"] = ev.has_subevents
        ctx["plans"] = plans
        ctx["items"] = items
        ctx["rows"] = rows
        return ctx

    def post(self, request, *args, **kwargs):
        ev = request.event
        key = request.POST.get("target")
        target = self._target_by_key(key)
        if target is None:
            messages.error(request, _("Unknown target."))
            return redirect(request.path)

        plan_id = request.POST.get("plan") or ""
        plan = None
        if plan_id:
            plan = SeatingPlan.objects.filter(
                organizer=request.organizer, pk=plan_id
            ).first()

        subevent = target if isinstance(target, SubEvent) else None

        try:
            with transaction.atomic():
                # Guard: a plan change must not drop already-sold seats.
                validate_plan_change(ev, subevent, plan)

                target.seating_plan = plan
                target.save()

                SeatCategoryMapping.objects.filter(
                    event=ev, subevent=subevent
                ).delete()

                mapping = {}
                if plan:
                    _, cats = _plan_stats(plan)
                    for cat in cats:
                        pid = request.POST.get("map_%s" % cat)
                        if not pid:
                            continue
                        item = ev.items.filter(pk=pid).first()
                        if not item:
                            continue
                        SeatCategoryMapping.objects.create(
                            event=ev, subevent=subevent,
                            layout_category=cat, product=item,
                        )
                        mapping[cat] = item

                generate_seats(ev, subevent, plan, mapping)
        except SeatProtected as e:
            messages.error(request, str(e))
            return redirect(request.path)

        messages.success(request, _("Seating configuration has been saved."))
        return redirect(request.path)
