import zipfile
import glob
import os
import re
import sys
import json
import platform
from datetime import datetime, timezone

# Parse Facebook files
#facebook_zips = glob.glob('./inbox/*_facebook.zip')
#for fbz in facebook_zips:
#    with zipfile.ZipFile(fbz,"r") as zip_ref:
#        zip_ref.extractall("./inbox/temp")

temp_out = os.path.join('src', 'inbox', 'temp')

if len(sys.argv) != 2:
    sys.exit("ERROR: Path to zips required")
unzips = os.listdir(temp_out)
fb_regex = re.compile(r'.*_facebook$')
facebook_unzips = list(filter(fb_regex.search, unzips))

for fbu in facebook_unzips:
    comments_path = os.path.join(temp_out, fbu, 'comments', 'comments.json')
    comments_json = open(comments_path).read()
    comments = json.loads(comments_json)['comments']
    for comment in comments:
        timestamp = datetime.fromtimestamp(comment['timestamp'], timezone.utc)
        if 'attachments' in comment:
            print('FOUND ATTACHMENT: {0}'.format(comment['attachments'][0]['data'][0]['external_context']['url']))
        comment_date = timestamp.date()
        comment_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
        #print(comment['data'][0]['comment']['comment'] or '### NO COMMENT ###')
        #print('{0} @ {1}'.format(comment_date, comment_time))

