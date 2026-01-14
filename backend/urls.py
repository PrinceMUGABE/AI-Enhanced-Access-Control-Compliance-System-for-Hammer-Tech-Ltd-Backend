# urls.py - ROOT URLS
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('userApp.urls')),
    path('onboarding/', include('onboarding.urls')),
    path('mentorship/', include('mentorshipApp.urls')),
    path('departments/', include('departmentApp.urls')),
    path('chats/', include('chatApp.urls')),
    path('notifications/', include('notificationApp.urls')),  # This should work
    path('assistance/', include('assistanceApp.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)