from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils.timezone import now
from django_scopes import scope

from pretix.base.models import (
    CartPosition,
    Event,
    Order,
    OrderPosition,
    Organizer,
    Voucher,
)
from pretix_seatingsale.signals import _available_seat_ids


@pytest.mark.django_db
def test_available_seat_ids_matches_seat_api_and_uses_one_query(django_assert_num_queries):
    organizer = Organizer.objects.create(name="Test", slug="availability-test")
    with scope(organizer=organizer):
        event = Event.objects.create(
            organizer=organizer,
            name="Test",
            slug="availability-test",
            date_from=now(),
            date_to=now() + timedelta(hours=1),
        )
        item = event.items.create(name="Ticket", default_price=Decimal("10.00"))
        event.settings.seating_allow_blocked_seats_for_channel = ["pos"]

        free = event.seats.create(seat_guid="free")
        blocked = event.seats.create(seat_guid="blocked", blocked=True)
        cart_reserved = event.seats.create(seat_guid="cart")
        order_reserved = event.seats.create(seat_guid="order")
        voucher_reserved = event.seats.create(seat_guid="voucher")

        CartPosition.objects.create(
            event=event,
            cart_id="active-cart",
            item=item,
            seat=cart_reserved,
            price=Decimal("10.00"),
            expires=now() + timedelta(minutes=10),
        )
        order = Order.objects.create(
            code="ORDER1",
            event=event,
            email="buyer@example.test",
            total=Decimal("10.00"),
            sales_channel=organizer.sales_channels.get(identifier="web"),
            locale="en",
            status=Order.STATUS_PENDING,
            datetime=now(),
            expires=now() + timedelta(days=1),
        )
        OrderPosition.objects.create(
            order=order,
            item=item,
            variation=None,
            price=Decimal("10.00"),
            seat=order_reserved,
        )
        Voucher.objects.create(
            event=event,
            code="SEAT1",
            item=item,
            seat=voucher_reserved,
            valid_until=now() + timedelta(minutes=10),
        )

        # Prime the event settings before measuring the availability query.
        assert event.settings.seating_allow_blocked_seats_for_channel == ["pos"]
        assert event.settings.seating_minimal_distance == 0
        assert not event.settings.seating_distance_within_row

        with django_assert_num_queries(1):
            web_available = _available_seat_ids(event, None, "web")

        expected_web = {
            seat.pk for seat in (free, blocked, cart_reserved, order_reserved, voucher_reserved)
            if seat.is_available(sales_channel="web")
        }
        assert web_available == expected_web

        pos_available = _available_seat_ids(event, None, "pos")
        expected_pos = {
            seat.pk for seat in (free, blocked, cart_reserved, order_reserved, voucher_reserved)
            if seat.is_available(sales_channel="pos")
        }
        assert pos_available == expected_pos
        assert blocked.pk not in web_available
        assert blocked.pk in pos_available


@pytest.mark.django_db
def test_available_seat_ids_are_scoped_to_subevent():
    organizer = Organizer.objects.create(name="Test", slug="subevent-availability-test")
    with scope(organizer=organizer):
        event = Event.objects.create(
            organizer=organizer,
            name="Series",
            slug="subevent-availability-test",
            date_from=now(),
            date_to=now() + timedelta(days=2),
        )
        subevent = event.subevents.create(name="Date 1", date_from=now())
        event_seat = event.seats.create(seat_guid="event-seat")
        subevent_seat = event.seats.create(seat_guid="subevent-seat", subevent=subevent)
        CartPosition.objects.create(
            event=event,
            subevent=subevent,
            cart_id="date-cart",
            seat=subevent_seat,
            price=Decimal("0.00"),
            expires=now() + timedelta(minutes=10),
        )

        assert subevent.settings.seating_minimal_distance == 0
        assert not subevent.settings.seating_distance_within_row
        with django_assert_num_queries(1):
            available = _available_seat_ids(event, subevent, "web")

        expected = (
            {subevent_seat.pk}
            if subevent_seat.is_available(sales_channel="web")
            else set()
        )
        assert available == expected
        assert event_seat.pk not in available
