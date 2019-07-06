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
import instaloader
from itertools import dropwhile, takewhile

months_back = 8
days_back = months_back*30.4375
supported_types = ['.bmp', '.jpeg', '.jpg', '.jpe', '.png', '.tiff', '.tif']
outbox_path = os.path.join('outbox')

def blurFaces(image):
    img = cv2.imread(image)
    faces = face_recognition.face_locations(img)

    for (top, right, bottom, left) in faces:
        face_image = img[top:bottom, left:right]
        face_image = cv2.GaussianBlur(face_image, (99, 99), 30)
        img[top:bottom, left:right] = face_image

    return img

def genCSV(folder, filename, content):
    # Generate CSVs from data
    csv_out = os.path.join(outbox_path, folder, filename)
    os.makedirs(os.path.dirname(csv_out), exist_ok=True)
    with open(csv_out, "w+", encoding='utf-8') as csv_file:
        csv_writer = csv.writer(csv_file, quoting=csv.QUOTE_ALL, lineterminator = '\n')
        for entry in content:
            csv_writer.writerow(entry)

# Pull Instagram data from web
posts_parsed = [['Date', 'Time', 'Media', 'Caption', 'Likes', 'Comments']]
L = instaloader.Instaloader()
user_name = input('Please enter subject\'s Instagram username: ')
L.interactive_login(user_name)
igu = user_name + ' - IG ONLY'
media_root = os.path.join(outbox_path, igu, 'media')
pathlib.Path(media_root).mkdir(parents=True, exist_ok=True)
profile = instaloader.Profile.from_username(L.context, user_name)
posts = profile.get_posts()

follow_parsed = [
    ['Followers', 'Followees'],
    [profile.followers, profile.followees]
    ]

genCSV(igu, 'following.csv', follow_parsed)

SINCE = datetime.today()
UNTIL = SINCE - timedelta(days=days_back)
post_count = 0
print('Parsing {0}\'s media...'.format(user_name), flush=True)
for post in takewhile(lambda p: p.date > UNTIL, dropwhile(lambda p: p.date > SINCE, posts)):
    try:
        media_dest = os.path.join(media_root, str(post_count))
        L.download_pic(media_dest, post.url, post.date, filename_suffix=None)
        post_count += 1

        likes = post.likes
        time = post.date_local.strftime("%#I:%M %p") if platform.system() == 'Windows' else post.date_local.strftime("%-I:%M %p")
        date = post.date_local.date()
        unrem = ''
        for word in post.caption.split():
            if word[0] is '@':
                unrem += '{{USERNAME}} '
            else:
                unrem += word + ' '
        caption = scrubadub.clean(unrem)
        comments = ''
        for comment in post.get_comments():
            unrem = ''
            for word in comment[2].split():
                if word[0] is '@':
                    unrem += '{{USERNAME}} '
                else:
                    unrem += word + ' '
            comments += '"' + scrubadub.clean(unrem) + '", '

        entry = [date, time, media_dest, caption, likes, comments]
        posts_parsed.append(entry)
    except Exception as e:
        print("Error parsing IG post: " + type(e).__name__ + ": {}".format(e))
        continue

print('Scrubbing {0}\'s media...'.format(user_name), flush=True)
for filename in os.listdir(media_root):
    try:
        if any(filename.endswith(end) for end in supported_types):
            cv2.imwrite(os.path.join(media_root, filename), blurFaces(os.path.join(media_root, filename)))
    except Exception as e:
        print("Error scrubbing IG media: " + type(e).__name__ + ": {}".format(e))
        continue
genCSV(igu, 'posts.csv', posts_parsed)
