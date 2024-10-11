from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
import requests
import os
from langchain_community.document_loaders import WebBaseLoader
import logging
from dotenv import load_dotenv
from git import Repo
import shutil
from werkzeug.utils import secure_filename
import boto3
from urllib.parse import urlparse
from botocore import UNSIGNED
from botocore.client import Config
import PyPDF2
import time

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')
app.config['UPLOAD_FOLDER'] = 'uploads'

API_URL = os.getenv('API_URL')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



def check_authentication():
    access_token = session.get('access_token')
    if access_token:
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            response = requests.get(f"{API_URL}/user_history", headers=headers)
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Authentication check failed: {response.text}")
                session.pop('access_token', None)
                flash('Session expired, please login again', 'danger')
                return False
        except requests.RequestException as e:
            logger.error(f"Error during authentication check: {e}")
            flash('Error during authentication check. Please login again.', 'danger')
            session.pop('access_token', None)
            return False
    else:
        flash('You need to login first', 'danger')
        return False



# Utility function to check if user is premium
def is_premium_user():
    token = session.get('access_token')
    if not token:
        flash('You need to log in to access this feature.', 'danger')
        return False

    headers = {'Authorization': f'Bearer {token}'}
    try:
        # Fetch user ID
        user_id_response = requests.get(f"{API_URL}/user/id", headers=headers)
        if user_id_response.status_code == 200:
            user_id = user_id_response.json().get('user_id')
        else:
            flash('Failed to retrieve user ID', 'danger')
            return False

        # Check if user is premium
        premium_status_response = requests.get(f"{API_URL}/user/{user_id}/premium/status", headers=headers)
        if premium_status_response.status_code == 200:
            return premium_status_response.json().get('premium_status', False)
        else:
            flash('Failed to verify premium status', 'danger')
            return False
    except requests.RequestException as e:
        logger.error(f"Error checking premium status: {e}")
        flash('Error during premium status check.', 'danger')
        return False



def aws_download_single_file(s3_url, local_file_path):
    # Parse the S3 URL to get the bucket name and object key
    parsed_url = urlparse(s3_url)
    bucket_name = parsed_url.netloc
    object_key = parsed_url.path.lstrip('/')
    
    # Create the S3 client with unsigned config for public access
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    
    try:
        # Download the file
        print(f"Downloading {object_key} from bucket {bucket_name} to {local_file_path}")
        s3.download_file(bucket_name, object_key, local_file_path)
        print(f"Download complete: {local_file_path}")
    except s3.exceptions.NoSuchBucket:
        print(f"Bucket {bucket_name} does not exist.")
    except s3.exceptions.NoSuchKey:
        print(f"Object {object_key} does not exist.")
    except Exception as e:
        print(f"Error downloading file: {e}")




def aws_download_single_file(bucket_url, local_file_path):
    # Parse the S3 URL to get the bucket name and file key
    parsed_url = urlparse(bucket_url)
    bucket_name = parsed_url.netloc
    object_key = parsed_url.path.lstrip('/')

    # Create the S3 client with unsigned config for public access
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))
    
    try:
        # Download the file
        print(f"Downloading {object_key} from bucket {bucket_name} to {local_file_path}")
        s3.download_file(bucket_name, object_key, local_file_path)
        print(f"Download complete: {local_file_path}")
    except Exception as e:
        print(f"Error downloading file: {e}")
        raise Exception(f"Error downloading file: {e}")


@app.route('/aws-single-file', methods=['POST'])
def aws_single_file():
    if not is_premium_user():
        return jsonify({'error': 'This feature is available to premium users only.'}), 403
    
    try:
        # Get S3 URL from the user input (assumed to be passed as JSON)
        data = request.json
        s3_url = data.get('s3_url')

        if not s3_url:
            return jsonify({'error': 'S3 URL is required'}), 400
        
        # Define the local file path where you want to save the file
        cwd = os.getcwd()
        local_file_path = os.path.join(cwd, 'aws_downloads', os.path.basename(urlparse(s3_url).path))

        # Ensure the local folder exists
        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
        
        # Call the function to download the single file from S3
        aws_download_single_file(s3_url, local_file_path)

        return jsonify({'message': f'File downloaded successfully to {local_file_path}'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# download all the contents from a bucket
def dump_bucket(bucket_url, local_folder):
    # Parse the S3 URL to get the bucket name
    parsed_url = urlparse(bucket_url)
    bucket_name = parsed_url.netloc

    # Create the S3 client with unsigned config for public access
    s3 = boto3.client('s3', config=Config(signature_version=UNSIGNED))

    try:
        # List all objects in the bucket
        paginator = s3.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=bucket_name)

        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    object_key = obj['Key']
                    # Define the local file path where you want to save the file
                    local_file_path = os.path.join(local_folder, object_key)

                    # Ensure the local folder exists
                    os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

                    # Download the file
                    print(f"Downloading {object_key} from bucket {bucket_name} to {local_file_path}")
                    s3.download_file(bucket_name, object_key, local_file_path)
                    print(f"Download complete: {local_file_path}")
    except Exception as e:
        print(f"Error dumping bucket: {e}")
        raise Exception(f"Error dumping bucket: {e}")

@app.route('/aws-bucket-dump', methods=['POST'])
def aws_bucket_dump():
    if not is_premium_user():
        return jsonify({'error': 'This feature is available to premium users only.'}), 403
    
    try:
        # Get bucket URL from the frontend (sent as JSON)
        data = request.json
        bucket_url = data.get('bucket_url')

        if not bucket_url:
            return jsonify({'error': 'Bucket URL is required'}), 400

        # Define the local folder where you want to save all files
        cwd = os.getcwd()
        local_folder = os.path.join(cwd, 'aws_bucket_dump')

        # Ensure the local folder exists
        os.makedirs(local_folder, exist_ok=True)

        # Dump the entire bucket
        dump_bucket(bucket_url, local_folder)

        return jsonify({'message': f'Bucket contents downloaded successfully to {local_folder}'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500



@app.route('/read-bucket-dump', methods=['GET'])
def read_bucket_dump():
    
    if not is_premium_user():
        return jsonify({'error': 'This feature is available to premium users only.'}), 403
    
    # The local folder where the bucket contents were dumped
    local_folder = os.path.join(os.getcwd(), 'aws_bucket_dump')
    
    # Allowed file extensions for text files
    allowed_file_extensions = [
        '.txt', '.json', '.csv', '.xml', '.yaml', '.yml', '.md', '.ini', '.log',
        '.html', '.css', '.scss', '.sass', '.less', '.py', '.js', '.ts', 
        '.jsx', '.tsx', '.cpp', '.c', '.h', '.java', '.rb', '.php', '.go', 
        '.swift', '.rs', '.kt', '.pl', '.lua', '.r', '.m', '.sh', '.bat'
    ]
    
    # File extensions considered binary (handled separately)
    binary_file_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.zip', '.tar', '.gz']
    
    try:
        if not os.path.exists(local_folder):
            return jsonify({'error': 'No bucket dump found'}), 400
        
        file_contents = []
        
        # Traverse through the dumped files in the local folder
        for root, dirs, files in os.walk(local_folder):
            for file in files:
                file_path = os.path.join(root, file)
                extension = os.path.splitext(file)[1].lower()
                
                if extension in allowed_file_extensions:
                    # Handle text files
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        file_contents.append({
                            'filename': file,
                            'content': content,
                            'is_binary': False
                        })
                    except Exception as e:
                        app.logger.error(f"Error reading file {file}: {str(e)}")
                        return jsonify({'error': f"Failed to read {file}"}), 500
                elif extension == '.pdf':
                    # Handle PDF files
                    try:
                        content = extract_pdf_text(file_path)
                        file_contents.append({
                            'filename': file,
                            'content': content,
                            'is_binary': False
                        })
                    except Exception as e:
                        app.logger.error(f"Error reading PDF {file}: {str(e)}")
                        return jsonify({'error': f"Failed to read {file}"}), 500
                elif extension in binary_file_extensions:
                    # Handle binary files (do not read the content, just indicate it's a binary file)
                    file_contents.append({
                        'filename': file,
                        'content': 'Binary file - content not displayed',
                        'is_binary': True
                    })
                else:
                    # Skip unsupported file types
                    continue

        return jsonify({'files': file_contents}), 200

    except Exception as e:
        app.logger.error(f"Error reading bucket dump: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Helper function to extract text from PDFs using PyPDF2
def extract_pdf_text(file_path):
    pdf_text = ""
    with open(file_path, 'rb') as pdf_file:
        reader = PyPDF2.PdfReader(pdf_file)
        # Extract text from each page
        for page_num in range(len(reader.pages)):
            page = reader.pages[page_num]
            pdf_text += page.extract_text()
    return pdf_text



@app.route('/read-files', methods=['POST'])
def read_files():
    allowed_file_extensions = [
    # Text and Data Files
    '.txt', '.json', '.csv', '.xml', '.yaml', '.yml', '.md', '.ini', '.log', '.pdf',
    
    # Web and Style Files
    '.html', '.css', '.scss', '.sass', '.less',
    
    # Programming and Scripting Languages
    '.py', '.js', '.ts', '.jsx', '.tsx', '.cpp', '.c', '.h', '.java', '.rb', 
    '.php', '.go', '.swift', '.rs', '.kt', '.pl', '.lua', '.r', '.m', 
    
    # Shell/Bash and Batch Files
    '.sh', '.bat'
    ]

    try:
        # Log the start of the function
        app.logger.info("Received request to read files.")
        print("Received request to read files.")

        # Check if files were provided in the request
        if 'files' not in request.files:
            app.logger.error("No files provided in the request.")
            print("No files provided in the request.")
            return jsonify({"error": "No files provided"}), 400

        # Get the list of files
        files = request.files.getlist('files')
        app.logger.info(f"Received {len(files)} files.")
        print(f"Received {len(files)} files.")

        # List to store the processed file contents
        file_contents = []

        if not files:
            app.logger.error("Empty file list in the request.")
            print("Empty file list in the request.")
            return jsonify({"error": "No files provided"}), 400

        # Iterate over the files
        for file in files:
            filename = file.filename
            app.logger.info(f"Processing file: {filename}")
            print(f"Processing file: {filename}")

            # Check if the file extension is allowed
            if not filename.endswith(tuple(allowed_file_extensions)):
                app.logger.warning(f"Skipping unsupported file: {filename}")
                print(f"Skipping unsupported file: {filename}")
                continue

            try:
                # Read the content as text (assuming UTF-8 encoding)
                content = file.read().decode('utf-8')
                file_contents.append({
                    'filename': filename,
                    'content': content
                })
                app.logger.info(f"Successfully processed file: {filename}")
                print(f"Successfully processed file: {filename}")

            except Exception as e:
                app.logger.error(f"Error processing file {filename}: {str(e)}")
                print(f"Error processing file {filename}: {str(e)}")
                return jsonify({"error": f"Failed to process {filename}"}), 500

        # Log the total number of successfully processed files
        app.logger.info(f"Successfully processed {len(file_contents)} files out of {len(files)}.")
        print(f"Successfully processed {len(file_contents)} files out of {len(files)}.")

        return jsonify(file_contents), 200

    except Exception as e:
        # Log the error in case of an exception
        app.logger.error(f"Server Error: {str(e)}")
        print(f"Server Error: {str(e)}")
        return jsonify({"error": str(e)}), 500



@app.route('/get-repo-file-content', methods=['GET'])
def get_repo_file_content():
    filename = request.args.get('filename')
    repo_directory = 'repofetch'  # Directory where the repo was cloned

    # Check if the file exists
    file_path = os.path.join(repo_directory, filename)
    
    if not os.path.exists(file_path):
        app.logger.error(f"File not found: {filename}")
        return jsonify({"error": "File not found"}), 404
    
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        app.logger.info(f"Successfully fetched content for file: {filename}")
        return jsonify({"filename": filename, "content": content}), 200

    except Exception as e:
        app.logger.error(f"Error reading file {filename}: {str(e)}")
        return jsonify({"error": str(e)}), 500




@app.before_request
def before_request():
    if request.endpoint not in ('login', 'register', 'static'):
        if not check_authentication():
            return redirect(url_for('login'))



@app.route('/')
def home():
    packs = []
    code_packs = []  # Initialize an empty list for code packs
    if 'access_token' in session:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        try:
            # Fetch regular packs
            response = requests.get(f"{API_URL}/packman/list_packs", headers=headers)
            if response.status_code == 200:
                packs = response.json()
            else:
                logger.error(f"Failed to fetch packs: {response.text}")
                flash('Failed to fetch packs', 'danger')

            # Fetch code packs
            response = requests.get(f"{API_URL}/packman/code/list_code_packs", headers=headers)
            if response.status_code == 200:
                code_packs = response.json()
            else:
                logger.error(f"Failed to fetch code packs: {response.text}")
                flash('Failed to fetch code packs', 'danger')

        except requests.RequestException as e:
            logger.error(f"Error fetching packs: {e}")
            flash('Error fetching packs', 'danger')
    return render_template('home.html', packs=packs, code_packs=code_packs)


#packman-code html page
@app.route('/packman-code')
def packman_code():
    return render_template('packman_code.html')
    

#leaves out .git files and directories
def get_files_in_repofetch():
    directory_path = 'repofetch'
    if os.path.exists(directory_path) and os.path.isdir(directory_path):
        # Skip .git directory and any other directories
        return [f for f in os.listdir(directory_path) if f != '.git' and not os.path.isdir(os.path.join(directory_path, f))]
    return []

# upload file
@app.route('/upload-file', methods=['POST'])
def upload_file():
    try:
        directory_path = 'repofetch'
        logging.debug('Entered upload_file function')

        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
            logging.debug(f"Directory 'repofetch' created at: {directory_path}")
        else:
            logging.debug(f"Directory '{directory_path}' already exists.")

        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        filename = secure_filename(file.filename)
        file_path = os.path.join(directory_path, filename)
        file.save(file_path)
        logging.debug(f"File '{filename}' uploaded to '{file_path}'")

        files = get_files_in_repofetch()
        return jsonify({"message": f"File '{filename}' successfully uploaded", "files": files}), 200

    except Exception as e:
        logging.error(f"Server Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/fetch-repo', methods=['POST'])
def fetch_repo():
    try:
        directory_path = 'repofetch'
        logging.debug('Entered fetch_repo function')

        if os.path.exists(directory_path) and os.path.isdir(directory_path):
            logging.debug(f"The directory '{directory_path}' already exists.")
            return jsonify({"error": "Directory already exists"}), 400

        repo_fetch_dir = os.path.join(os.getcwd(), 'repofetch')
        os.makedirs(repo_fetch_dir, exist_ok=True)
        logging.debug(f"Directory 'repofetch' created at: {repo_fetch_dir}")

        repo_url = request.form.get('repoURL')
        logging.debug(f"REPO URL: {repo_url}")

        if not repo_url:
            logging.error("No repository URL provided.")
            return jsonify({"error": "No repository URL provided"}), 400

        try:
            logging.info(f"Attempting to clone repository from URL: {repo_url}")
            repo = Repo.clone_from(repo_url, repo_fetch_dir)
            logging.info("Repository successfully cloned.")
        except Exception as e:
            logging.error(f"Failed to fetch repository: {e}")
            return jsonify({"error": str(e)}), 500

        try:
            files = get_files_in_repofetch()
            logging.debug(f"Files in 'repofetch': {files}")
            return jsonify({"message": "Repository successfully fetched", "files": files}), 200
        except Exception as e:
            logging.error(f"Error retrieving files from 'repofetch': {e}")
            return jsonify({"error": str(e)}), 500

    except Exception as e:
        logging.error(f"Server Error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/clear-repo', methods=['POST'])
def clear_repo():
    try:
        repo_directory_path = 'repofetch'
        deeplake_directory_path = 'my_deeplake'

        logging.debug("Starting clear_repo function")

        # Attempt to delete the repo directory
        if os.path.exists(repo_directory_path) and os.path.isdir(repo_directory_path):
            logging.debug(f"Attempting to delete directory '{repo_directory_path}'")
            for _ in range(3):  # Retry up to 3 times
                try:
                    shutil.rmtree(repo_directory_path)
                    logging.debug(f"Directory '{repo_directory_path}' deleted successfully")
                    break
                except Exception as e:
                    logging.error(f"Failed to delete directory '{repo_directory_path}': {e}")
                    time.sleep(1)  # Wait before retrying
            else:
                return jsonify({"error": f"Failed to delete directory '{repo_directory_path}' after retries"}), 500

        # Attempt to delete the deeplake directory
        if os.path.exists(deeplake_directory_path) and os.path.isdir(deeplake_directory_path):
            logging.debug(f"Attempting to delete directory '{deeplake_directory_path}'")
            try:
                shutil.rmtree(deeplake_directory_path)
                logging.debug(f"Directory '{deeplake_directory_path}' deleted successfully")
            except Exception as e:
                logging.error(f"Failed to delete directory '{deeplake_directory_path}': {e}")
                return jsonify({"error": f"Failed to delete directory '{deeplake_directory_path}': {e}"}), 500

        # Delete processed files metadata
        main_directory = os.getcwd()
        file = os.path.join(main_directory, 'processed_files_metadata.json')
        if os.path.exists(file):
            try:
                os.remove(file)
                logging.debug(f"File 'processed_files_metadata.json' deleted successfully")
            except Exception as e:
                logging.error(f"Failed to delete file 'processed_files_metadata.json': {e}")
                return jsonify({"error": f"Failed to delete file 'processed_files_metadata.json': {e}"}), 500

        logging.debug("clear_repo function completed successfully")
        return jsonify({"message": "Directory cleared"}), 200
    except Exception as e:
        logging.error(f"Server Error: {e}")
        return jsonify({"error": str(e)}), 500



@app.route('/del-pack')
def del_pack():
    packs = []
    code_packs = []
    if 'access_token' in session:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        try:
            # Fetch regular packs
            response = requests.get(f"{API_URL}/packman/list_packs", headers=headers)
            if response.status_code == 200:
                packs = response.json()
            else:
                logger.error(f"Failed to fetch packs: {response.text}")
                flash('Failed to fetch packs', 'danger')

            # Fetch code packs
            response = requests.get(f"{API_URL}/packman/code/list_code_packs", headers=headers)
            if response.status_code == 200:
                code_packs = response.json()
            else:
                logger.error(f"Failed to fetch code packs: {response.text}")
                flash('Failed to fetch code packs', 'danger')

        except requests.RequestException as e:
            logger.error(f"Error fetching packs: {e}")
            flash('Error fetching packs', 'danger')
    return render_template('del_pack.html', packs=packs, code_packs=code_packs)




@app.route('/delete_pack/<int:pack_id>', methods=['DELETE'])
def delete_pack(pack_id):
    if 'access_token' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    token = session.get('access_token')
    headers = {'Authorization': f'Bearer {token}'}
    try:
        response = requests.delete(f"{API_URL}/packman/pack/{pack_id}", headers=headers)
        if response.status_code == 200:
            return jsonify({'message': 'Pack deleted successfully'}), 200
        else:
            logger.error(f"Failed to delete pack: {response.text}")
            return jsonify({'message': 'Failed to delete pack'}), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error deleting pack: {e}")
        return jsonify({'message': 'Error deleting pack'}), 500



@app.route('/delete_code_pack/<int:pack_id>', methods=['DELETE'])
def delete_code_pack(pack_id):
    if 'access_token' not in session:
        return jsonify({'message': 'Unauthorized'}), 401

    token = session.get('access_token')
    headers = {'Authorization': f'Bearer {token}'}
    try:
        response = requests.delete(f"{API_URL}/packman/code_pack/{pack_id}", headers=headers)
        if response.status_code == 200:
            return jsonify({'message': 'Code pack deleted successfully'}), 200
        else:
            logger.error(f"Failed to delete code pack: {response.text}")
            return jsonify({'message': 'Failed to delete code pack'}), response.status_code
    except requests.RequestException as e:
        logger.error(f"Error deleting code pack: {e}")
        return jsonify({'message': 'Error deleting code pack'}), 500



@app.route('/register', methods=['GET', 'POST'])
def register():
    return redirect("https://sourcebox-official-website-9f3f8ae82f0b.herokuapp.com/sign_up")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        try:
            response = requests.post(f"{API_URL}/login", json={
                'email': email,
                'password': password
            })

            if response.status_code == 200:
                access_token = response.json().get('access_token')
                session['access_token'] = access_token
                flash('Logged in successfully!', 'success')
                return redirect(url_for('packman'))
            else:
                message = response.json().get('message', 'Login failed')
                logger.error(f"Login failed: {message}")
                flash(message, 'danger')
        except requests.RequestException as e:
            logger.error(f"Error during login: {e}")
            flash('Error during login', 'danger')

    return render_template('login.html')


@app.route('/packman')
def packman():
    return render_template('packman.html')


@app.route('/packman/package_pack', methods=['POST'])
def package_pack():
    token = session.get('access_token')
    data = request.get_json()

    pack_name = data.get('pack_name')
    contents = data.get('contents')

    if not pack_name or not contents:
        return jsonify({'message': 'Pack name and contents are required'}), 400

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    try:
        response = requests.post(f"{API_URL}/packman/pack", json={
            'pack_name': pack_name,
            'contents': contents
        }, headers=headers)

        if response.status_code != 201:
            logger.error(f"Failed to process pack: {response.text}")
            return jsonify({'message': 'Failed to process pack'}), 500

        return jsonify(response.json()), 201
    except requests.RequestException as e:
        logger.error(f"Error processing pack: {e}")
        return jsonify({'message': 'Error processing pack'}), 500




@app.route('/packman/preview_link', methods=['POST'])
def preview_link():
    link = request.json.get('link')
    if not link:
        return jsonify({'message': 'Link is required'}), 400

    try:
        loader = WebBaseLoader(link)
        docs = loader.load()

        docs_json = [{'url': doc.metadata.get('url'), 'content': doc.page_content} for doc in docs]

        return jsonify({'message': 'Link processed successfully', 'docs': docs_json})
    except Exception as e:
        logger.error(f"Error processing link: {e}")
        return jsonify({'message': 'Error processing link'}), 500



@app.route('/packman/preview_file', methods=['POST'])
def preview_file():
    if 'file' not in request.files:
        return jsonify({'message': 'File is required'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400

    try:
        content = file.read().decode('utf-8')  # Assuming text files for simplicity

        return jsonify({'message': 'File processed successfully', 'content': content})
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        return jsonify({'message': 'Error processing file'}), 500



@app.route('/packman/list_packs', methods=['GET'])
def list_packs():
    token = session.get('access_token')
    if not token:
        flash('You need to login first', 'danger')
        return redirect(url_for('login'))

    headers = {'Authorization': f'Bearer {token}'}
    try:
        response = requests.get(f"{API_URL}/packman/list_packs", headers=headers)

        if response.status_code == 200:
            packs = response.json()
            return jsonify(packs)
        else:
            logger.error(f"Failed to fetch packs: {response.text}")
            flash('Failed to fetch packs', 'danger')
            return jsonify({'message': 'Failed to fetch packs'}), 500
    except requests.RequestException as e:
        logger.error(f"Error fetching packs: {e}")
        flash('Error fetching packs', 'danger')
        return jsonify({'message': 'Error fetching packs'}), 500


@app.route('/packman-code/package_code_pack', methods=['POST'])
def package_code_pack():
    token = session.get('access_token')
    data = request.get_json()

    pack_name = data.get('pack_name')
    contents = data.get('contents')

    if not pack_name or not contents:
        flash('Pack name and contents are required', 'danger')
        return jsonify({'message': 'Pack name and contents are required'}), 400

    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    try:
        response = requests.post(f"{API_URL}/packman/code_pack", json={
            'pack_name': pack_name,
            'contents': contents
        }, headers=headers)

        if response.status_code != 201:
            logger.error(f"Failed to process code pack: {response.text}")
            flash('Failed to process code pack', 'danger')
            return jsonify({'message': 'Failed to process code pack'}), 500

        flash('Code pack published successfully!', 'success')
        return jsonify(response.json()), 201
    except requests.RequestException as e:
        logger.error(f"Error processing code pack: {e}")
        flash('Error processing code pack', 'danger')
        return jsonify({'message': 'Error processing code pack'}), 500




@app.route('/logout')
def logout():
    session.pop('access_token', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))




if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, use_reloader=False, host="0.0.0.0", port=port) #was port 80