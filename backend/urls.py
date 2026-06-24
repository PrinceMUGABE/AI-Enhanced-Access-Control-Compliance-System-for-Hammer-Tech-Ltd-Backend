# urls.py - ROOT URLS
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('userApp.urls')),
    path('departments/', include('departmentApp.urls')),
    path('incidents/', include('incidentApp.urls', namespace='incidents')),
    path('risk-assessment/', include('riskAssessmentApp.urls')),
    path('compliance-audit/', include('complianceAuditApp.urls')),
    path('training/', include('trainingApp.urls')),
    path('candidate/', include('trainingCandidateApp.urls')),
    path('progress/', include('learningProgressApp.urls')),
    path('reports/', include('reportApp.urls')),
    path('notifications/', include('notificationApp.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)