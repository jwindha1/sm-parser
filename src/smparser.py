import zipfile
import glob
import os
import re
import sys

# Parse Facebook files
#facebook_zips = glob.glob('./inbox/*_facebook.zip')
#for fbz in facebook_zips:
#    with zipfile.ZipFile(fbz,"r") as zip_ref:
#        zip_ref.extractall("./inbox/temp")

if len(sys.argv) != 2:
    sys.exit("ERROR: Path to zips required")
unzips = os.listdir('./src/inbox/temp')
fb_regex = re.compile(r'.*_facebook$')
facebook_unzips = list(filter(fb_regex.search, unzips))
print(facebook_unzips)
