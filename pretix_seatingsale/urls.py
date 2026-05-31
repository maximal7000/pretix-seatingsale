from django.urls import path

from . import views

urlpatterns = [
    path(
        "control/organizer/<str:organizer>/seatingsale/",
        views.SeatingPlanList.as_view(),
        name="list",
    ),
    path(
        "control/organizer/<str:organizer>/seatingsale/import/",
        views.SeatingPlanImport.as_view(),
        name="import",
    ),
    path(
        "control/organizer/<str:organizer>/seatingsale/<int:plan>/edit/",
        views.SeatingPlanEdit.as_view(),
        name="edit",
    ),
    path(
        "control/organizer/<str:organizer>/seatingsale/<int:plan>/delete/",
        views.SeatingPlanDelete.as_view(),
        name="delete",
    ),
    path(
        "control/event/<str:organizer>/<str:event>/seatingsale/",
        views.SeatingAssign.as_view(),
        name="assign",
    ),
]
