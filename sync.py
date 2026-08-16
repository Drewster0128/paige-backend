import io
import os.path
import json
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import pdb
import requests
import ftplib
from PIL import Image
import numpy as np


load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly"
]
CREDENTIALS = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
SERVICE_CREDENTIALS = ServiceAccountCredentials.from_json_keyfile_dict(CREDENTIALS, SCOPES)

def fetch_google_sheet_dataframe():
    db = None
    try:
        service = build("sheets", "v4", credentials=SERVICE_CREDENTIALS)
        sheet = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=os.environ["SPREADSHEET_ID"], range='Sheet1')
            .execute()
        )
        column_names = sheet['values'][0][0:-1]
        data = sheet['values'][1:]
        db = pd.DataFrame(data=data, columns=column_names)
        db = (
            db
            .assign(id=lambda x : (
                x["Art Piece"]
                .str.replace(r'[^a-zA-Z0-9]', '', regex=True)
                .str.lower()
                )
            )
        )
        db = db.replace("", np.nan)
        db = db.dropna(subset=['Art Piece', 'Description', "Original Size", "Print Sizes", "Date Created", "Medium", "Availability"])
        return db
    except Exception as e:
        print(e)
        return db


def fetch_artwork_images_dataframe():
    db = None
    try:
        service = build("drive", "v3", credentials=SERVICE_CREDENTIALS)
        artwork_files = (
            service.files()
            .list(q=f"'{os.environ["ARTWORK_IMAGES_FOLDER_ID"]}' in parents")
            .execute()
        )
        db = pd.DataFrame.from_dict(artwork_files['files'])
        db = (
            db
            .rename(columns={"id": "driveId"})
            .assign(id=lambda x : (
                x['name']
                .apply(
                    lambda x : os.path.splitext(x)[0]
                )
                .str.replace(r'[^a-zA-Z0-9]', '', regex=True)
                .str.lower()
                )
            )
        )
        return db[["id", "driveId", "name"]]
    except Exception as e:
        print(e)
        return db


def fetch_hostinger_dataframe():
    db = None
    response = requests.get("https://psychedelicqueenartistry.com/pictures.json")

    if response.status_code == 200:
        hostinger_json = response.json()
        db = pd.DataFrame.from_records(hostinger_json)
    elif response.status_code == 404:
        return db
    else:
        raise Exception(f'{response.status_code}: {response.reason}')



def get_artwork_to_remove(google_data_frame, hostinger_data_frame):
    return hostinger_data_frame[~hostinger_data_frame["id"].isin(google_data_frame["id"])]

def get_artwork_to_add(google_data_frame, hostinger_data_frame):
    return google_data_frame[~google_data_frame["id"].isin(hostinger_data_frame["id"])]

def upload_artwork_to_hostinger(full_buffer, croped_buffer, name):
    try:
        ftp = ftplib.FTP()
        ftp.connect(os.environ["HOSTINGER_FTP_HOST"], int(os.environ["HOSTINGER_FTP_PORT"]))
        ftp.login(os.environ["HOSTINGER_FTP_USERNAME"], os.environ["HOSTINGER_FTP_PASSWORD"])

        ftp.storbinary(f"STOR domains/psychedelicqueenartistry.com/public_html/img/full/{name}", full_buffer)
        ftp.storbinary(f"STOR domains/psychedelicqueenartistry.com/public_html/img/4x3/{name}", croped_buffer)
        print(f"{name} uploaded!")
        
        ftp.quit()
    except Exception as e:
        print(f'Error: {e}')

def upload_meta_data_to_hostinger(artwork_dataframe):
    meta_data_buffer = io.BytesIO()
    db = artwork_dataframe[["Art Piece", "Description", "Price", "Original Size", "Print Sizes", "Date Created", "Medium", "Availability", "id"]]
    db.rename(columns={"id": "ID"}, inplace=True)
    db.to_json(meta_data_buffer, orient="records")
    meta_data_buffer.seek(0)

    try:
        ftp = ftplib.FTP()
        ftp.connect(os.environ["HOSTINGER_FTP_HOST"], int(os.environ["HOSTINGER_FTP_PORT"]))
        ftp.login(os.environ["HOSTINGER_FTP_USERNAME"], os.environ["HOSTINGER_FTP_PASSWORD"])

        ftp.storbinary(f"STOR domains/psychedelicqueenartistry.com/public_html/pictures.json", meta_data_buffer)
        print("Meta Data Uploaded!")
        ftp.quit()
    except Exception as e:
        print(f'Error: {e}')

def download_artwork_from_drive(artwork_drive_id):
    try:
        service = build("drive", "v3", credentials=SERVICE_CREDENTIALS)
        print(artwork_drive_id)
        request = (
            service.files()
            .get_media(fileId=artwork_drive_id)
        )
        binary_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(binary_buffer, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%")

        binary_buffer.seek(0)
        return binary_buffer
    except Exception as e:
        print(f'Error: {e}')

def transform_to_webp(artwork_buffer):
    webp_buffer = io.BytesIO()
    artwork_image = Image.open(artwork_buffer)
    artwork_image.save(webp_buffer, format="webp")
    webp_buffer.seek(0)

    return webp_buffer

def transform_to_4x3(artwork_buffer):
    webp_4x3_buffer = io.BytesIO()

    artwork_image_full = Image.open(artwork_buffer)

    width, height = artwork_image_full.size

    # Calculate target 4:3 dimensions
    target_width = width
    target_height = int(width * 3 / 4)

    if target_height > height:
        target_height = height
        target_width = int(height * 4 / 3)

    # Center crop coordinates
    left = (width - target_width) / 2
    upper = (height - target_height) / 2
    right = (width + target_width) / 2
    lower = (height + target_height) / 2

    artwork_image_4x3 = artwork_image_full.crop((left, upper, right, lower))
    artwork_image_4x3.save(webp_4x3_buffer, format="webp")

    webp_4x3_buffer.seek(0)
    return webp_4x3_buffer


def pipeline_download(artwork_dataframe):
    artwork_dataframe["original_buffer"] = artwork_dataframe['driveId'].apply(lambda driveId: download_artwork_from_drive(driveId))
    return artwork_dataframe

def pipeline_transform(artwork_dataframe):
    artwork_dataframe["full_webp_buffer"] = artwork_dataframe["original_buffer"].apply(lambda buffer: transform_to_webp(buffer))
    artwork_dataframe["4x3_webp_buffer"] = artwork_dataframe["original_buffer"].apply(lambda buffer: transform_to_4x3(buffer))
    return artwork_dataframe

def pipeline_upload(artwork_dataframe):
    artwork_dataframe.apply(lambda row: upload_artwork_to_hostinger(row["full_webp_buffer"], row["4x3_webp_buffer"], f"{row["id"]}.webp"), axis=1)


try:
    google_sheet_data_frame = fetch_google_sheet_dataframe()
    artwork_images_data_frame = fetch_artwork_images_dataframe()
    hostinger_data_frame = fetch_hostinger_dataframe()

    google_data_frame = google_sheet_data_frame.merge(artwork_images_data_frame, how="inner")

    # DOWNLOAD IMAGE FROM GOOGLE DRIVE
    # CONVERT TO WEBP
    # MAKE SEPERATE 4x3 VERSION
    # UPLOAD BOTH
    # UPDATE HOSTINGER JSON
    if hostinger_data_frame == None:
        (
            google_data_frame
            .pipe(pipeline_download)
            .pipe(pipeline_transform)
            .pipe(pipeline_upload)
        )
        upload_meta_data_to_hostinger(google_data_frame)
except Exception as e:
    print(e)


# STATUS: get_artwork_to_add and get_artwork_to_remove do not work because the ID syntax currently on the hostinger json does not match the id pattern on the google dataframe
# TO FIX ABOVE STATUS, I SHOULD CONSIDER WIPING THE FILE AND ALL CURRENT PHOTOS TO GIVE IT A CLEAN SLATE. THAT WILL REQUIRE A CHECK IF pictures.json exists on hostinger