import json

from django.dispatch import receiver
from django.template.loader import get_template

from pretix.base.models import SeatCategoryMapping
from pretix.presale.signals import render_seating_plan


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

    # category -> color
    colors = {}
    for c in plan.layout_data.get("categories", []):
        colors[c["name"]] = c.get("color", "#2980b9")

    guid_cat = _guid_to_category(plan)

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
    qs = event.seats.filter(subevent=subevent).select_related("product").order_by(
        "sorting_rank", "seat_guid"
    )
    for s in qs:
        cat = guid_cat.get(s.seat_guid, "")
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
            "available": available,
            "product": prod,
        })

    ctx = {
        "seats_json": json.dumps(seats),
        "categories_json": json.dumps([
            {"name": n, "color": colors[n]} for n in colors
        ]),
        "has_seats": len(seats) > 0,
    }
    template = get_template("pretixpresale/event/seatingsale_map.html")
    return template.render(ctx, request=request)
