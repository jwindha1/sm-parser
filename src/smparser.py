import zipfile
import glob
import os
import re
import sys
import json
import platform
import csv
import scrubadub
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import face_recognition
import cv2
from shutil import copyfile
import pathlib

def blurFaces(image):
    img = cv2.imread(image)
    faces = face_recognition.face_locations(img)

    for (top, right, bottom, left) in faces:
        face_image = img[top:bottom, left:right]
        face_image = cv2.GaussianBlur(face_image, (99, 99), 30)
        img[top:bottom, left:right] = face_image

    return img

def genCSV(filename, content):
    # Generate CSVs from data
    csv_out = os.path.join(outbox_path, fbu, filename)
    os.makedirs(os.path.dirname(csv_out), exist_ok=True)
    with open(csv_out, "w+", encoding='utf-8') as csv_file:
        csv_writer = csv.writer(csv_file, quoting=csv.QUOTE_ALL, lineterminator = '\n')
        for entry in content:
            csv_writer.writerow(entry)

# Parse Facebook files
print('Unzipping facebook data dumps...', flush=True)
facebook_zips = glob.glob('./inbox/*_facebook.zip')
fbz_counter = 1
for fbz in facebook_zips:
    print('Unzipping {0} of {1} archives...'.format(fbz_counter, len(facebook_zips)), end='\r', flush=True)
    fbz_counter += 1
    with zipfile.ZipFile(fbz,"r") as zip_ref:
        zip_ref.extractall("./inbox/temp")

temp_out = os.path.join('inbox', 'temp')
outbox_path = os.path.join('outbox')

if len(sys.argv) != 2:
    sys.exit("ERROR: Path to zips required")

# ID extracted datasets
unzips = os.listdir(temp_out)
fb_regex = re.compile(r'.*_facebook$')
facebook_unzips = list(filter(fb_regex.search, unzips))

# Parse extracted Facebook datasets
print('Parsing unzipped facebook data dumps...', flush=True)
for fbu in facebook_unzips:
    print('Parsing comments and likes of {0} data dump...'.format(fbu), flush=True)
    # Parse comments and likes
    comments_path = os.path.join(temp_out, fbu, 'comments', 'comments.json')
    comments_json = open(comments_path).read()
    comments = json.loads(comments_json)['comments']
    comments_parsed = [['Date', 'Time', 'Author', 'Comment', 'URL']]
    for comment in comments:
        if datetime.fromtimestamp(comment['timestamp']) < datetime.now()-timedelta(days=183):
            continue
        # Extract comment details
        timestamp = datetime.fromtimestamp(comment['timestamp'], timezone.utc)
        comment_date = timestamp.date()
        comment_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
        comment_attachment = comment['attachments'][0]['data'][0]['external_context']['url'] if 'attachments' in comment else ''
        comment_text = scrubadub.clean(comment['data'][0]['comment']['comment']) if 'comment' in comment['data'][0]['comment'] else ''
        comment_author = comment['data'][0]['comment']['author']
        comments_parsed.append([comment_date, comment_time, comment_author, comment_text, comment_attachment])

    genCSV('comments.csv', comments_parsed)

    # Parse reactions
    print('Parsing reactions of {0} data dump...'.format(fbu), flush=True)
    reactions_path = os.path.join(temp_out, fbu, 'likes_and_reactions', 'posts_and_comments.json')
    reactions_json = open(reactions_path).read()
    reactions = json.loads(reactions_json)['reactions']
    categories = ['photo', 'comment', 'post', 'link', 'album', 'video', 'other']
    reactions_parsed = [['From', 'To', 'Author'] + categories]
    react_totals = defaultdict(lambda: defaultdict(int))
    start_date = end_date = False
    for reaction in reactions:
        if datetime.fromtimestamp(reaction['timestamp']) < datetime.now()-timedelta(days=183):
            continue
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

    # Parse posts
    print('Parsing posts of {0} data dump...'.format(fbu), flush=True)
    media_root = os.path.join(outbox_path, fbu, 'media')
    pathlib.Path(media_root).mkdir(parents=True, exist_ok=True)
    posts_path = os.path.join(temp_out, fbu, 'posts', 'your_posts.json')
    posts_json = open(posts_path).read()
    posts = json.loads(posts_json)['status_updates']
    posts_parsed = [['Date', 'Time', 'Post', 'Caption', 'Comments']]
    media_id = 0
    supported_types = ['.bmp', '.jpeg', '.jpg', '.jpe', '.png', '.tiff', '.tif']
    post_counter = 1
    for post in posts:
        print('Parsing {0} of {1} posts...'.format(post_counter, len(posts)), end='\r', flush=True)
        post_counter += 1
        # Extract comment details
        if datetime.fromtimestamp(post['timestamp']) < datetime.now()-timedelta(days=183):
            continue
        timestamp = datetime.fromtimestamp(post['timestamp'], timezone.utc)
        post_date = timestamp.date()
        post_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
        if 'data' in post:
            if 'post' in post['data'][0]:
                caption = scrubadub.clean(post['data'][0]['post'])
            else:
                continue
        elif 'title' in post:
            caption = scrubadub.clean(post['title'])
        else:
            continue
        if 'attachments' in post:
            attachments = post['attachments'][0]['data']
            for attachment in attachments:
                if 'media' in attachment:
                    content = attachment['media']
                    media = content['uri']
                elif 'external_context' in attachment:
                    content = attachment['external_context']
                    caption += ': ' + content['url']
                    media = ''
                comments = ''
                if 'comments' in content:
                    for comment in content['comments']:
                        comments += '"' + scrubadub.clean(comment['comment']) + '", '
                scrubadub.clean(caption)
                media_src = os.path.join(temp_out, fbu, media)
                filename, file_extension = os.path.splitext(media)
                media_dest = os.path.join(media_root, '{0}{1}'.format(media_id, file_extension))
                media_id += 1
                if file_extension in supported_types:
                    cv2.imwrite(media_dest, blurFaces(media_src))
                else:
                    copyfile(media_src, media_dest)
                entry = [post_date, post_time, media_dest, caption, comments]
                posts_parsed.append(entry)
    genCSV('posts.csv', posts_parsed)
