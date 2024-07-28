from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
import requests
import os
from langchain_community.document_loaders import WebBaseLoader
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')
app.config['UPLOAD_FOLDER'] = 'uploads'

API_URL = 'https://sourcebox-central-auth-8396932a641c.herokuapp.com'

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

@app.before_request
def before_request():
    if request.endpoint not in ('login', 'register', 'static'):
        if not check_authentication():
            return redirect(url_for('login'))

@app.route('/')
def home():
    packs = []
    if 'access_token' in session:
        token = session.get('access_token')
        headers = {'Authorization': f'Bearer {token}'}
        try:
            response = requests.get(f"{API_URL}/packman/list_packs", headers=headers)
            if response.status_code == 200:
                packs = response.json()
            else:
                logger.error(f"Failed to fetch packs: {response.text}")
                flash('Failed to fetch packs', 'danger')
        except requests.RequestException as e:
            logger.error(f"Error fetching packs: {e}")
            flash('Error fetching packs', 'danger')
    return render_template('home.html', packs=packs)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')

        try:
            response = requests.post(f"{API_URL}/register", json={
                'email': email,
                'username': username,
                'password': password
            })

            if response.status_code == 201:
                flash('User registered successfully!', 'success')
                return redirect(url_for('login'))
            else:
                message = response.json().get('message', 'Registration failed')
                logger.error(f"Registration failed: {message}")
                flash(message, 'danger')
        except requests.RequestException as e:
            logger.error(f"Error during registration: {e}")
            flash('Error during registration', 'danger')

    return render_template('register.html')

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

@app.route('/logout')
def logout():
    session.pop('access_token', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
