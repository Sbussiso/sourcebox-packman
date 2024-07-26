from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
import requests
import os
from langchain_community.document_loaders import WebBaseLoader

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your_secret_key')
app.config['UPLOAD_FOLDER'] = 'uploads'

API_URL = 'https://sourcebox-central-auth-8396932a641c.herokuapp.com'

def check_authentication():
    access_token = session.get('access_token')
    if access_token:
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(f"{API_URL}/user_history", headers=headers)
        if response.status_code == 200:
            return True
        else:
            session.pop('access_token', None)
            flash('Session expired, please login again', 'danger')
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
    if 'access_token' in session:
        flash('You are already authenticated', 'success')
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        
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
            flash(message, 'danger')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
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
            flash(message, 'danger')
    
    return render_template('login.html')

@app.route('/packman')
def packman():
    return render_template('packman.html')

@app.route('/packman/web_pack', methods=['POST'])
def web_pack():
    token = session.get('access_token')
    data = request.get_json()

    pack_name = data.get('pack_name')
    docs = data.get('docs')
    if not pack_name or not docs:
        return jsonify({'message': 'Pack name and docs are required'}), 400

    headers = {'Authorization': f'Bearer {token}'}
    response = requests.post(f"{API_URL}/packman/web_pack", json=data, headers=headers)
    
    if response.status_code != 201:
        flash('Failed to process link', 'danger')
        return jsonify({'message': 'Failed to process link'}), 500

    flash('Link processed successfully', 'success')
    return jsonify({'message': 'Link processed successfully'})

@app.route('/packman/file_pack', methods=['POST'])
def file_pack():
    token = session.get('access_token')
    pack_name = request.form.get('pack_name')
    if 'file' not in request.files or not pack_name:
        return jsonify({'message': 'Pack name and file are required'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    
    session_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'user_files')
    os.makedirs(session_folder, exist_ok=True)
    
    filename = file.filename
    filepath = os.path.join(session_folder, filename)
    file.save(filepath)

    headers = {'Authorization': f'Bearer {token}'}
    data = {'pack_name': pack_name, 'filename': filename, 'filepath': filepath}
    response = requests.post(f"{API_URL}/packman/file_pack", json=data, headers=headers)

    if response.status_code != 201:
        flash('Failed to upload file', 'danger')
        return jsonify({'message': 'Failed to upload file'}), 500

    flash('File uploaded successfully', 'success')
    return jsonify({'message': 'File uploaded successfully', 'filename': filename}), 201

@app.route('/packman/preview_link', methods=['POST'])
def preview_link():
    link = request.json.get('link')
    if not link:
        return jsonify({'message': 'Link is required'}), 400

    loader = WebBaseLoader(link)
    docs = loader.load()

    docs_json = [{'url': doc.metadata.get('url'), 'content': doc.page_content} for doc in docs]
    
    return jsonify({'message': 'Link processed successfully', 'docs': docs_json})

@app.route('/packman/preview_file', methods=['POST'])
def preview_file():
    if 'file' not in request.files:
        return jsonify({'message': 'File is required'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
    
    content = file.read().decode('utf-8')  # Assuming text files for simplicity

    return jsonify({'message': 'File processed successfully', 'content': content})

@app.route('/logout')
def logout():
    session.pop('access_token', None)
    flash('Logged out successfully!', 'success')
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
