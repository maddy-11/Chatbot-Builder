import os
import io
import re
import requests
import csv
import gspread
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from bs4 import BeautifulSoup
from oauth2client.service_account import ServiceAccountCredentials
from django.conf import settings

BASE_DIR = settings.BASE_DIR
google_credentials = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'credentials.json')
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, 'private', google_credentials)

def is_google_drive_folder_url(url):
    drive_folder_pattern = re.compile(r'(https?://)?(www\.)?(drive\.google\.com/drive/folders/[\w-]+|docs\.google\.com/document/d/[\w-]+)')
    return bool(re.match(drive_folder_pattern, url))

def is_youtube_url(url):
    youtube_pattern = re.compile(r'(https?://)?(www\.)?(youtube\.com/watch\?v=|youtu\.be/)[\w-]+(&\S+)?')
    return bool(re.match(youtube_pattern, url))

def is_google_sheet_url(url):
    google_sheet_pattern = re.compile(r'(https?://)?(www\.)?(docs\.google\.com/spreadsheets/d/)([\w-]+)/edit.*')
    return bool(re.match(google_sheet_pattern, url))

def get_youtube_video_id(url):
    yt = YouTube(url)
    return yt.video_id

def get_subtitles(video_id, chatbot_dir):
    try:
        os.makedirs(chatbot_dir, exist_ok=True)
        file_path = os.path.join(chatbot_dir, f'{video_id}.txt')
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None
        for transcript_item in transcript_list:
            if transcript_item.is_translatable:
                transcript = transcript_item.translate('en')
                break
        if transcript is None:
            transcript = transcript_list.find_transcript(['en'])
        subtitles = transcript.fetch()
        with open(file_path, 'w') as f:
            for item in subtitles:
                text = item['text']
                f.write(f"{text}\n")
        return file_path
    except Exception as e:
        return str(e)

def read_google_sheet(url, chatbot_dir):
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
    client = gspread.authorize(credentials)
    spreadsheet = client.open_by_url(url)
    spreadsheet_name = spreadsheet.title
    worksheet = spreadsheet.get_worksheet(0)
    values = worksheet.get_all_values()
    os.makedirs(chatbot_dir, exist_ok=True)
    file_path = os.path.join(chatbot_dir, f'{spreadsheet_name}.csv')
    with open(file_path, 'w', newline='') as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerows(values)
    add_empty_row_to_csv(file_path)
    return file_path

def download_files_from_drive(url, chatbot_dir):
    print('in google drive')
    os.makedirs(chatbot_dir, exist_ok=True)
    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    service = build('drive', 'v3', credentials=credentials)
    file_id = None
    folder_id = None

    if 'drive.google.com/drive/folders/' in url:
        folder_id = re.findall(r'/folders/([a-zA-Z0-9_-]+)', url)[0]
    elif 'drive.google.com/file/d/' in url or 'docs.google.com/document/d/' in url:
        file_id = re.findall(r'/d/([a-zA-Z0-9_-]+)', url)[0]
    else:
        raise ValueError('Invalid Google Drive URL provided.')

    file_paths = []
    if folder_id:
        results = service.files().list(q=f"'{folder_id}' in parents",
                                       pageSize=1000, fields="files(id, name, mimeType)").execute()
        items = results.get('files', [])
        for item in items:
            file_path = os.path.join(chatbot_dir, item['name'])
            file_path_with_extension, download_status = download_file(service, item['id'], file_path, item['mimeType'])
            if download_status:
                file_paths.append((item['name'], file_path_with_extension))
    elif file_id:
        file = service.files().get(fileId=file_id, fields='name, mimeType').execute()
        file_path = os.path.join(chatbot_dir, file['name'])
        file_path_with_extension, download_status = download_file(service, file_id, file_path, file['mimeType'])
        if download_status:
            file_paths.append((file_path_with_extension, file['name']))
    
    return file_paths

def download_file(service, file_id, file_path, mime_type):
    try:
        request = service.files().get_media(fileId=file_id)
        with io.FileIO(file_path, 'wb') as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
                print(f'Download {int(status.progress() * 100)}%.')
        return file_path, True
    except Exception as e:
        if 'fileNotDownloadable' in str(e):
            export_mime_type = None
            extension = ""
            if mime_type == 'application/vnd.google-apps.document':
                export_mime_type = 'application/pdf'
                extension = '.pdf'
            elif mime_type == 'application/vnd.google-apps.spreadsheet':
                export_mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                extension = '.xlsx'
            elif mime_type == 'application/vnd.google-apps.presentation':
                export_mime_type = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                extension = '.pptx'
            elif mime_type == 'text/plain':
                export_mime_type = 'text/plain'
                extension = '.txt'
            elif mime_type == 'text/csv':
                export_mime_type = 'text/csv'
                extension = '.csv'
            elif mime_type == 'application/pdf':
                export_mime_type = 'application/pdf'
                extension = '.pdf'
            else:
                raise ValueError('Unsupported Google Workspace file type.')

            file_path_with_extension = file_path + extension
            request = service.files().export_media(fileId=file_id, mimeType=export_mime_type)
            with io.FileIO(file_path_with_extension, 'wb') as fh:
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    print(f'Download {int(status.progress() * 100)}%.')
            if os.path.exists(file_path) and os.path.getsize(file_path) == 0:
                os.remove(file_path)  # Remove the empty file without extension
            return file_path_with_extension, True
        else:
            raise e
                       
def scrape_and_save_urls(url, chatbot_dir):
    os.makedirs(chatbot_dir, exist_ok=True)
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        content = soup.get_text()
        content_lines = content.splitlines()
        cleaned_lines = [line for line in content_lines if line.strip()]
        cleaned_content = '\n'.join(cleaned_lines)
        file_name = f"{url.replace('https://', '').replace('/', '_')}.txt"
        file_path = os.path.join(chatbot_dir, file_name)
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(cleaned_content)
        return file_path
    except requests.RequestException as e:
        print(f"Failed to retrieve {url}: {e}")
        return None