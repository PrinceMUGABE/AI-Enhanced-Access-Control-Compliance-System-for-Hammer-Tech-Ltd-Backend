# Run in Django shell
from incidentApp.models import Incident
from userApp.models import CustomUser

# Assign department based on created_by user
for incident in Incident.objects.filter(department__isnull=True):
    if incident.created_by and incident.created_by.department:
        incident.department = incident.created_by.department
        incident.save()
        print(f"Assigned incident {incident.incident_number} to department {incident.department.name}")
    elif incident.assigned_to and incident.assigned_to.department:
        incident.department = incident.assigned_to.department
        incident.save()
        print(f"Assigned incident {incident.incident_number} to department {incident.department.name}")