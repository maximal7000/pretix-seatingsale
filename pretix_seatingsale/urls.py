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
]
