import zipfile
import glob
import os
import re
import sys
import json
import platform
import csv
from datetime import datetime, timezone
from collections import defaultdict

def genCSV(filename, content):
    # Generate CSVs from data
    csv_out = os.path.join(outbox_path, fbu, filename)
    os.makedirs(os.path.dirname(csv_out), exist_ok=True)
    with open(csv_out, "w+", encoding='utf-8') as csv_file:
        csv_writer = csv.writer(csv_file, quoting=csv.QUOTE_ALL, lineterminator = '\n')
        for entry in content:
            csv_writer.writerow(entry)

# Parse Facebook files
'''facebook_zips = glob.glob('./inbox/*_facebook.zip')
for fbz in facebook_zips:
    with zipfile.ZipFile(fbz,"r") as zip_ref:
        zip_ref.extractall("./inbox/temp")'''

temp_out = os.path.join('inbox', 'temp')
outbox_path = os.path.join('outbox')

if len(sys.argv) != 2:
    sys.exit("ERROR: Path to zips required")

# ID extracted datasets
unzips = os.listdir(temp_out)
fb_regex = re.compile(r'.*_facebook$')
facebook_unzips = list(filter(fb_regex.search, unzips))

# Parse extracted Facebook datasets
for fbu in facebook_unzips:
    # Parse comments and likes
    comments_path = os.path.join(temp_out, fbu, 'comments', 'comments.json')
    comments_json = open(comments_path).read()
    comments = json.loads(comments_json)['comments']
    comments_parsed = [['Date', 'Time', 'Author', 'Comment', 'URL']]
    for comment in comments:
        # Extract comment details
        timestamp = datetime.fromtimestamp(comment['timestamp'], timezone.utc)
        comment_date = timestamp.date()
        comment_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
        comment_attachment = comment['attachments'][0]['data'][0]['external_context']['url'] if 'attachments' in comment else ''
        comment_text = comment['data'][0]['comment']['comment'] if 'comment' in comment['data'][0]['comment'] else ''
        comment_author = comment['data'][0]['comment']['author']
        comments_parsed.append([comment_date, comment_time, comment_author, comment_text, comment_attachment])

    genCSV('comments.csv', comments_parsed)

    # Parse reactions
    reactions_path = os.path.join(temp_out, fbu, 'likes_and_reactions', 'posts_and_comments.json')
    reactions_json = open(reactions_path).read()
    reactions = json.loads(reactions_json)['reactions']
    categories = ['photo', 'comment', 'post', 'link', 'album', 'video', 'other']
    reactions_parsed = [['From', 'To', 'Author'] + categories]
    react_totals = defaultdict(lambda: defaultdict(int))
    start_date = end_date = False
    for reaction in reactions:
        # Extract reaction details
        timestamp = datetime.fromtimestamp(reaction['timestamp'], timezone.utc)
        if not start_date or not end_date:
            start_date = end_date = timestamp
        if(abs((start_date - timestamp).days) > 7):
            tmp_week = []
            for cat in categories:
                tmp_cat = ''
                for react in react_totals[cat]:
                    tmp_cat += react + ': ' + str(react_totals[cat][react]) + ' '
                tmp_week.append(tmp_cat)
            reactions_parsed.append([end_date.date(), start_date.date(), reaction['data'][0]['reaction']['actor']] + tmp_week)
            start_date = end_date = timestamp
            react_totals = defaultdict(lambda: defaultdict(int))
        else:
            end_date = timestamp

        category = next((cat for cat in categories if cat in reaction['title']), 'other')
        react_totals[category][reaction['data'][0]['reaction']['reaction']] += 1

    genCSV('reactions.csv', reactions_parsed)

    '''# Parse posts
    posts_path = os.path.join(temp_out, fbu, 'posts', 'your_posts.json')
    posts_json = open(posts_path).read()
    posts = json.loads(posts_json)['status_updates']
    posts_parsed = [['Date', 'Time', 'Author', 'Post', 'Comments', 'Media']]
    for post in posts:
        # Extract comment details
        timestamp = datetime.fromtimestamp(comment['timestamp'], timezone.utc)
        comment_date = timestamp.date()
        comment_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")'''
