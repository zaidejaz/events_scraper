from flask import Blueprint, render_template, request, redirect, url_for, current_app, session
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from datetime import datetime

auth_bp = Blueprint('auth', __name__)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.session_protection = 'strong'

class User(UserMixin):
    def __init__(self, id):
        self.id = id
        self.last_active = datetime.now()
    
    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    if user_id == current_app.config['AUTH_USERNAME']:
        return User(user_id)
    return None

@auth_bp.before_request
def before_request():
    if current_user.is_authenticated:
        session.permanent = True  # Enable permanent session
        session['last_active'] = datetime.utcnow().isoformat()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('events.events_page'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember', False)
        
        if username == current_app.config['AUTH_USERNAME'] and \
           password == current_app.config['AUTH_PASSWORD']:
            user = User(username)
            login_user(user, remember=remember)
            session.permanent = True
            
            # Get the next page from the URL parameters
            next_page = request.args.get('next')
            # Make sure the next page is a relative URL (security measure)
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('events.events_page')
                
            return redirect(next_page)
        
        return render_template('login.html', error='Invalid credentials')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('auth.login'))