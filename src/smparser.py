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

def genCSV(folder, filename, content):
    # Generate CSVs from data
    csv_out = os.path.join(outbox_path, folder, filename)
    os.makedirs(os.path.dirname(csv_out), exist_ok=True)
    with open(csv_out, "w+", encoding='utf-8') as csv_file:
        csv_writer = csv.writer(csv_file, quoting=csv.QUOTE_ALL, lineterminator = '\n')
        for entry in content:
            csv_writer.writerow(entry)

'''# Parse Facebook files
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
fb_regex = re.compile(r'.*_[fF]acebook$')
facebook_unzips = list(filter(fb_regex.search, unzips))

# Parse extracted Facebook datasets
print('Unzipping complete!', flush=True)
for fbu in facebook_unzips:
    # Get display name
    profile_path = os.path.join(temp_out, fbu, 'profile_information', 'profile_information.json')
    profile_json = open(profile_path).read()
    display_name = json.loads(profile_json)['profile']['name']['full_name']

    print('Parsing {0}\'s friends...'.format(display_name), flush=True)
    # Parse friends
    friends_path = os.path.join(temp_out, fbu, 'friends', 'friends.json')
    removed_path = os.path.join(temp_out, fbu, 'friends', 'removed_friends.json')
    friends_json = open(friends_path).read()
    removed_json = open(removed_path).read()
    num_friends = len(json.loads(friends_json)['friends'])
    removed_friends = json.loads(removed_json)['deleted_friends']
    num_enemies = 0
    friends_parsed = [['Total Friends', 'Removed Friends']]
    for enemy in removed_friends:
        if datetime.fromtimestamp(enemy['timestamp']) < datetime.now()-timedelta(days=183):
            continue
        num_enemies += 1
    friends_parsed.append([num_friends, num_enemies])

    genCSV(fbu, 'friends.csv', friends_parsed)

    # Parse reactions
    print('Parsing {0}\'s reactions...'.format(display_name), flush=True)
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

    genCSV(fbu, 'reactions.csv', reactions_parsed)

    # Parse posts
    print('Parsing {0}\'s posts...'.format(display_name), flush=True)
    media_root = os.path.join(outbox_path, fbu, 'media')
    pathlib.Path(media_root).mkdir(parents=True, exist_ok=True)
    posts_path = os.path.join(temp_out, fbu, 'posts', 'your_posts.json')
    posts_json = open(posts_path).read()
    posts = json.loads(posts_json)['status_updates']
    posts_parsed = [['Date', 'Time', 'Location', 'Post', 'Caption', 'Friend Comments', 'Subject Comments']]
    location = 'Profile'
    media_id = 0
    supported_types = ['.bmp', '.jpeg', '.jpg', '.jpe', '.png', '.tiff', '.tif']
    post_counter = 1
    rem_comments = []
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
        elif 'title' in post:
            caption = scrubadub.clean(post['title'])

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
                if 'description' in content:
                        caption = scrubadub.clean(content['description'])
                friend_comments = ''
                subject_comments = ''
                if 'comments' in content:
                    for comment in content['comments']:
                        if (display_name in comment['author']):
                            subject_comments += '"' + scrubadub.clean(comment['comment']) + '", '
                            rem_comments.append(comment['comment'])
                        else:
                            friend_comments += '"' + scrubadub.clean(comment['comment']) + '", '
                scrubadub.clean(caption)
                media_src = os.path.join(temp_out, fbu, media)
                filename, file_extension = os.path.splitext(media)
                media_dest = 'N/A'
                if file_extension in supported_types:
                    media_id += 1
                    media_dest = os.path.join(media_root, '{0}{1}'.format(media_id, file_extension))
                    cv2.imwrite(media_dest, blurFaces(media_src))
                entry = [post_date, post_time, location, media_dest, caption, friend_comments, subject_comments]
                posts_parsed.append(entry)

    # Parse group posts
    print('Parsing {0}\'s group posts...'.format(display_name), flush=True)
    posts_path = os.path.join(temp_out, fbu, 'groups', 'your_posts_and_comments_in_groups.json')
    posts_json = open(posts_path).read()
    posts = json.loads(posts_json)['group_posts']
    post_counter = 1
    rem_comments = []
    for post in posts:
        print('Parsing {0} of {1} group posts...'.format(post_counter, len(posts)), end='\r', flush=True)
        post_counter += 1
        # Extract comment details
        if datetime.fromtimestamp(post['timestamp']) < datetime.now()-timedelta(days=183):
            pass
        timestamp = datetime.fromtimestamp(post['timestamp'], timezone.utc)
        post_date = timestamp.date()
        post_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")

        subject_comments = ''
        location = 'Group'
        caption = ''
        media_dest = 'N/A'
        if 'data' in post:
            if 'post' in post['data'][0]:
                caption = scrubadub.clean(post['data'][0]['post'])
            else:
                caption = scrubadub.clean(post['title'])
            if 'comment' in post['data'][0]:
                subject_comments += '"' + scrubadub.clean(post['data'][0]['comment']['comment']) + '", '
                location = post['data'][0]['comment']['group']
            elif 'title' in post:
                location = post['title'].split(' in ',1)[1]
        else:
            continue

        if 'attachments' not in post:
            entry = [post_date, post_time, location, media_dest, caption, '', subject_comments]
            posts_parsed.append(entry)
        else:
            attachments = post['attachments'][0]['data']
            for attachment in attachments:
                if 'media' in attachment:
                    content = attachment['media']
                    media = content['uri']
                elif 'external_context' in attachment:
                    content = attachment['external_context']
                    caption += ': ' + content['url']
                    media = ''
                if 'description' in content:
                        caption = scrubadub.clean(content['description'])
                friend_comments = ''
                subject_comments = ''
                if 'comments' in content:
                    for comment in content['comments']:
                        if (display_name in comment['author']):
                            subject_comments += '"' + scrubadub.clean(comment['comment']) + '", '
                            rem_comments.append(comment['comment'])
                        else:
                            friend_comments += '"' + scrubadub.clean(comment['comment']) + '", '

                scrubadub.clean(caption)
                media_src = os.path.join(temp_out, fbu, media)
                filename, file_extension = os.path.splitext(media)
                if file_extension in supported_types:
                    media_id += 1
                    media_dest = os.path.join(media_root, '{0}{1}'.format(media_id, file_extension))
                    cv2.imwrite(media_dest, blurFaces(media_src))
                entry = [post_date, post_time, location, media_dest, caption, friend_comments, subject_comments]
                posts_parsed.append(entry)

    # Parse profile update posts
    print('Parsing {0}\'s profile updates...'.format(display_name), flush=True)
    posts_path = os.path.join(temp_out, fbu, 'profile_information', 'profile_update_history.json')
    posts_json = open(posts_path).read()
    posts = json.loads(posts_json)['profile_updates']
    post_counter = 1
    rem_comments = []
    for post in posts:
        print('Parsing {0} of {1} updates...'.format(post_counter, len(posts)), end='\r', flush=True)
        post_counter += 1
        # Extract comment details
        if datetime.fromtimestamp(post['timestamp']) < datetime.now()-timedelta(days=183):
            pass
        timestamp = datetime.fromtimestamp(post['timestamp'], timezone.utc)
        post_date = timestamp.date()
        post_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
        if 'title' in post:
            caption = post['title']
        else:
            continue

        location = 'Profile'
        media_dest = 'N/A'
        if 'attachments' not in post:
            entry = [post_date, post_time, location, media_dest, caption, '', '']
            posts_parsed.append(entry)
        else:
            attachments = post['attachments'][0]['data']
            for attachment in attachments:
                if 'media' in attachment:
                    content = attachment['media']
                    media = content['uri']
                    friend_comments = ''
                    subject_comments = ''
                    if 'comments' in content:
                        for comment in content['comments']:
                            if (display_name in comment['author']):
                                subject_comments += '"' + scrubadub.clean(comment['comment']) + '", '
                                rem_comments.append(comment['comment'])
                            else:
                                friend_comments += '"' + scrubadub.clean(comment['comment']) + '", '

                scrubadub.clean(caption)
                media_src = os.path.join(temp_out, fbu, media)
                filename, file_extension = os.path.splitext(media)
                if file_extension in supported_types:
                    media_id += 1
                    media_dest = os.path.join(media_root, '{0}{1}'.format(media_id, file_extension))
                    cv2.imwrite(media_dest, blurFaces(media_src))
                entry = [post_date, post_time, location, media_dest, caption, friend_comments, subject_comments]
                posts_parsed.append(entry)

    genCSV(fbu, 'posts.csv', posts_parsed)

    # Parse comments and likes
    print('Parsing {0}\'s comments and likes...'.format(display_name), flush=True)
    comments_path = os.path.join(temp_out, fbu, 'comments', 'comments.json')
    comments_json = open(comments_path).read()
    comments = json.loads(comments_json)['comments']
    timeline_path = os.path.join(temp_out, fbu, 'posts', 'other_people\'s_posts_to_your_timeline.json')
    timeline_json = open(timeline_path).read()
    timeline = json.loads(timeline_json)['wall_posts_sent_to_you']
    comments_parsed = [['Date', 'Time', 'Author', 'Subject Comment', 'Friend Timeline Comment', 'URL']]
    for comment in comments:
        if datetime.fromtimestamp(comment['timestamp']) < datetime.now()-timedelta(days=183):
            continue
        # Extract comment details
        timestamp = datetime.fromtimestamp(comment['timestamp'], timezone.utc)
        comment_date = timestamp.date()
        comment_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
        comment_attachment = comment['attachments'][0]['data'][0]['external_context']['url'] if 'attachments' in comment else ''
        if 'comment' in comment['data'][0]['comment']:
            if comment['data'][0]['comment']['comment'] not in rem_comments:
                comment_text = scrubadub.clean(comment['data'][0]['comment']['comment'])
            else:
                continue
        else:
            comment_text = ''
        comment_author = comment['data'][0]['comment']['author']
        comments_parsed.append([comment_date, comment_time, comment_author, comment_text, '', comment_attachment])

    for timeline_post in timeline:
        if datetime.fromtimestamp(timeline_post['timestamp']) < datetime.now()-timedelta(days=183):
            continue
        # Extract comment details
        timestamp = datetime.fromtimestamp(timeline_post['timestamp'], timezone.utc)
        timeline_post_date = timestamp.date()
        timeline_post_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")

        if 'data' not in timeline_post:
            continue

        attachment = ''
        if 'attachments' in timeline_post:
            if 'media' in timeline_post['attachments'][0]['data'][0]:
                attachment = timeline_post['attachments'][0]['data'][0]['media']['uri']
            elif 'external_context' in timeline_post['attachments'][0]['data'][0]:
                attachment = timeline_post['attachments'][0]['data'][0]['external_context']['url']

        if 'post' not in timeline_post['data'][0]:
            if attachment is not '':
                comment_text = attachment
            else:
                continue
        else:
            comment_text = timeline_post['data'][0]['post']

        comments_parsed.append([timeline_post_date, timeline_post_time, 'Friend', comment_text, attachment])

    genCSV(fbu, 'comments.csv', comments_parsed)

# Parse Instagram files
print('Unzipping Instagram data dumps...', flush=True)
instagram_zips = glob.glob('./inbox/*_instagram.zip')
fbz_counter = 1
for fbz in instagram_zips:
    print('Unzipping {0} of {1} archives...'.format(fbz_counter, len(instagram_zips)), end='\r', flush=True)
    fbz_counter += 1
    with zipfile.ZipFile(fbz,"r") as zip_ref:
        zip_ref.extractall("./inbox/temp")'''

temp_out = os.path.join('inbox', 'temp')
outbox_path = os.path.join('outbox')

if len(sys.argv) != 2:
    sys.exit("ERROR: Path to zips required")

# ID extracted datasets
unzips = os.listdir(temp_out)
ig_regex = re.compile(r'.*_[iI]nstagram$')
instagram_unzips = list(filter(ig_regex.search, unzips))

# Parse extracted Instagram datasets
print('\nUnzipping complete!', flush=True)
for igu in instagram_unzips:
    # Get display name
    profile_path = os.path.join(temp_out, igu, 'profile.json')
    profile_json = open(profile_path).read()
    display_name = json.loads(profile_json)['name']

    # Parse comments
    print('Parsing {0}\'s comments...'.format(display_name), flush=True)
    comments_path = os.path.join(temp_out, igu, 'comments.json')
    comments_json = open(comments_path, encoding='utf8').read()
    comments = json.loads(comments_json)
    comments_parsed = [['Date', 'Time', 'Author', 'Subject Comment', 'Friend Comment']]
    for comment_sections in comments:
        for comment in comments[comment_sections]:
            timestamp = datetime.strptime(comment[0], '%Y-%m-%dT%H:%M:%S')
            if timestamp < datetime.now()-timedelta(days=183):
                pass#continue
            post_date = timestamp.date()
            post_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
            content = scrubadub.clean(comment[1])
            author = comment[2]
            subject_comment = ''
            friend_comment = ''
            if (display_name in author):
                subject_comment = content
            else:
                friend_comment = content
            comments_parsed.append([post_date, post_time, author, subject_comment, friend_comment])

    genCSV(igu, 'comments.csv', comments_parsed)

    f1=open('./testfile.txt', 'w+')

    print('Parsing {0}\'s likes...'.format(display_name), flush=True)
    likes_path = os.path.join(temp_out, igu, 'likes.json')
    likes_json = open(likes_path, encoding='utf8').read()
    likes = json.loads(likes_json)

    print(json.dumps(likes, indent=4, sort_keys=True), file=f1)