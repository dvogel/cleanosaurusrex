import json
import sys
import urllib2
import unicodecsv as csv

res = urllib2.urlopen('http://sunlightfoundation.com/team/?json')
staff = json.load(res)

writer = csv.writer(sys.stdout)
writer.writerow(('first_name','last_name','email','avatar_url'))

for role in ('president', 'general_staff'):
    for employee in staff[role]:
        writer.writerow((
            employee['first_name'],
            employee['last_name'],
            employee['email'],
            employee['avatar_alt'] # Cheeky diversion
        ))
