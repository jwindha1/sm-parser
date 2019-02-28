import zipfile
import glob
import os
import os.path
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

supported_types = ['.bmp', '.jpeg', '.jpg', '.jpe', '.png', '.tiff', '.tif']

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

# ID extracted datasets
unzips = os.listdir(temp_out)
fb_regex = re.compile(r'.*_[fF]acebook$')
facebook_unzips = list(filter(fb_regex.search, unzips))

rem_comments = []

# Parse extracted Facebook datasets
print('Unzipping complete!', flush=True)
for fbu in facebook_unzips:
    # Get display name
    profile_path = os.path.join(temp_out, fbu, 'profile_information', 'profile_information.json')

    display_name = fbu
    if os.path.isfile(profile_path):
        profile_json = open(profile_path).read()
        display_name = json.loads(profile_json)['profile']['name']['full_name']
    else:
        print('NO PROFILE DEETS')

    print('Parsing {0}\'s friends...'.format(display_name), flush=True)
    # Parse friends
    friends_parsed = [['Total Friends', 'Removed Friends']]
    friends_path = os.path.join(temp_out, fbu, 'friends', 'friends.json')
    removed_path = os.path.join(temp_out, fbu, 'friends', 'removed_friends.json')
    if os.path.isfile(friends_path):
        friends_json = open(friends_path).read()
        num_friends = len(json.loads(friends_json)['friends'])
        if os.path.isfile(removed_path):
            removed_json = open(removed_path).read()
            removed_friends = json.loads(removed_json)['deleted_friends']
            num_enemies = 0
            for enemy in removed_friends:
                if datetime.fromtimestamp(enemy['timestamp']) < datetime.now()-timedelta(days=183):
                    continue
                num_enemies += 1
            friends_parsed.append([num_friends, num_enemies])
        else:
            friends_parsed.append([num_friends, 0])
        
        genCSV(fbu, 'friends.csv', friends_parsed)

    # Parse reactions
    print('Parsing {0}\'s reactions...'.format(display_name), flush=True)
    reactions_path = os.path.join(temp_out, fbu, 'likes_and_reactions', 'posts_and_comments.json')
    if os.path.isfile(reactions_path):
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
    found_posts = 0
    posts_parsed = [['Date', 'Time', 'Location', 'Post', 'Caption', 'Friend Comments', 'Subject Comments']]
    media_root = os.path.join(outbox_path, fbu, 'media')
    pathlib.Path(media_root).mkdir(parents=True, exist_ok=True)
    posts_path = os.path.join(temp_out, fbu, 'posts', 'your_posts.json')
    if os.path.isfile(posts_path):
        found_posts += 1
        posts_json = open(posts_path).read()
        posts = json.loads(posts_json)['status_updates']
        location = 'Profile'
        media_id = 0
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
                    entry = [post_date, post_time, location, media_dest, caption.encode('latin1').decode('utf8'), friend_comments.encode('latin1').decode('utf8'), subject_comments.encode('latin1').decode('utf8')]
                    posts_parsed.append(entry)

    # Parse group posts
    print('Parsing {0}\'s group posts...'.format(display_name), flush=True)
    posts_path = os.path.join(temp_out, fbu, 'groups', 'your_posts_and_comments_in_groups.json')
    if os.path.isfile(posts_path):
        found_posts += 1
        posts_json = open(posts_path).read()
        posts = json.loads(posts_json)['group_posts']
        if 'activity_log_data' in posts:
            posts = posts['activity_log_data']
        post_counter = 1
        rem_comments = []
        for post in posts:
            print('Parsing {0} of {1} group posts...'.format(post_counter, len(posts)), end='\r', flush=True)
            post_counter += 1
            # Extract comment details
            if datetime.fromtimestamp(post['timestamp']) < datetime.now()-timedelta(days=183):
                continue
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
                    entry = [post_date, post_time, location, media_dest, caption.encode('latin1').decode('utf8'), friend_comments.encode('latin1').decode('utf8'), subject_comments.encode('latin1').decode('utf8')]
                    posts_parsed.append(entry)

    # Parse profile update posts
    print('Parsing {0}\'s profile updates...'.format(display_name), flush=True)
    posts_path = os.path.join(temp_out, fbu, 'profile_information', 'profile_update_history.json')
    if os.path.isfile(posts_path):
        found_posts += 1
        posts_json = open(posts_path).read()
        posts = json.loads(posts_json)['profile_updates']
        post_counter = 1
        rem_comments = []
        for post in posts:
            print('Parsing {0} of {1} updates...'.format(post_counter, len(posts)), end='\r', flush=True)
            post_counter += 1
            # Extract comment details
            if datetime.fromtimestamp(post['timestamp']) < datetime.now()-timedelta(days=183):
                continue
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
                    entry = [post_date, post_time, location, media_dest, caption.encode('latin1').decode('utf8'), friend_comments.encode('latin1').decode('utf8'), subject_comments.encode('latin1').decode('utf8')]
                    posts_parsed.append(entry)

    if found_posts > 0:
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
        comments_parsed.append([comment_date, comment_time, comment_author, comment_text.encode('latin1').decode('utf8'), '', comment_attachment])

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

        comments_parsed.append([timeline_post_date, timeline_post_time, 'Friend', comment_text.encode('latin1').decode('utf8'), attachment])

    genCSV(fbu, 'comments.csv', comments_parsed)

# Parse Instagram files
print('Unzipping Instagram data dumps...', flush=True)
instagram_zips = glob.glob('./inbox/*_instagram.zip')
igz_counter = 1
for igz in instagram_zips:
    print('Unzipping {0} of {1} archives...'.format(igz_counter, len(instagram_zips)), end='\r', flush=True)
    igz_counter += 1
    with zipfile.ZipFile(igz,"r") as zip_ref:
        zip_ref.extractall("./inbox/temp")

temp_out = os.path.join('inbox', 'temp')
outbox_path = os.path.join('outbox')

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
    user_name = json.loads(profile_json)['username']
    media_root = os.path.join(outbox_path, igu, 'media')
    pathlib.Path(media_root).mkdir(parents=True, exist_ok=True)

    # Parse comments
    print('Parsing {0}\'s comments...'.format(display_name), flush=True)
    comments_path = os.path.join(temp_out, igu, 'comments.json')
    comments_json = open(comments_path, encoding='utf8').read()
    comments = json.loads(comments_json)
    comments_parsed = [['Date', 'Time', 'Subject\'s Photo', 'Friend\'s Photo']]
    for comment_sections in comments:
        for comment in comments[comment_sections]:
            timestamp = datetime.strptime(comment[0], '%Y-%m-%dT%H:%M:%S')
            if timestamp < datetime.now()-timedelta(days=183):
                continue
            post_date = timestamp.date()
            post_time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
            content = scrubadub.clean(comment[1])
            unrem = ''
            for word in content.split():
                if word[0] is '@':
                    unrem += '{{USERNAME}} '
                else:
                    unrem += word + ' '
            content = unrem
            author = comment[2]
            subject_comment = ''
            friend_comment = ''
            if (display_name in author):
                subject_comment = content
            else:
                friend_comment = content
            comments_parsed.append([post_date, post_time, subject_comment, friend_comment])

    genCSV(igu, 'comments.csv', comments_parsed)

    # Pull Instagram data from web
    posts_parsed = [['Date', 'Time', 'Media', 'Caption', 'Likes', 'Comments']]
    L = instaloader.Instaloader()
    L.interactive_login(user_name)
    profile = instaloader.Profile.from_username(L.context, user_name)
    posts = profile.get_posts()

    follow_parsed = [
        ['Followers', 'Followees'],
        [profile.followers, profile.followees]
        ]

    genCSV(igu, 'following.csv', follow_parsed)

    SINCE = datetime.today()
    UNTIL = SINCE - timedelta(days=183)
    post_count = 0
    print('Parsing {0}\'s media...'.format(user_name), flush=True)
    for post in takewhile(lambda p: p.date > UNTIL, dropwhile(lambda p: p.date > SINCE, posts)):
        media_dest = os.path.join(media_root, str(post_count))
        L.download_pic(media_dest, post.url, post.date, filename_suffix=None)
        post_count += 1

        likes = post.likes
        time = post.date_local.strftime("%#I:%M %p") if platform.system() == 'Windows' else post.date_local.strftime("%-I:%M %p")
        date = post.date_local.date()
        caption = post.caption
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

    print('Scrubbing {0}\'s media...'.format(user_name), flush=True)
    for filename in os.listdir(media_root):
        if any(filename.endswith(end) for end in supported_types):
            cv2.imwrite(os.path.join(media_root, filename), blurFaces(os.path.join(media_root, filename)))

    genCSV(igu, 'posts.csv', posts_parsed)
