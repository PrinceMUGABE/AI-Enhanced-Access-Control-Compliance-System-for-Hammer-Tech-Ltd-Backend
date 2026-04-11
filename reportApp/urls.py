# reportApp/urls.py
from django.urls import path
from .views import RoleBasedDashboardView, DashboardFiltersView, ExportDashboardView, ReportGenerationView, AvailableReportTypesView, ReportHistoryView

urlpatterns = [
    path('dashboard/', RoleBasedDashboardView.as_view(), name='role-dashboard'),
    path('dashboard/filters/', DashboardFiltersView.as_view(), name='dashboard-filters'),
    path('dashboard/export/', ExportDashboardView.as_view(), name='export-dashboard'),

    path('reports/generate/', ReportGenerationView.as_view(), name='generate-report'),
    path('reports/types/', AvailableReportTypesView.as_view(), name='available-report-types'),
    path('reports/history/', ReportHistoryView.as_view(), name='report-history'),
]