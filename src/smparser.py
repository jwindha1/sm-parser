import zipfile
import glob
import os
import re
import sys
import json
import platform
import csv
from datetime import datetime, timezone

# Parse Facebook files
#facebook_zips = glob.glob('./inbox/*_facebook.zip')
#for fbz in facebook_zips:
#    with zipfile.ZipFile(fbz,"r") as zip_ref:
#        zip_ref.extractall("./inbox/temp")

temp_out = os.path.join('src', 'inbox', 'temp')
outbox_path = os.path.join('src', 'outbox')

if len(sys.argv) != 2:
    sys.exit("ERROR: Path to zips required")

# ID extracted datasets
unzips = os.listdir(temp_out)
fb_regex = re.compile(r'.*_facebook$')
facebook_unzips = list(filter(fb_regex.search, unzips))

# Parse extracted Facebook datasets
for fbu in facebook_unzips:
    comments_path = os.path.join(temp_out, fbu, 'comments', 'comments.json')
    comments_json = open(comments_path).read()
    comments = json.loads(comments_json)['comments']
    comments_parsed = [['Date', 'Time', 'Author', 'Comment', 'URL']]
    for comment in comments:
        timestamp = datetime.fromtimestamp(comment['timestamp'], timezone.utc)

        # Extract comment details
        comment_attachment = comment['attachments'][0]['data'][0]['external_context']['url'] if 'attachments' in comment else ''
        comment_date = timestamp.date()
        comment_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
        comment_text = comment['data'][0]['comment']['comment'] if 'comment' in comment['data'][0]['comment'] else ''
        comment_author = comment['data'][0]['comment']['author']
        comments_parsed.append([comment_date, comment_time, comment_author, bytes(comment_text, 'ascii', 'ignore').decode('unicode-escape'), comment_attachment])

    # Generate CSVs from data
    comment_csv = os.path.join(outbox_path, fbu, 'comments.csv')
    os.makedirs(os.path.dirname(comment_csv), exist_ok=True)
    with open(comment_csv, "w+") as csv_file:
        csv_writer = csv.writer(csv_file, quoting=csv.QUOTE_ALL, lineterminator = '\n')
        for comment in comments_parsed:
            csv_writer.writerow(comment)

