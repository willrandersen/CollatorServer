import xlwt
from xlwt import Workbook
import pandas as pd
import datetime
from threading import Thread
import requests
from bs4 import BeautifulSoup
import lxml.html
from Task_Queue import *

def format_string(input_string):
    current_len = len(input_string)
    x = 0
    while x < current_len:
        if ord(input_string[x]) <= 32:
            y = x
            while y < len(input_string) and ord(input_string[y]) <= 32:
                y += 1
            if y - x >= 5:
                input_string = input_string[:x] + input_string[y:]
                current_len = len(input_string)
        x+=1
    output_str = ""
    for letter in input_string:
        if ord(letter) < 32:
            output_str += ' '
        else:
            output_str += letter
    return output_str.strip()


def GetCustomerNumber(SC, session):
    MOL_url_POST_Order_Status = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/order_status_detail.asp'
    load_detail_params = {'OSRpage': 'yes', 'OrderKey': SC, 'System': 'COF', 'CustEnterpriseId' : ''}
    order_status_request = session.post(MOL_url_POST_Order_Status, params=load_detail_params)

    order_status_html = order_status_request.text
    order_status_html = order_status_html.replace("<FONT>", "")
    order_status_html = order_status_html.replace("</FONT>", "")

    order_status_parser = BeautifulSoup(order_status_html, 'html.parser')
    tables = order_status_parser.find_all('table', border='0', width='90%')
    top_data_table = tables[1]
    second_row = top_data_table.find_all('tr')[1]
    second_element_html = second_row.find_all('td')[1]

    customer_number = format_string(second_element_html.get_text())
    return customer_number


def GetConfirmationNums(cust_num, session):
    MOL_url_POST_Search = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/order_search_results.asp'

    page = 1
    current_time = datetime.datetime.today()
    fromYear = current_time.year - 3
    fromDate = str(current_time.month) + '/' + str(current_time.day) + '/' + str(fromYear)
    table_empty = False
    found_SCs = []
    while not table_empty:
        table_empty = True
        search_params = {'TypeOfOrder': '', 'Cust': cust_num, 'CustType': 'CustomerNumber',
                         'EntName': cust_num, 'Search': '',
                         'SearchType': '', 'RadioIndex': '1', 'FromDate': fromDate,
                         'ToDate': current_time.strftime('%d/%m/%Y'), 'DateType': 'PODATE',
                         'Address': 'ALL', 'ordstatus': 'ALL', 'SortField': 'CUST_PO_DT', 'SortDirection': 'DESC',
                         'Page': page}
        search_customer_number_request = session.get(MOL_url_POST_Search, params=search_params)
        customer_search_parser = BeautifulSoup(search_customer_number_request.text, 'html.parser')
        # print(customer_search_parser.prettify())
        layers = customer_search_parser.find_all('table', class_='cssTABLE')[0].find_all('tr')  # 5,6
        for each_val in layers:
            color = each_val.get('bgcolor')
            if color == '#d1d1d1' or color == '#FFFFFF':
                table_empty = False
                element_list = (each_val.find_all('td'))
                if element_list[0].get('class') == ['Arial8pt']:
                    current_order_number = element_list[2].get_text()
                    current_SC = element_list[6].get_text()
                    if 'ONELINER' in current_order_number:
                        continue
                    found_SCs.append(current_SC)
        page += 1
    return found_SCs


def GetProjectName(SC, session):
    MOL_url_POST_Report = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/list_header.asp'
    payload = {'lb_search_action': 'LISTIN', 'titleList': '', 'lb_search_number': 'LISTID', 'lb_search_Type': 'LISTID',
               'tb_searchValue': '', 'tb_LineItem': '', 'tb_searchnumber': SC, 'lb_list_tracking': 'LISTHEADER',
               'lb_list_tracking1': '', 'lb_list_tracking2': '', 'lb_list_tracking3': '',
               'lb_list_tracking_temp': 'LISTHEADER',
               'tbdtAsOfDate': '', 'btn_search': 'Search'}
    header_request = session.post(MOL_url_POST_Report, data=payload)
    header_parser = BeautifulSoup(header_request.text, 'html.parser')
    header_table = header_parser.find_all('table', class_="CssTable", border="0", cellpadding="2", cellspacing="0", width="100%")[1]
    header_input_row = header_table.find_all('tr', bgcolor='#FFFFFF')[0]
    project_name_html = header_input_row.find_all('td')[6]
    return format_string(project_name_html.get_text())

def GetNameThread(SC, session, list, index):
    try:
        this_SC_name = GetProjectName(SC, session)
        list[index] = this_SC_name.upper(), SC
    except IndexError:
        list[index] = '', SC

def GetProjectSCs(project_name, possible_SCs, session, original_SC=''):
    SC_project_names = [''] * len(possible_SCs)
    threads = []
    count = 0
    for each_SC in possible_SCs:
        if each_SC == original_SC:
            SC_project_names[count] = '', ''
            count += 1
            continue
        process = Task(target=GetNameThread, args=[each_SC, session, SC_project_names, count])
        threads.append(process)
        count += 1

    full_run(threads,8)

    same_project_SCs = []
    count = -1
    for each_result, each_SC in SC_project_names:
        count+=1
        if each_result.strip().upper() == project_name.strip().upper():
            same_project_SCs.append(each_SC)
    return same_project_SCs
