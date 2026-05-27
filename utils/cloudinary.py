import os
import cloudinary
import cloudinary.uploader

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True,
)


def upload_user_photos(files, folder='private-dating'):
    urls = []
    for f in files:
        if not f or not f.filename:
            continue
        result = cloudinary.uploader.upload(f, folder=folder)
        urls.append(result.get('secure_url'))
    return urls
