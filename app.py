import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file
from werkzeug.utils import secure_filename
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient
import gridfs

# MongoDB Atlas connection

MONGO_URI = "mongodb+srv://john:22F01A0514jOHN@hackathon.qp5qlat.mongodb.net/?retryWrites=true&w=majority&appName=Hackathon"
client = MongoClient(MONGO_URI)
db = client["hackathon_portal"]
fs = gridfs.GridFS(db)

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max upload

# Allowed poster extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Home Page
@app.route('/')
def index():
    return render_template('index.html')

# ---------------- COLLEGE ROUTES ----------------
@app.route('/college/signup', methods=['GET', 'POST'])
def college_signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        address = request.form['address']
        password = request.form['password']
        # Check if college exists
        exists = db.colleges.find_one({'name': name})
        if exists:
            flash('College name already exists!', 'danger')
            return redirect(url_for('college_signup'))
        db.colleges.insert_one({
            'name': name,
            'email': email,
            'address': address,
            'password': password
        })
        flash('Signup successful! Please login.', 'success')
        return redirect(url_for('college_login'))
    return render_template('college_signup.html')

@app.route('/college/login', methods=['GET', 'POST'])
def college_login():
    if request.method == 'POST':
        name = request.form['name']
        password = request.form['password']
        college = db.colleges.find_one({'name': name, 'password': password})
        if college:
            session['college_id'] = str(college['_id'])
            session['college_name'] = college['name']
            return redirect(url_for('college_dashboard'))
        flash('Invalid credentials!', 'danger')
    return render_template('college_login.html')

@app.route('/college/dashboard', methods=['GET', 'POST'])
def college_dashboard():
    if 'college_id' not in session:
        return redirect(url_for('college_login'))
    college_id = session['college_id']
    # Post Hackathon
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        post_date = datetime.now().date().isoformat()
        deadline = request.form['deadline']
        prizes = request.form.get('prizes', '')
        poster_url = None
        file = request.files.get('poster')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_bytes = file.read()
            try:
                file_id = fs.put(file_bytes, filename=filename, content_type=file.content_type)
                poster_url = url_for('serve_image', file_id=str(file_id))
            except Exception as e:
                flash('Poster upload failed: ' + str(e), 'danger')
        db.hackathons.insert_one({
            'title': title,
            'description': description,
            'post_date': post_date,
            'deadline': deadline,
            'prizes': prizes,
            'poster_url': poster_url,
            'college_id': college_id
        })
        flash('Hackathon posted!', 'success')
        return redirect(url_for('college_dashboard'))
    # View hackathons
    hackathons = list(db.hackathons.find({'college_id': college_id}).sort('post_date', -1))
    for h in hackathons:
        if h.get('poster_url') and not str(h['poster_url']).startswith('/image/'):
            h['poster_url'] = url_for('serve_image', file_id=str(h['poster_url']))
    print('DEBUG: hackathons in college_dashboard:', [(h.get('title'), h.get('poster_url')) for h in hackathons])
    # View judges
    judges = list(db.judges.find({'college_id': college_id}))
    # View student ideas
    ideas = list(db.ideas.find({'hackathon_id': {'$in': [h['_id'] for h in hackathons]}}))
    # Only show ideas for this college's hackathons
    college_hackathon_ids = [h['_id'] for h in hackathons]
    ideas = [i for i in ideas if i['hackathon_id'] in college_hackathon_ids]
    # Attach student and hackathon details to each idea
    for idea in ideas:
        student = db.students.find_one({'_id': ObjectId(idea['student_id'])}) if idea.get('student_id') else None
        hackathon = db.hackathons.find_one({'_id': idea['hackathon_id']}) if idea.get('hackathon_id') else None
        idea['students'] = {'name': student['name']} if student else {'name': ''}
        idea['hackathons'] = {'title': hackathon['title']} if hackathon else {'title': ''}
    # Fetch college details
    college = db.colleges.find_one({'_id': ObjectId(college_id)})
    return render_template('college_dashboard.html', hackathons=hackathons, judges=judges, ideas=ideas, college=college)

@app.route('/college/judge', methods=['POST'])
def add_judge():
    if 'college_id' not in session:
        return redirect(url_for('college_login'))
    judge_id = request.form['judge_id']
    name = request.form['name']
    password = request.form['password']
    college_id = session['college_id']
    exists = db.judges.find_one({'judge_id': judge_id})
    if exists:
        flash('Judge ID already exists!', 'danger')
    else:
        db.judges.insert_one({
            'judge_id': judge_id,
            'name': name,
            'password': password,
            'college_id': college_id
        })
        flash('Judge added!', 'success')
    return redirect(url_for('college_dashboard'))

@app.route('/college/logout')
def college_logout():
    session.clear()
    return redirect(url_for('index'))

# ---------------- STUDENT ROUTES ----------------
@app.route('/student/signup', methods=['GET', 'POST'])
def student_signup():
    colleges = list(db.colleges.find({}, {'_id': 1, 'name': 1}))
    if request.method == 'POST':
        name = request.form['name']
        roll_no = request.form['roll_no']
        password = request.form['password']
        year = request.form['year']
        branch = request.form['branch']
        college_id = str(request.form['college_id'])
        print('DEBUG: college_id from form:', college_id)
        if not college_id or college_id == 'None':
            flash('Please select a college.', 'danger')
            return redirect(url_for('student_signup'))
        exists = db.students.find_one({'roll_no': roll_no})
        if exists:
            flash('Roll number already exists!', 'danger')
            return redirect(url_for('student_signup'))
        db.students.insert_one({
            'name': name,
            'roll_no': roll_no,
            'password': password,
            'year': year,
            'branch': branch,
            'college_id': college_id
        })
        flash('Signup successful! Please login.', 'success')
        return redirect(url_for('student_login'))
    return render_template('student_signup.html', colleges=colleges)

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        roll_no = request.form['roll_no']
        password = request.form['password']
        student = db.students.find_one({'roll_no': roll_no, 'password': password})
        print("LOGIN QUERY RESULT:", student)
        if student:
            session['student_id'] = str(student['_id'])
            session['student_name'] = student['name']
            session['college_id'] = student['college_id']
            return redirect(url_for('student_dashboard'))
        flash('Invalid credentials!', 'danger')
    return render_template('student_login.html')

@app.route('/student/dashboard', methods=['GET', 'POST'])
def student_dashboard():
    if 'student_id' not in session:
        return redirect(url_for('student_login'))
    student_id = session['student_id']
    college_id = session['college_id']
    # View hackathons
    hackathons = list(db.hackathons.find({'college_id': college_id}).sort('post_date', -1))
    for h in hackathons:
        if h.get('poster_url') and not str(h['poster_url']).startswith('/image/'):
            h['poster_url'] = url_for('serve_image', file_id=str(h['poster_url']))
        h['hackathon_id'] = str(h['_id'])
    print('DEBUG: hackathons in student_dashboard:', [(h.get('title'), h.get('poster_url')) for h in hackathons])
    # Submit idea
    if request.method == 'POST':
        hackathon_id = request.form['hackathon_id']
        title = request.form['title']
        description = request.form['description']
        prototype = request.form.get('prototype', '')
        db.ideas.insert_one({
            'student_id': student_id,
            'hackathon_id': ObjectId(hackathon_id),
            'title': title,
            'description': description,
            'prototype': prototype
        })
        flash('Idea submitted!', 'success')
        return redirect(url_for('student_dashboard'))
    # View submitted ideas
    ideas = list(db.ideas.find({'student_id': student_id}).sort('post_date', -1))
    # Attach hackathon title and scores to each idea
    for idea in ideas:
        hackathon = db.hackathons.find_one({'_id': idea['hackathon_id']})
        idea['hackathons'] = {'title': hackathon['title']} if hackathon else {'title': ''}
        # Attach all scores for this idea
        idea_scores = list(db.scores.find({'idea_id': idea['_id']}))
        idea['scores'] = idea_scores
    # Fetch student details
    student = db.students.find_one({'_id': ObjectId(student_id)})
    return render_template('student_dashboard.html', hackathons=hackathons, ideas=ideas, student=student)

@app.route('/student/logout')
def student_logout():
    session.clear()
    return redirect(url_for('index'))

# ---------------- JUDGE ROUTES ----------------
@app.route('/judge/login', methods=['GET', 'POST'])
def judge_login():
    if request.method == 'POST':
        judge_id = request.form['judge_id']
        password = request.form['password']
        judge = db.judges.find_one({'judge_id': judge_id, 'password': password})
        if judge:
            session['judge_id'] = judge['judge_id']
            session['judge_name'] = judge['name']
            session['college_id'] = judge['college_id']
            return redirect(url_for('judge_dashboard'))
        flash('Invalid credentials!', 'danger')
    return render_template('judge_login.html')

@app.route('/judge/dashboard', methods=['GET', 'POST'])
def judge_dashboard():
    if 'judge_id' not in session:
        return redirect(url_for('judge_login'))
    judge_id = session['judge_id']
    college_id = session['college_id']
    # Get hackathons for this college
    hackathons = list(db.hackathons.find({'college_id': college_id}))
    hackathon_ids = [h['_id'] for h in hackathons]
    # Get ideas for these hackathons
    ideas = list(db.ideas.find({
        'hackathon_id': {'$in': hackathon_ids}
    }).sort('post_date', -1))
    # Attach student and hackathon details to each idea
    for idea in ideas:
        student = db.students.find_one({'_id': ObjectId(idea['student_id'])}) if idea.get('student_id') else None
        hackathon = db.hackathons.find_one({'_id': idea['hackathon_id']}) if idea.get('hackathon_id') else None
        idea['students'] = {'name': student['name']} if student else {'name': ''}
        idea['hackathons'] = {'title': hackathon['title']} if hackathon else {'title': ''}
        idea['idea_id'] = str(idea['_id'])
        # Attach scores for this judge
        idea_scores = list(db.scores.find({'idea_id': idea['_id'], 'judge_id': judge_id}))
        idea['scores'] = idea_scores
    # Handle scoring
    if request.method == 'POST':
        idea_id = request.form['idea_id']
        score = int(request.form['score'])
        # Upsert score
        existing_score = db.scores.find_one({'idea_id': ObjectId(idea_id), 'judge_id': judge_id})
        if existing_score:
            db.scores.update_one({'_id': existing_score['_id']}, {'$set': {'score': score}})
        else:
            db.scores.insert_one({'idea_id': ObjectId(idea_id), 'judge_id': judge_id, 'score': score})
        flash('Score submitted!', 'success')
        return redirect(url_for('judge_dashboard'))
    return render_template('judge_dashboard.html', ideas=ideas)

@app.route('/judge/logout')
def judge_logout():
    session.clear()
    return redirect(url_for('index'))

# Endpoint to serve images from GridFS
@app.route('/image/<file_id>')
def serve_image(file_id):
    try:
        file = fs.get(ObjectId(file_id))
        return send_file(file, mimetype=file.content_type)
    except Exception as e:
        flash('Image not found.', 'danger')
        return '', 404

if __name__ == '__main__':
    app.run(debug=True) 
