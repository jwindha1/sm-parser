import zipfile
import glob

# Parse Facebook files
facebook_zips = glob.glob('./inbox/*_facebook.zip')
for fbz in facebook_zips:
    with zipfile.ZipFile(fbz,"r") as zip_ref:
        zip_ref.extractall("./inbox/temp")