import io
import os
import json
from dotenv import load_dotenv
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
import pandas as pd
import requests
import ftplib
import numpy as np

load_dotenv()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
CREDENTIALS = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])
SERVICE_CREDENTIALS = ServiceAccountCredentials.from_json_keyfile_dict(CREDENTIALS, SCOPES)

def fetch_google_sheet_events():
    db = None
    try:
        service = build("sheets", "v4", credentials=SERVICE_CREDENTIALS)
        sheet = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=os.environ["EVENTS_SPREADSHEET_ID"], range="Sheet1")
            .execute()
        )
        column_names = sheet['values'][0]
        data = sheet['values'][1:]
        db = pd.DataFrame(data=data, columns=column_names)
        db.replace("", np.nan, inplace=True)
    except Exception as e:
        print(e)
    finally:
        return db

def fetch_hostinger_events():
    db = None
    response = requests.get("https://psychedelicqueenartistry.com/events.json")

    if response.status_code == 200:
        hostinger_json = response.json()
        db = pd.DataFrame.from_records(hostinger_json)
    elif response.status_code == 404:
        return db
    else:
        raise Exception(f'{response.status_code}: {response.reason}')

def pipeline_remove_events(events_db, hostinger_db):
    if hostinger_db == None:
        return events_db
    else:
        return hostinger_db[hostinger_db[["Title", "Start Date"]].isin(events_db[["Title", "Start Date"]])]

def pipeline_add_events(hostinger_db, events_db):
    events_to_add = events_db[~events_db[["Title", "Start Date"]].isin(hostinger_db[["Title", "Start Date"]])]
    result = pd.concat([hostinger_db, events_to_add], ignore_index=True)
    result.dropna(inplace=True)
    return result

def pipeline_upload_event_data_to_hostinger(events_db):
    event_data_buffer = io.BytesIO()
    events_db.to_json(event_data_buffer, orient="records")
    event_data_buffer.seek(0)

    try:
        ftp = ftplib.FTP()
        ftp.connect(os.environ["HOSTINGER_FTP_HOST"], int(os.environ["HOSTINGER_FTP_PORT"]))
        ftp.login(os.environ["HOSTINGER_FTP_USERNAME"], os.environ["HOSTINGER_FTP_PASSWORD"])

        ftp.storbinary("STOR domains/psychedelicqueenartistry.com/public_html/events.json", event_data_buffer)
        print("Event Data Uploaded!")
        ftp.quit()
    except Exception as e:
        print(f'Error: {e}')


#PIPELINE

events_db = fetch_google_sheet_events() 
hostinger_db = fetch_hostinger_events()

(
    events_db
    .pipe(pipeline_remove_events, hostinger_db)
    .pipe(pipeline_add_events, events_db)
    .pipe(pipeline_upload_event_data_to_hostinger)
)