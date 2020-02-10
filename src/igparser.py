import zipfile
import glob
import os
import scrubadub
import nltk
import re
import cv2
import sys

# in: None; out: None
def init():
    if not os.path.isdir('./inbox/temp'): os.mkdir('./inbox/temp')
    if not os.path.isdir('./outbox'): os.mkdir('./outbox')
    nltk.download('punkt')

# globals
init()
temp_path = os.path.join('inbox', 'temp')
outbox_path = os.path.join('outbox')
offline = len(sys.argv) == 2 and sys.argv[1] == 'offline'

# in: None; out: None
def unzip():
    print("unzipping")
    zips = glob.glob("./inbox/*.zip")
    for zip in zips:
        with zipfile.ZipFile(z, "r") as zip_ref:
            name = zip_ref.filename
            assert(name[:8] == "./inbox/" and name[-4:] == ".zip")
            name = name[8:-4]
            dest_path = os.path.join(temp_path, name)
            zip_ref.extractall(dest_path)

def ask_date():
    month_match = re.compile(r"^(\d|\d{2})$")
    months_back = input("How many months back? Enter a 1 or 2 digit number, then press enter: ").strip()
    while month_match.match(months_back) is None:
        months_back = input("Please enter a valid 1 or 2 digit number, then press enter: ").strip()

    date_match = re.compile(r"(^\d{4}-([0]\d|1[0-2])-([0-2]\d|3[01])$|^today$)")
    date_string = input("Parse within {0} month(s) of what date? \"today\" or YYYY-MM-DD, then press enter: ".format(months_back)).strip()
    while date_match.match(date_string) is None:
        date_string = input("Please enter in the proper format (\"today\" or YYYY-MM-DD), then press enter: ").strip()
    timestamp = datetime.today()
    if date_string != "today":
        yr_mo_day = [int(x) for x in date_string.split("-")]
        timestamp = datetime(yr_mo_day[0], yr_mo_day[1], yr_mo_day[2])
    if datetime.today() < timestamp:
        print("Error: date entered is in the future. Let's try again.")
        months_back, timestamp = ask_date()
    return int(months_back), timestamp

def out_of_range(curr, months_back, last_date):
    return (last_date-timedelta(days=months_back*30.4375) >= curr or curr > last_date)

def blur_faces(image_path):
    print("blurring faces")
    faces = face_recognition.face_locations(cv2.imread(image_path))
    for (top, right, bottom, left) in faces:
        face_image = img[top:bottom, left:right]
        face_image = cv2.GaussianBlur(face_image, (99, 99), 30)
        img[top:bottom, left:right] = face_image
    return img

def gen_csv(parsed_path, filename, content):
    print("generating csv")
    csv_out = os.path.join(parsed_path, "{0}.csv".format(filename))
    os.makedirs(os.path.dirname(csv_out), exist_ok=True)
    with open(csv_out, "w+", encoding='utf-8') as csv_file:
        csv_writer = csv.writer(csv_file, quoting=csv.QUOTE_ALL, lineterminator = '\n')
        for entry in content: csv_writer.writerow(entry)

# in: unzip_path for particular account, filename string like "comments"
# out: list of data
def get_json(unzip_path, filename):
    json_path = os.path.join(unzip_path, "{0}.json".format(filename))
    return json.loads(open(json_path).read())

# in: string
# out: timestamp, time, date
def get_timestamp(when):
    timestamp = datetime.strptime(when, '%Y-%m-%dT%H:%M:%S')
    date = timestamp.date()
    time = timestamp.strftime("%#I:%M %p") if platform.system() == 'Windows' else timestamp.strftime("%-I:%M %p")
    return timestamp, date, time

# in: text; out: cleaned text
def clean_text(text):
    text = scrubadub.clean(text)
    return re.sub(r'@\S*', "{{USERNAME}}", text).encode('latin1', 'ignore').decode('utf8')

def parse_profile_metadata(unzip_path):
    print("parsing profile metadata")
    data = get_json(unzip_path, "profile")
    username = data['username']
    name = data['name'] if 'name' in data else ''
    return username, name

def parse_comments(unzip_path, parsed_path, months_back, last_date, username):
    print("parsing comments")
    data = get_json(unzip_path, "comments")
    users_comments_on_their_post = [["Date", "Time", "Content"]]
    users_comments_on_other_post = [["Date", "Time", "Content"]]
    for section in data:
        for comment in section:
            timestamp, date, time = get_timestamp(comment[0])
            if out_of_range(timestamp, months_back, last_date): continue
            content = clean_text(comment[1])
            row = [date, time, content]
            author = comment[2]
            if author == username: users_comments_on_their_post.append(row)
            else: users_comments_on_other_post.append(row)
    gen_csv(parsed_path, "users_comments_on_their_post", users_comments_on_their_post)
    gen_csv(parsed_path, "users_comments_on_other_post", users_comments_on_other_post)

def parse_follow(unzip_path, parsed_path):
    print("parsing follow")
    data = get_json(unzip_path, "connections")
    follow_parsed = [['Followers', 'Followees'],
        [len(data['followers']), len(data['following'])]]
    gen_csv(parsed_path, "follow", follow_parsed)

def parse_posts_offline(unzip_path, months_back, last_date):
    print("parsing offline posts")
    media_path = os.path.join(unzip_path, "media")
    media_parsed = [["Date", "Time", "Path", "Caption", "Likes", "Comments"]]
    timestamps_for_media_parsed = []
    post_counter = 0

    # out: true if success
    def add_media(media, tracker, timestamp, post_num, num_pics):
        filename, ext_type = os.path.splitext(media)
        if ext_type not in ['.bmp', '.jpeg', '.jpg', '.jpe', '.png', '.tiff', '.tif']:
            return false
        media_src = os.path.join(unzip_path, media["path"])
        media_dest = os.path.join(media_path, str(post_num), "{0}.{1}".format(chr(97-1+num_pics), ext_type))
        cv2.imwrite(media_dest, blur_faces(media_src))
        tracker[timestamp] = (post_num, num_pics + 1)
        return true

    def parse_type(post_lst):
        tracker = {}  # timestamp -> (post_num, num_pics)
        for media in post_lst:
            timestamp, date, time = media["taken_at"]
            if out_of_range(timestamp, months_back, last_date): continue
            if timestamp in tracker:
                post_num, num_pics = tracker[timestamp]
                add_media(media, tracker, timestamp, post_num, num_pics)
            else:
                post_num = post_counter
                num_pics = 0
                if add_media(media, tracker, timestamp, post_num, num_pics):
                    media_parsed.append([date, time, os.path.join(media_path, str(post_num)), media["caption"], "", ""])
                    timestamps_for_media_parsed.append(timestamp)
                    post_counter += 1

    data = get_json(unzip_path, "media")
    parse_type(data["photos"].extend(data["videos"]))
    parse_type(data["stories"])
    parse_type(data["profile"])
    return media_parsed, timestamps_for_media_parsed

def parse_posts_online(media_parsed, timestamps_for_media_parsed, username):
    print("parsing online posts")
    L = instaloader.Instaloader()
    try:
        L.interactive_login(username)
    except Exception as e:
        print("Failed login with username from download: " + type(e).__name__ + ": {}".format(e))
        username = input('Please enter subject\'s Instagram username: ')
        L.interactive_login(username)
    profile = instaloader.Profile.from_username(L.context, username)
    posts = profile.get_posts()
    for post in posts:
        timestamp = post.date_local
        if timestamp not in timestamps_for_media_parsed: continue
        row = media_parsed[timestamps_for_media_parsed.index(timestamp)]
        row[4] = post.likes
        row[5] = "; ".join([clean_text(comment) for comment in post.get_comments()])
        media_parsed[timestamps_for_media_parsed.index(timestamp)] = row
    return media_parsed

def parse_posts(unzip_path, parsed_path, months_back, last_date, username):
    media_parsed, timestamps_for_media_parsed = parse_posts_offline(unzip_path, months_back, last_date)
    if not offline:
        media_parsed = parse_posts_online(media_parsed, timestamps_for_media_parsed, username)
    gen_csv(parsed_path, "posts", media_parsed)

def parse_all_accounts():
    unzip()
    for unzip in os.listdir(temp_path):
        unzip_path = os.path.join(temp_path, unzip)
        username, name = parse_profile_metadata(unzip_path)
        parsed_path = os.path.join(outbox_path, username)
        months_back, last_date = ask_date()
        parse_comments(unzip_path, parsed_path, months_back, last_date, username)
        parse_follow(unzip_path, parsed_path)
        parse_posts(unzip_path, parsed_path, months_back, last_date, username)
    print("cleaning up")
    shutil.rmtree(temp_path)

parse_all_accounts()
