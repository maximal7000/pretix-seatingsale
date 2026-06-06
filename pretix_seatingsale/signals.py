import json

from django.dispatch import receiver
from django.template.loader import get_template
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _

from pretix.base.models import SeatCategoryMapping
from pretix.control.signals import nav_event, nav_organizer
from pretix.presale.signals import render_seating_plan

SEAT_ICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 448 512" '
    'class="svg-icon"><path d="M64 64a32 32 0 0 0-32 32v160a32 32 0 0 0 '
    '32 32h16v-96a64 64 0 0 1 64-64h160V96a32 32 0 0 0-32-32H64zm304 '
    '160H160a32 32 0 0 0-32 32v160a32 32 0 0 0 32 32h16v-32a16 16 0 0 1 '
    '32 0v32h128v-32a16 16 0 0 1 32 0v32h16a32 32 0 0 0 32-32V256a32 32 '
    '0 0 0-32-32z"/></svg>'
)


def _guid_to_category(plan):
    """Map every seat_guid to its category name from the plan layout."""
    out = {}
    if not plan:
        return out
    data = plan.layout_data
    for zone in data.get("zones", []):
        for row in zone.get("rows", []):
            for seat in row.get("seats", []):
                out[seat["seat_guid"]] = seat.get("category", "")
    return out


def _guid_to_rowpos(plan):
    """Map every seat_guid to its row's number-label position.

    Possible values from seats.pretix.eu: "left", "right", "both", "none".
    """
    out = {}
    if not plan:
        return out
    data = plan.layout_data
    for zone in data.get("zones", []):
        for row in zone.get("rows", []):
            pos = row.get("row_number_position", "both")
            for seat in row.get("seats", []):
                out[seat["seat_guid"]] = pos
    return out


def _areas(plan):
    """Collect non-seat decorations (stage, entrance, pillars, labels…).

    Areas are stored per zone with coordinates relative to the zone, so we
    add the zone offset to get absolute coordinates like the seats have.
    """
    out = []
    if not plan:
        return out
    data = plan.layout_data
    for zone in data.get("zones", []):
        zx = zone.get("position", {}).get("x", 0)
        zy = zone.get("position", {}).get("y", 0)
        for a in zone.get("areas", []):
            shape = a.get("shape")
            if not shape:
                continue
            ax = a.get("position", {}).get("x", 0)
            ay = a.get("position", {}).get("y", 0)
            area = {
                "shape": shape,
                "x": zx + ax,
                "y": zy + ay,
                "color": a.get("color", "#dddddd"),
                "border_color": a.get("border_color"),
                "rotation": a.get("rotation", 0),
            }
            if shape == "rectangle":
                rect = a.get("rectangle", {})
                area["width"] = rect.get("width", 0)
                area["height"] = rect.get("height", 0)
            elif shape == "circle":
                area["radius"] = a.get("circle", {}).get("radius", 0)
            elif shape == "ellipse":
                rad = a.get("ellipse", {}).get("radius", {})
                area["rx"] = rad.get("x", 0)
                area["ry"] = rad.get("y", 0)
            elif shape == "polygon":
                pts = a.get("polygon", {}).get("points", [])
                area["points"] = [
                    {"x": zx + p.get("x", 0), "y": zy + p.get("y", 0)}
                    for p in pts
                ]
            # A standalone text shape, or a label attached to any shape.
            txt = a.get("text")
            if txt:
                area["text"] = {
                    "text": txt.get("text", ""),
                    "color": txt.get("color", "#333333"),
                    "size": txt.get("size", 16),
                    "x": zx + ax + txt.get("position", {}).get("x", 0),
                    "y": zy + ay + txt.get("position", {}).get("y", 0),
                }
            out.append(area)
    return out


def _plan_for(event, subevent):
    if subevent is not None:
        return subevent.seating_plan
    return event.seating_plan


@receiver(render_seating_plan, dispatch_uid="seatingsale_render")
def render_seating_plan_receiver(sender, request, **kwargs):
    event = sender
    subevent = kwargs.get("subevent")
    plan = _plan_for(event, subevent)
    if not plan:
        return ""

    try:
        channel = request.sales_channel.identifier
    except AttributeError:
        channel = "web"

    # category -> color, in plan order
    colors = {}
    for c in plan.layout_data.get("categories", []):
        colors[c["name"]] = c.get("color", "#2980b9")

    guid_cat = _guid_to_category(plan)
    guid_rowpos = _guid_to_rowpos(plan)

    # category -> product (+ its variations) via SeatCategoryMapping
    maps = SeatCategoryMapping.objects.filter(
        event=event, subevent=subevent
    ).select_related("product")
    cat_product = {}
    for m in maps:
        item = m.product
        if item is None:
            continue
        variations = [
            {"id": v.pk, "name": str(v.value), "price": str(v.default_price)}
            for v in item.variations.filter(active=True)
        ]
        cat_product[m.layout_category] = {
            "item": item.pk,
            "item_name": str(item.name),
            "price": str(item.default_price),
            "variations": variations,
        }

    # seat objects, sorted by rank for stable rendering
    seats = []
    used_categories = set()
    qs = event.seats.filter(subevent=subevent).select_related("product").order_by(
        "sorting_rank", "seat_guid"
    )
    for s in qs:
        cat = guid_cat.get(s.seat_guid, "")
        used_categories.add(cat)
        prod = cat_product.get(cat)
        available = bool(prod) and not s.blocked and s.is_available(sales_channel=channel)
        seats.append({
            "guid": s.seat_guid,
            "x": s.x or 0,
            "y": s.y or 0,
            "cat": cat,
            "color": colors.get(cat, "#888888"),
            "name": s.name,
            "number": s.seat_number or "",
            "row": s.row_name or "",
            "rowpos": guid_rowpos.get(s.seat_guid, "both"),
            "available": available,
            "product": prod,
        })

    # Only categories that actually have seats, in plan order.
    categories = [
        {"name": n, "color": colors[n]}
        for n in colors
        if n in used_categories
    ]

    # Maximum number of items a customer may put in the cart in one order.
    try:
        max_per_order = int(event.settings.max_items_per_order)
    except (TypeError, ValueError):
        max_per_order = 10

    ctx = {
        "seats_json": json.dumps(seats),
        "categories_json": json.dumps(categories),
        "areas_json": json.dumps(_areas(plan)),
        "has_seats": len(seats) > 0,
        # Hide the category legend/filter when there is only one category.
        "show_categories": len(categories) > 1,
        "max_per_order": max_per_order,
    }
    template = get_template("pretixpresale/event/seatingsale_map.html")
    return template.render(ctx, request=request)


@receiver(nav_organizer, dispatch_uid="seatingsale_orga_nav")
def control_nav_orga(sender, request=None, **kwargs):
    if not request.user.has_organizer_permission(
        request.organizer, "can_change_organizer_settings", request=request
    ):
        return []
    url = resolve(request.path_info)
    return [
        {
            "label": _("Seating plans"),
            "url": reverse(
                "plugins:pretix_seatingsale:list",
                kwargs={"organizer": request.organizer.slug},
            ),
            "active": url.namespace == "plugins:pretix_seatingsale",
            "icon": "th",
        }
    ]


@receiver(nav_event, dispatch_uid="seatingsale_event_nav")
def control_nav_event(sender, request=None, **kwargs):
    if not request.user.has_event_permission(
        request.organizer, request.event, "can_change_event_settings",
        request=request,
    ):
        return []
    url = resolve(request.path_info)
    return [
        {
            "label": _("Seating"),
            "url": reverse(
                "plugins:pretix_seatingsale:assign",
                kwargs={
                    "organizer": request.organizer.slug,
                    "event": request.event.slug,
                },
            ),
            "active": url.namespace == "plugins:pretix_seatingsale"
            and url.url_name == "assign",
            "icon": "th",
        }
    ]
