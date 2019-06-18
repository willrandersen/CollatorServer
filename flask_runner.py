from flask import Flask, request, Response
from enum import Enum
import requests
from random import randint
import flask
import lxml.html
from bs4 import BeautifulSoup
import json
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from flask_heroku import Heroku


app = Flask(__name__)

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

@app.route('/')
def get_initial_page():
    return flask.send_from_directory(directory='HTML_pages', filename='Login_Main.html')



@app.route('/Main')
def get_Main_page():
    return flask.send_from_directory(directory='HTML_pages', filename='Redirect_Home.html')


@app.route('/Login-Data', methods=['POST'])
def handle_login():
    with requests.Session() as session:
        username = request.form['Username']
        password = request.form['Password']

        login_result = initiate_login(session, username, password)
        while login_result == Login_Error.TIME_OUT:
            login_result = initiate_login(session, username, password)
        if login_result == Login_Error.INVALID:
            return '{"Logged_in" : false}'
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
        json_data = json.dumps(response_json)
        return json_data

if __name__ == '__main__':
    app.run(port=80, debug=True)