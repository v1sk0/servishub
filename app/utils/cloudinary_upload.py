"""
Cloudinary upload utility for image uploads.

Handles logo and cover image uploads with validation.
"""
import os
import cloudinary
import cloudinary.uploader
from flask import current_app
from werkzeug.utils import secure_filename


# Allowed image extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# Max file size in bytes (5MB)
MAX_FILE_SIZE = 5 * 1024 * 1024


def init_cloudinary():
    """Initialize Cloudinary from environment variables."""
    cloudinary_url = os.getenv('CLOUDINARY_URL')
    if cloudinary_url:
        # CLOUDINARY_URL format: cloudinary://api_key:api_secret@cloud_name
        return True

    # Fallback to individual env vars
    cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME')
    api_key = os.getenv('CLOUDINARY_API_KEY')
    api_secret = os.getenv('CLOUDINARY_API_SECRET')

    if cloud_name and api_key and api_secret:
        cloudinary.config(
            cloud_name=cloud_name,
            api_key=api_key,
            api_secret=api_secret,
            secure=True
        )
        return True

    return False


def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def validate_file(file):
    """
    Validate uploaded file.

    Returns tuple (is_valid, error_message)
    """
    if not file:
        return False, 'Fajl nije prosleđen'

    if file.filename == '':
        return False, 'Fajl nije izabran'

    if not allowed_file(file.filename):
        return False, f'Dozvoljeni formati: {", ".join(ALLOWED_EXTENSIONS)}'

    # Check file size by reading content
    file.seek(0, 2)  # Seek to end
    size = file.tell()
    file.seek(0)  # Reset to beginning

    if size > MAX_FILE_SIZE:
        return False, f'Fajl je prevelik (max {MAX_FILE_SIZE // (1024*1024)}MB)'

    return True, None


def upload_logo(file, tenant_id):
    """
    Upload a logo image to Cloudinary.

    Args:
        file: FileStorage object from request.files
        tenant_id: Tenant ID for organizing uploads

    Returns:
        dict with 'success', 'url', 'public_id' or 'error' key
    """
    # Validate file
    is_valid, error = validate_file(file)
    if not is_valid:
        return {'success': False, 'error': error}

    # Initialize Cloudinary
    if not init_cloudinary():
        return {'success': False, 'error': 'Cloudinary nije konfigurisan'}

    try:
        # Generate unique filename
        filename = secure_filename(file.filename)
        public_id = f"servishub/logos/tenant_{tenant_id}"

        # Upload to Cloudinary with transformations for logo
        result = cloudinary.uploader.upload(
            file,
            public_id=public_id,
            overwrite=True,
            folder=None,  # public_id already includes folder
            resource_type='image',
            transformation=[
                {'width': 500, 'height': 500, 'crop': 'limit'},  # Max dimensions
                {'quality': 'auto:good'},
                {'fetch_format': 'auto'}
            ]
        )

        return {
            'success': True,
            'url': result['secure_url'],
            'public_id': result['public_id'],
            'width': result.get('width'),
            'height': result.get('height')
        }

    except Exception as e:
        current_app.logger.error(f'Cloudinary upload error: {str(e)}')
        return {'success': False, 'error': f'Greška pri uploadu: {str(e)}'}


def delete_logo(tenant_id):
    """
    Delete a logo from Cloudinary.

    Args:
        tenant_id: Tenant ID

    Returns:
        dict with 'success' or 'error' key
    """
    if not init_cloudinary():
        return {'success': False, 'error': 'Cloudinary nije konfigurisan'}

    try:
        public_id = f"servishub/logos/tenant_{tenant_id}"
        result = cloudinary.uploader.destroy(public_id)

        return {'success': True, 'result': result.get('result')}

    except Exception as e:
        current_app.logger.error(f'Cloudinary delete error: {str(e)}')
        return {'success': False, 'error': f'Greška pri brisanju: {str(e)}'}
