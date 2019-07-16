from enum import Enum
import requests
from random import randint
import lxml.html
from bs4 import BeautifulSoup
import json
import flask
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_heroku import Heroku
import datetime
from Parsing_Task import cel, do_table_parsing
from celery.result import AsyncResult
import pandas as pd
import flask_excel as excel
import time


MAX_TABLE_SIZE = 15

app = Flask(__name__)
excel.init_excel(app)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
#app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Locomotives12moby!@localhost:5432/user_data'
heroku = Heroku(app)
db = SQLAlchemy(app)


class User(db.Model):
    __tablename__ = "user_pickled_cookie_data"
    id = db.Column(db.Integer, primary_key=True)
    cookie = db.Column(db.String(60), unique=True)
    user_name = db.Column(db.String(20))
    session = db.Column(db.PickleType)
    name = db.Column(db.String)
    last_login = db.Column(db.DateTime)

    def __init__(self, cookie, username, session, name, time):
        self.cookie = cookie
        self.user_name = username
        self.session = session
        self.name = name
        self.last_login = time

    def __repr__(self):
        return str({'id' : self.id, 'user_name' : self.user_name, 'cookie' : self.cookie, 'name' : self.name, 'login' : self.last_login})

    def serialize(self):
        return {'id' : self.id, 'user_name' : self.user_name, 'cookie' : self.cookie, 'session' : "Session_object", 'name' : self.name, 'login' : self.last_login}


class Search(db.Model):
    __tablename__ = "recent_searches"
    id = db.Column(db.Integer, primary_key=True)
    user_name = db.Column(db.String(20))
    search_completed = db.Column(db.DateTime)
    search_started = db.Column(db.DateTime)
    table_data = db.Column(db.PickleType)
    task_id = db.Column(db.String())
    status = db.Column(db.String())
    items_searched = db.Column(db.PickleType)


    def __init__(self, user_name, task_id, search_dict):
        self.items_searched = search_dict
        self.user_name = user_name
        self.table_data = None
        self.search_started = datetime.datetime.now(datetime.timezone.utc)
        self.task_id = task_id
        self.status = 'Incomplete'
        self.search_completed = None

    def __repr__(self):
        return str({'id' : self.id, 'user_name' : self.user_name, 'search_completed_time' : self.search_completed, 'task_id' : self.task_id})

    def serialize(self):
        return {'id' : self.id, 'user_name' : self.user_name, 'search_completed_time' : self.search_completed, 'task_id' : self.task_id, "items_searched" : self.items_searched}

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
            JSlogin_name = JSlogin_name[:JSlogin_name.index(";") - 1]
            return JSlogin_name

def getRandomLetters(length=60):
    output_string = ''
    sample = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'
    for index in range(0, length):
        index = randint(0, len(sample) - 1)
        output_string += sample[index]
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

def get_detailed_search_info_html(dict):
    string_builder = '<h3>Search Meta Data:</h3>'
    for each_entry in dict.keys():
        if dict[each_entry][0] == 'No_Data_Found_Proj':
            string_builder += 'No project data found for ' + each_entry
        if dict[each_entry][0] == 'No_Data_Found':
            string_builder += 'No data found for ' + each_entry
        if dict[each_entry][0] == 'single_fo_search':
            string_builder += 'Singe FO search on ' + each_entry + " from List ID " + dict[each_entry][1]
        if dict[each_entry][0] == 'single_listid_search':
            string_builder += 'Single List ID search on ' + each_entry
        if dict[each_entry][0] == 'advanced_proj_search':
            string_builder += "Project search on <b>" + each_entry + "</b>: SCs on project: "
            for each_other_SC in dict[each_entry][1:-2]:
                string_builder += each_other_SC + ', '
            string_builder = string_builder[:-2]
            string_builder += '<p class="subdata">Customer Number: ' + dict[each_entry][-1] + '</p>'
            string_builder += '<p class="subdata">Project Name: ' + dict[each_entry][-2] + '</p>'
        if dict[each_entry][0] == 'proj_search':
            string_builder += "Project search on <b>" + each_entry + "</b>: SCs on project: "
            for each_other_SC in dict[each_entry][1:]:
                string_builder += each_other_SC + ', '
            string_builder = string_builder[:-2]
        string_builder += '<br>'
    return string_builder


def get_bolded_dict_string(dict, status):
    string_builder = ''
    for each_entry in dict.keys():
        if status == 'FAILURE':
            if dict[each_entry]:
                string_builder += "<i><b>" + each_entry + "</b></i>"
            else:
                string_builder += "<i>" + each_entry + "</i>"
        elif type(dict[each_entry]) == type([]) and 'No_Data_Found_Proj' == dict[each_entry][0]:
            string_builder += "<i><b>" + each_entry + "</b></i>"
        elif type(dict[each_entry]) == type([]) and 'No_Data_Found' == dict[each_entry][0]:
            string_builder += "<i>" + each_entry + "</i>"
        elif (type(dict[each_entry]) == type([]) and 'single' not in dict[each_entry][0]) or (dict[each_entry] and type(dict[each_entry]) != type([])):
            string_builder += "<b>" + each_entry + "</b>"
        else:
            string_builder += each_entry
        string_builder += ', '
    return string_builder[:-2]


def build_recent_table(username):
    #start_recent_table = time.time()
    recent_searches = Search.query.filter_by(user_name=username).order_by(Search.search_started).all()
    #print('table build time: ' + str(time.time() - start_recent_table))
    after_database = time.time()
    if len(recent_searches) == 0:
        return '<tr>No Recent Searches</tr>'
    table_html = '<tr>'
    time_delt = datetime.timedelta(hours=5)
    #print('table build time: ' + str(time.time() - after_database))
    for each_search in recent_searches[::-1]:
        table_html += "\n<tr>"
        table_html += "<td>" + (each_search.search_started - time_delt).strftime("%b %d %Y %H:%M:%S") + " CDT </td>"
        table_html += "<td>" + each_search.task_id + "</td>"
        table_html += "<td>" + each_search.status + "</td>"
        table_html += "<td>" + get_bolded_dict_string(each_search.items_searched, each_search.status) + "</td>"
        #table_html += "<td>" + "" + "</td>"
        #table_html += "<td>" + "Link" + "</td>"
        if str(each_search.status) == 'SUCCESS':
            table_html += '<td> <a href="/load_search/' + each_search.task_id + '">Link</a> </td>'
        else:
            table_html += "<td>" + "Unavailable" + "</td>"
        table_html += "</tr>"
    #print('table build time: ' + str(time.time() - after_database))
    return table_html + "\n"


def update_unresolved_searches(username):
    #start_recent_table = time.time()
    recent_searches = Search.query.filter_by(user_name=username).all()
    #print('table update time: ' + str(time.time() - start_recent_table))
    for each_search in recent_searches:
        task_id = each_search.task_id
        #time_since_search = datetime.datetime.now() - each_search.search_started
        #duration_seconds = time_since_search.total_seconds()
        # if duration_seconds > 60 * 60 * 24 * 7:
        #     Search.query.filter_by(task_id=task_id).delete()
        #     continue
        if each_search.status != 'SUCCESS' and each_search.status != 'FAILURE':
            res = AsyncResult(task_id, app=cel)
            each_search.status = str(res.state)
            if each_search.status == 'SUCCESS':
                output_table, header, metadata = res.get()
                each_search.items_searched = metadata
                each_search.search_completed = datetime.datetime.now(datetime.timezone.utc)
                each_search.table_data = (output_table, header)
                res.forget()
            if each_search.status == 'FAILURE':
                each_search.search_completed = datetime.datetime.now(datetime.timezone.utc)
                res.forget()
    #start_recent_table = time.time()
    db.session.commit()
    #print('table commit time: ' + str(time.time() - start_recent_table))


@app.route('/about', methods=['GET'])
def send_about():
    if isLoggedIn(request):
        response_file = open('HTML_pages/Redirect_Main.html')
        return response_file.read()
    else:
        response_file = open('HTML_pages/Instructions_page_logged_out.html')
    return response_file.read()

@app.route('/logout', methods=['DELETE'])
def logout_data():
    if not isLoggedIn(request):
        return 'Not Logged In', 203
    requested_with_cookie = request.cookies.get('logged_in_cookie')
    user_searched = User.query.filter_by(cookie=requested_with_cookie).delete()
    db.session.commit()
    return 'Logged Out', 200


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

@app.route('/check_searches')
def get_all_search_data():
    all_logins = Search.query.all()
    return jsonify([e.serialize() for e in all_logins])

@app.route('/Main')
def get_main_page():
    #start_time = time.time()
    if not isLoggedIn(request):
        response_file = open('HTML_pages/Redirect_Home.html')
        return response_file.read()
    response_file = open('HTML_pages/Main_Page.html')
    template = response_file.read()
    #print(time.time() - start_time)
    #response_file.close()
    requested_with_cookie = request.cookies.get('logged_in_cookie')
    user_searched = User.query.filter_by(cookie=requested_with_cookie).first()
    #print(time.time() - start_time)
    update_unresolved_searches(user_searched.user_name)
    #print(time.time() - start_time)
    template = template.format(user_searched.name, build_recent_table(user_searched.user_name))
    #print(time.time() - start_time)
    return template

@app.route('/Run-Search')
def get_search_page():
    #print('logged_in_cookie' in request.cookies.keys())
    if not isLoggedIn(request):
        response_file = open('HTML_pages/Redirect_Home.html')
        return response_file.read()
    response_file = open('HTML_pages/Run_Search.html')
    return response_file.read()
    # if 'logged_in_cookie' not in request.cookies.keys():
    #     return flask.send_from_directory(directory='HTML_pages', filename='Redirect_Home.html')
    # user_cookie = request.cookies.get('logged_in_cookie')
    # return user_cookie

@app.route('/Search', methods=['POST'])
def run_search():
    if not isLoggedIn(request):
        return '{"Logged_in" : false}', 401
    searched_data_dict = {}
    print('Search status 1')
    count = 0
    while count < 16:
        if 'search_' + str(count) in request.form.keys():
            datapoint = request.form['search_' + str(count)].strip()
            if datapoint == '':
                count += 1
                continue
            company_search = request.form['check_' + str(count)] in ['True', 'true']
            searched_data_dict[datapoint] = company_search
            count += 1
        else:
            break
    if len(searched_data_dict) == 0:
        return 'Invalid Response', 400
    requested_with_cookie = request.cookies.get('logged_in_cookie')
    user_searched = User.query.filter_by(cookie=requested_with_cookie).first()

    sort_method = request.form['sort_val']

    async_req = do_table_parsing.delay(searched_data_dict, user_searched.session, sort_method)

    print('Search status 2')

    submitted_task = Search(user_searched.user_name, async_req.id, searched_data_dict)
    db.session.add(submitted_task)

    recent_searches = Search.query.filter_by(user_name=user_searched.user_name).order_by(Search.search_started).all()
    if len(recent_searches) > MAX_TABLE_SIZE:
        Search.query.filter_by(task_id=recent_searches[0].task_id).delete()
    db.session.commit()
    return async_req.id, 202

@app.route('/status_check/<task_id>')
def check_status(task_id):
    if not isLoggedIn(request):
        return '{"status" : "LOGGED_OUT"}', 401  # change to 401

    requested_with_cookie = request.cookies.get('logged_in_cookie')
    user_object = User.query.filter_by(cookie=requested_with_cookie).first()

    search_object = Search.query.filter_by(task_id=task_id).first()

    if search_object is None:
        return 'Invalid Request', 404

    if user_object.user_name != search_object.user_name:
        return 'Forbidden', 403

    if search_object.status == 'SUCCESS':
        output_table, header = search_object.table_data
        metadata = search_object.items_searched

        pd.set_option('display.max_colwidth', -1)
        df = pd.DataFrame(output_table)
        df.columns = header
        return get_detailed_search_info_html(metadata) + '<br><br>' + df.to_html(index=False, justify='center')
    if search_object.status == 'FAILURE':
        return '{"status" : "FAILURE"}'


    res = AsyncResult(task_id, app=cel)
    #print(res.info)
    search_object.status = str(res.state)
    info = res.info
    if search_object.status == 'RUNNING':
        db.session.commit()
        return '{"status" : "RUNNING", "progress" : ' + str(info['done']) + ', "data_points": ' + str(info['total']) + '}'

    if search_object.status == 'FAILURE':
        search_object.search_completed = datetime.datetime.now(datetime.timezone.utc)
        res.forget()
        db.session.commit()
        return '{"status" : "FAILURE"}'

    if search_object.status == 'SUCCESS':
        output_table, header, metadata = res.get()
        search_object.items_searched = metadata

        search_object.search_completed = datetime.datetime.now(datetime.timezone.utc)
        search_object.table_data = (output_table, header)
        db.session.commit()

        res.forget()
        print('Forgot' + task_id)
        pd.set_option('display.max_colwidth', -1)
        df = pd.DataFrame(output_table)
        df.columns = header
        return get_detailed_search_info_html(metadata) + '<br><br>' + df.to_html(index=False, justify='center')
    else:
        db.session.commit()
        return '{"status" : "' + str(res.state) + '"}'


@app.route('/load_search/<task_id>')
def show_past_search(task_id):
    if not isLoggedIn(request):
        response_file = open('HTML_pages/Redirect_Home.html')
        return response_file.read(), 401
    requested_with_cookie = request.cookies.get('logged_in_cookie')
    user_object = User.query.filter_by(cookie=requested_with_cookie).first()

    search_object = Search.query.filter_by(task_id=task_id).first()

    if search_object is None:
        return 'Invalid Request', 404

    #if user_object.user_name != search_object.user_name:
    #    return 'Forbidden'

    if search_object.status == 'FAILURE':
        return 'Failed Search'


    if search_object.status != 'SUCCESS':
        res = AsyncResult(task_id, app=cel)
        search_object.status = str(res.state)
        info = res.info
        if search_object.status == 'SUCCESS':
            output_table, header, metadata = res.get()
            search_object.items_searched = metadata
            search_object.search_completed = datetime.datetime.now(datetime.timezone.utc)
            search_object.table_data = (output_table, header)
            db.session.commit()
            res.forget()
        elif search_object.status == 'FAILURE':
            search_object.search_completed = datetime.datetime.now(datetime.timezone.utc)
            db.session.commit()
            res.forget()
        else:
            return '{"status" : "RUNNING", "progress" : ' + str(info['done']) + ', "data_points": ' + str(info['total']) + '}'
    table, header = search_object.table_data

    response_file = open('HTML_pages/load_search_template.html')
    template = response_file.read()

    pd.set_option('display.max_colwidth', -1)
    df = pd.DataFrame(table)
    df.columns = header
    table_html_string = df.to_html(index=False, justify='center')

    time_delt = datetime.timedelta(hours=5)

    response_html = template.format(task_id, search_object.user_name, (search_object.search_started - time_delt).strftime("%b %d %Y %H:%M:%S") + " CDT", get_detailed_search_info_html(search_object.items_searched),task_id,table_html_string)
    return response_html


@app.route('/download/<task_id>')
def send_loaded_file(task_id):
    if not isLoggedIn(request):
        response_file = open('HTML_pages/Redirect_Home.html')
        return response_file.read(), 401

    requested_with_cookie = request.cookies.get('logged_in_cookie')
    user_object = User.query.filter_by(cookie=requested_with_cookie).first()

    search_object = Search.query.filter_by(task_id=task_id).first()

    if search_object is None:
        return 'Invalid Request'

    # if user_object.user_name != search_object.user_name:
    #     return 'Forbidden', 403

    if search_object.status != 'SUCCESS':
        return 'File Unready'

    table, header = search_object.table_data
    table.insert(0, header)
    return excel.make_response_from_array(table, "xlsx", file_name="Collated-Data")


@app.route('/Login-Data', methods=['POST'])
def handle_login():
    session = requests.Session()
    username = request.form['Username']
    password = request.form['Password']

    login_result = initiate_login(session, username, password)
    while login_result == Login_Error.TIME_OUT:
        login_result = initiate_login(session, username, password)
    if login_result == Login_Error.INVALID:
        return '{"Logged_in" : false}', 401
    name = get_name_from_parser(BeautifulSoup(login_result, 'html.parser'))
    if name is None:
        return '{"Logged_in" : false}', 401
    del password
    # name = ''
    # if username != 'FRC374':
    #     return '{"Logged_in" : false}'
    # name = 'William Andersen'
    # print(name)

    response_json = {}
    response_json['Logged_in'] = True
    response_json['Cookie'] = getRandomLetters()
    response_json['Name'] = name

    remove_outdated(username.upper())
    new_login = User(response_json['Cookie'], username.upper(), session, name, datetime.datetime.now())
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