#celery -A backend worker --pool=solo --loglevel=info
#celery -A backend beat --loglevel=info
# python manage.py runserver
#python -m venv .venv
# .\Scripts\activate
# pip install -r requirements.txt



#Make MySQL use system timezone
#SET GLOBAL time_zone = SYSTEM;
#SET time_zone = SYSTEM;


#Verify
#SELECT @@global.time_zone, @@session.time_zone, @@system_time_zone;
#SELECT NOW(), UTC_TIMESTAMP(), NOW() - UTC_TIMESTAMP() as difference;