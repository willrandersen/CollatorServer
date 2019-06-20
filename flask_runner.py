from flask import Flask, request, Response
from enum import Enum
import requests
from random import randint
import flask
import lxml.html
from bs4 import BeautifulSoup
import json
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_heroku import Heroku
import pickle
import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
#app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Locomotives12moby!@localhost:5432/user_data'
heroku = Heroku(app)
db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = "user_cookie_data"
    id = db.Column(db.Integer, primary_key=True)
    cookie = db.Column(db.String(60), unique=True)
    user_name = db.Column(db.String(20))
    session = db.Column(db.Text)
    name = db.Column(db.String)
    last_login = db.Column(db.DateTime)

    def __init__(self, cookie, username, session, name, time):
        self.cookie = cookie
        self.user_name = username
        self.session = pickle.dumps(session, protocol=2)
        self.name = name
        self.last_login = time

    def __repr__(self):
        return str({'id' : self.id, 'user_name' : self.user_name, 'cookie' : self.cookie, 'name' : self.name, 'login' : self.last_login})

    def serialize(self):
        return {'id' : self.id, 'user_name' : self.user_name, 'cookie' : self.cookie, 'session' : self.session, 'name' : self.name, 'login' : self.last_login}


class Login_Error(Enum):
    INVALID = -1
    TIME_OUT = -2
    NETWORKING_FAILURE = -3

def MOL_Login(session, user, password):
    payload = {'Username': user, 'Password': password, 'Connection': 'NA',
               'USER': user, 'SMAUTHREASON': '0', 'btnLogin': 'Login', 'FullURL': '',
               'target': 'https://motonline.mot-solutions.com/default.asp', 'SMAGENTNAME': '', 'REALMOID': '',
               'postpreservationdata': '', 'hdnTxtCancel': '', 'hdnTxtContinue': ''}
    MOL_url_GET_Login = 'https://businessonline.motorolasolutions.com/login.aspx?authn_try_count=0&contextType=external&username=string&initial_command=NONE&contextValue=%2Foam&password=sercure_string&challenge_url=https%3A%2F%2Foamprod.motorolasolutions.com%2FOAMSamlRedirect%2FOAMCustomRedircet.jsp&request_id=7662974962118535276&CREDENTIAL_CONTEXT_DATA=USER_ACTION_COMMAND%2CUSER_ACTION_COMMAND%2Cnull%2Chidden%3BUsername%2CUser+ID%2C%2Ctext%3BPassword%2CPassword%2C%2Cpassword%3B&PLUGIN_CLIENT_RESPONSE=UserNamePswdClientResponse%3DUsername+and+Password+are+mandatory&locale=en_US&resource_url=https%253A%252F%252Fbusinessonline.motorolasolutions.com%252F'
    MOL_url_POST_Login = 'https://oamprod.motorolasolutions.com/oam/server/auth_cred_submit'
    login_page_text = session.get(MOL_url_GET_Login).text
    login_html = lxml.html.fromstring(login_page_text)
    hidden_inputs = login_html.xpath(r'//form//input[@type="hidden"]')
    for x in hidden_inputs:
        dict = x.attrib
        if 'value' in dict.keys():
            payload[dict['name']] = dict['value']
    login_request = session.post(MOL_url_POST_Login, data=payload)
    return login_request.text

def initiate_login(session, username, password):
    Login_attempt = MOL_Login(session, username, password)
    initial_login_parser = BeautifulSoup(Login_attempt, 'html.parser')

    if len(initial_login_parser.find_all('div', id='login-form')) != 0:
        return Login_Error.INVALID
    if len(initial_login_parser.find_all('p', class_='loginFailed')) != 0:
        return Login_Error.TIME_OUT
    return Login_attempt

def get_name_from_parser(parser):
    JSscript = parser.find_all('script', type="text/javascript")
    # print(JSscript[3].get_text().strip().startswith("var sBaseUrl = 'https://businessonline.motorolasolutions.com';"))
    for script in JSscript:
        if (script.get_text().strip().startswith("var sBaseUrl = 'https://businessonline.motorolasolutions.com';")):
            JSlogin_name = script.get_text().strip()
            find_string = 'var sLogonName = '
            JSlogin_name = JSlogin_name[JSlogin_name.index(find_string) + 1 + len(find_string):]
            JSlogin_name = JSlogin_name[:JSlogin_name.index("'")]
            return JSlogin_name

def getRandomLetters():
    output_string = ''
    sample = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
    for index in range(0, 60):
        index = randint(0, len(sample) - 1)
        output_string +=  sample[index]
    return output_string

def isLoggedIn(request):
    if 'logged_in_cookie' not in request.cookies.keys():
        return False
    requested_with_cookie = request.cookies.get('logged_in_cookie')
    row_with_cookie = User.query.filter_by(cookie= requested_with_cookie).first()
    if row_with_cookie is None:
        return False
    duration = datetime.datetime.now() - row_with_cookie.last_login
    duration_in_seconds = duration.total_seconds()
    if duration_in_seconds > (15 * 60):
        return False
    return True

def remove_outdated(username):
    all_user_logins = User.query.filter_by(user_name= username).all()
    for each_login in all_user_logins:
        time_since_login = datetime.datetime.now() - each_login.last_login
        time_since_login_seconds = time_since_login.total_seconds()
        if time_since_login_seconds > 15 * 60:
            User.query.filter_by(cookie=each_login.cookie).delete()
    db.session.commit()

@app.route('/')
def get_initial_page():
    if isLoggedIn(request):
        response_file = open('HTML_pages/Redirect_Main.html')
        return response_file.read()
    response_file = open('HTML_pages/Login_Main.html')
    return response_file.read()

# @app.route('/')
# def get_initial_page():
#     if isLoggedIn(request):
#         return flask.send_from_directory(directory='HTML_pages', filename='Redirect_Main.html', cache_timeout=1)
#     return flask.send_from_directory(directory='HTML_pages', filename='Login_Main.html', cache_timeout=1)

@app.route('/check_database')
def get_all_data():
    all_logins = User.query.all()
    return jsonify([e.serialize() for e in all_logins])

@app.route('/Main')
def get_Main_page():
    #print('logged_in_cookie' in request.cookies.keys())
    if not isLoggedIn(request):
        response_file = open('HTML_pages/Redirect_Home.html')
        return response_file.read()
    response_file = open('HTML_pages/Main.html')
    return response_file.read()
    # if 'logged_in_cookie' not in request.cookies.keys():
    #     return flask.send_from_directory(directory='HTML_pages', filename='Redirect_Home.html')
    # user_cookie = request.cookies.get('logged_in_cookie')
    # return user_cookie

@app.route('/Search', methods=['POST'])
def run_search():
    searched_data_dict = {}
    return ''


@app.route('/Login-Data', methods=['POST'])
def handle_login():
    session = requests.Session()
    username = request.form['Username']
    password = request.form['Password']

    login_result = initiate_login(session, username, password)
    while login_result == Login_Error.TIME_OUT:
        login_result = initiate_login(session, username, password)
    if login_result == Login_Error.INVALID:
        return '{"Logged_in" : false}'
    del password
    name = get_name_from_parser(BeautifulSoup(login_result, 'html.parser'))
    # name = ''
    # if username != 'FRC374':
    #     return '{"Logged_in" : false}'
    # name = 'William Andersen'
    # print(name)

    response_json = {}
    response_json['Logged_in'] = True
    response_json['Cookie'] = getRandomLetters()
    response_json['Name'] = name

    remove_outdated(username)
    new_login = User(response_json['Cookie'], username, session, name, datetime.datetime.now())
    db.session.add(new_login)
    db.session.commit()

    json_data = json.dumps(response_json)
    return json_data

# @app.after_request
# def add_header(r):
#     """
#     Add headers to both force latest IE rendering engine or Chrome Frame,
#     and also to cache the rendered page for 10 minutes.
#     """
#     r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
#     r.headers["Pragma"] = "no-cache"
#     r.headers["Expires"] = "0"
#     r.headers['Cache-Control'] = 'public, max-age=0'
#     return r

if __name__ == '__main__':
    app.run(port=80, debug=True)