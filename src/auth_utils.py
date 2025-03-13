from functools import wraps
from flask import request, redirect, url_for, current_app

def check_auth(username, password):
    """Check if a username/password combination is valid."""
    return username == current_app.config['AUTH_USERNAME'] and password == current_app.config['AUTH_PASSWORD']

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated