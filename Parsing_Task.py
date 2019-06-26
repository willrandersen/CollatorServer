from celery import Celery
from bs4 import BeautifulSoup
import requests
from threading import Thread
from Networking_Utils import *

def merge_MOL_DS(DS_table, MOL_table, MOL_header):
    MOL_header.append('Internal Comments (DS Items)')
    MOL_header.append('Buyer Name')
    if 'Tracking Information' not in MOL_header:
        MOL_header.append('Tracking Information')

    for each_DS_row in DS_table:
        DS_line_value = int(each_DS_row['LINE ITEM NUM'])
        for each_MOL_row in MOL_table:
            MOL_line_value = int(each_MOL_row['Line Item'])
            if DS_line_value == MOL_line_value:
                each_MOL_row['Description'] = each_DS_row['PART NUM AND DESCRIPTION']
                each_MOL_row['Plant'] = each_DS_row['SUPPLIER']
                each_MOL_row['Internal Comments (DS Items)'] = format_string(each_DS_row['INTERNAL COMMENTS'].strip())
                each_MOL_row['Buyer Name'] = each_DS_row['BUYER NAME']
                if 'PROMISE DATE' in each_DS_row.keys():
                    each_MOL_row['Tracking Information'] = "Unshipped"
                    each_MOL_row['Last Act. Ship Date'] = 'Promise Date: ' + each_DS_row['PROMISE DATE']
                else:
                    each_MOL_row['Tracking Information'] = each_DS_row['TRACKING NBR']
                    each_MOL_row['Last Act. Ship Date'] = each_DS_row['SHIP DATE']
                break

    for each_MOL_row in MOL_table:
        if 'Tracking Information' not in each_MOL_row.keys():
            each_MOL_row['Tracking Information'] = ''
        if 'Internal Comments (DS Items)' not in each_MOL_row.keys():
            each_MOL_row['Internal Comments (DS Items)'] = ''
        if 'Buyer Name' not in each_MOL_row.keys():
            each_MOL_row['Buyer Name'] = ''

def shipping_thread(session, SC, line_item, list, index):
    shipping_carrier, shipping_num, serial_codes = MOL_Shipping_Data(session, SC, line_item)
    serial_code_string = ''
    for each_code in serial_codes:
        serial_code_string += each_code + '   '
    list[index] = serial_code_string.strip(), shipping_carrier + '-' + shipping_num

def add_shipping_data(data_table, header, SC, session):
    if 'Tracking Information' not in header:
        header.append('Tracking Information')
    header.append('Serial Codes')
    threads = []
    results = [''] * len(data_table)
    list_count = 0
    for each_table_row in data_table:
        if 'Tracking Information' in each_table_row.keys() and each_table_row['Tracking Information'] != '':
            each_table_row['Serial Codes'] = '(No serial numbers available)'
            list_count += 1
            continue
        line_item = each_table_row['Line Item']
        process = Thread(target=shipping_thread, args=[session, SC, line_item, results, list_count])
        process.start()
        threads.append(process)
        list_count += 1
    for each_p in threads:
        each_p.join()
    for row_index in range(len(results)):
        if results[row_index] == '':
            continue
        serial_codes, shipping_status = results[row_index]
        data_table[row_index]['Tracking Information'] = shipping_status
        data_table[row_index]['Serial Codes'] = serial_codes

def SC_DS_Thread(FO, list, index):
    list[index] = getDSDict(FO)

def getDSDict_from_SC(SC):
    DS_URL = 'http://gemssearch.mot-solutions.com/fodetail.asp'
    payload = {'mode': 'listgo', 'li': SC}
    with requests.Session() as session:
        r = session.get(DS_URL, data=payload)
    html_data = r.text
    html_data = html_data.replace("</div>", "")
    html_data = html_data.replace("<STRONG>", "")
    html_data = html_data.replace("</STRONG>", "")

    soup_parser = BeautifulSoup(html_data, 'html.parser')

    tables_list = soup_parser.find_all('table', class_='sortable')

    if len(tables_list) == 0:
        return {}

    SC_table_rows_html = tables_list[0].find_all('tr')
    #print(SC_table_rows_html)
    DS_data = [''] * (len(SC_table_rows_html) - 1)
    threads = []
    for each_row_index in range(1, len(SC_table_rows_html)):
        row_elements = SC_table_rows_html[each_row_index].find_all('td')
        FO = format_string(row_elements[0].get_text())
        process = Thread(target=SC_DS_Thread, args=[FO,DS_data, each_row_index - 1])
        process.start()
        threads.append(process)

    for each_p in threads:
        each_p.join()
    table = []
    for each_FO in DS_data:
        table.extend(each_FO)
    return table


def sort_table(rows):
    last_unshipped_item = 0
    for index in range(len(rows)):
        current_item = rows[index]
        if current_item['Hold Code'] == 'Booked' or current_item['Hold Code'] == '':
            rows.remove(current_item)
            rows.insert(last_unshipped_item, current_item)
            last_unshipped_item += 1

def isFO(input):
    if len(input) != 13:
        return False
    input = format_string(input)
    for each_letter in input:
        if each_letter not in '0123456789':
            return False
    return True

cel = Celery()
cel.config_from_object('celery_settings')



@cel.task()
def do_table_parsing(request_dict, session):
    data_dict = {}
    for each_input in request_dict.keys():
        inputIsFo = isFO(each_input)
        SC = None
        if inputIsFo:
            FO_Info = MOL_Search_FO(session, each_input)
            SC = FO_Info['Confirmation Number']
            if not request_dict[each_input]:
                data_dict[each_input] = FO_Info
        else:
            SC = each_input
            if not request_dict[each_input]:
                data_dict[each_input] = False
        if request_dict[each_input]:
            Additional_SCs = GetCustomerNumber(SC, session)
            for each_SC in Additional_SCs:
                data_dict[each_SC] = False

    rows_to_print = []
    MOL_header = None
    for each_requested_data in data_dict.keys():
        if type(data_dict[each_requested_data]) == type({}):  # Is an FO
            Confirm_Number = data_dict[each_requested_data]['Confirmation Number']
            MOL_header, MOL_table = MOL_Order_Status(session, Confirm_Number, each_requested_data)

            #DS_table = getDSDict(each_requested_data)
            #merge_MOL_DS(DS_table, MOL_table, MOL_header)

            add_shipping_data(MOL_table, MOL_header, Confirm_Number, session)
            rows_to_print.extend(MOL_table)
        else:
            MOL_header, MOL_table = MOL_Order_Status(session, each_requested_data)
            #DS_table = getDSDict_from_SC(each_requested_data)
            #merge_MOL_DS(DS_table, MOL_table, MOL_header)
            add_shipping_data(MOL_table, MOL_header, each_requested_data, session)
            rows_to_print.extend(MOL_table)

    output_table = [[""] * len(MOL_header) for i in range(len(rows_to_print))]

    sort_table(rows_to_print)

    for each_row_value in range(len(rows_to_print)):
        for each_col_value in range(len(MOL_header)):
            output_table[each_row_value][each_col_value] = rows_to_print[each_row_value][MOL_header[each_col_value]]
    return output_table, MOL_header