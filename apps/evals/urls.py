from django.urls import path

from . import views

urlpatterns = [
    path("<int:skill_id>/", views.eval_suite_detail, name="eval-suite-detail"),
    path("<int:skill_id>/run/", views.run_eval, name="run-eval"),
    path("<int:skill_id>/history/", views.eval_history, name="eval-history"),
    path("<int:skill_id>/cases/", views.propose_eval_case, name="propose-eval-case"),
]
