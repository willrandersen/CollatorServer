from celery import Celery, states
from celery.exceptions import Ignore
from bs4 import BeautifulSoup
import requests
from Networking_Utils import *
from Additional_methods import GetProjectSCs, GetProjectName, GetConfirmationNums, GetCustomerNumber
from Parsing_Errors import NoValidInputs,DatapointNotFound
import psutil
import time
import gc
from Task_Queue import Task, full_run
from multithreaded_status import *

SHIPPING_THREAD_MAX = 26
STATUS_REQUEST_THREADS = 14

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
        try:
            if not each_table_row['Has Serial Codes']:
                each_table_row['Serial Codes'] = '(No serial numbers available)'
                each_table_row['Tracking Information'] = "-"
                list_count += 1
                continue
            if 'Tracking Information' in each_table_row.keys() and each_table_row['Tracking Information'] != '':
                each_table_row['Serial Codes'] = '(No serial numbers available)'
                list_count += 1
                continue
            line_item = each_table_row['Line Item']
            process = Task(target=shipping_thread, args=[session, SC, line_item, results, list_count])
            threads.append(process)
            list_count += 1
        except RuntimeError as e:
            print('Threading Error: shipping data')
            print(len(threads))
            raise e
    full_run(threads, SHIPPING_THREAD_MAX)
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

def sort_by_serial(rows):
    last_serial_item = 0
    for index in range(len(rows)):
        current_item = rows[index]
        if current_item['Serial Codes'] != '(No serial numbers available)':
            rows.remove(current_item)
            rows.insert(last_serial_item, current_item)
            last_serial_item += 1


def sort_by_tracking(rows):
    last_full_data_item = 0
    last_partial_data_item = 0
    for index in range(len(rows)):
        current_item = rows[index]
        tracking_info = current_item['Tracking Information'].split('-')
        if tracking_info[0] == '' and tracking_info[1] == '':
            continue
        if tracking_info[1] == '(No tracking number available)':
            rows.remove(current_item)
            rows.insert(last_partial_data_item, current_item)
            last_partial_data_item += 1
        else:
            rows.remove(current_item)
            rows.insert(last_full_data_item, current_item)
            last_partial_data_item += 1
            last_full_data_item += 1


def sort_by_unshipped(rows):
    last_unshipped_item = 0
    for index in range(len(rows)):
        current_item = rows[index]
        if int(current_item['Qty. Open']) > 0:
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

def isProjectOrder(input):
    return ':' in input


cel = Celery()
cel.config_from_object('celery_settings')


# @cel.task()
# def do_table_parsing(request_dict, session):
#     data_dict = {}
#     for each_input in request_dict.keys():
#         inputIsFo = isFO(each_input)
#         SC = None
#         if inputIsFo:
#             FO_Info = MOL_Search_FO(session, each_input)
#             SC = FO_Info['Confirmation Number']
#             if not request_dict[each_input]:
#                 data_dict[each_input] = FO_Info
#         else:
#             SC = each_input
#             if not request_dict[each_input]:
#                 data_dict[each_input] = False
#         if request_dict[each_input]:
#             Additional_SCs = GetCustomerNumber(SC, session)
#             for each_SC in Additional_SCs:
#                 data_dict[each_SC] = False
#
#     rows_to_print = []
#     MOL_header = None
#     print('progress_1')
#     for each_requested_data in data_dict.keys():
#         if type(data_dict[each_requested_data]) == type({}):  # Is an FO
#             Confirm_Number = data_dict[each_requested_data]['Confirmation Number']
#             print('progress_2')
#             MOL_header, MOL_table = MOL_Order_Status(session, Confirm_Number, each_requested_data)
#             print('progress_3')
#             #DS_table = getDSDict(each_requested_data)
#             #merge_MOL_DS(DS_table, MOL_table, MOL_header)
#             print('progress_4')
#             add_shipping_data(MOL_table, MOL_header, Confirm_Number, session)
#             rows_to_print.extend(MOL_table)
#         else:
#             MOL_header, MOL_table = MOL_Order_Status(session, each_requested_data)
#             #DS_table = getDSDict_from_SC(each_requested_data)
#             #merge_MOL_DS(DS_table, MOL_table, MOL_header)
#             add_shipping_data(MOL_table, MOL_header, each_requested_data, session)
#             rows_to_print.extend(MOL_table)
#
#     output_table = [[""] * len(MOL_header) for i in range(len(rows_to_print))]
#
#     sort_table(rows_to_print)
#
#     for each_row_value in range(len(rows_to_print)):
#         for each_col_value in range(len(MOL_header)):
#             output_table[each_row_value][each_col_value] = rows_to_print[each_row_value][MOL_header[each_col_value]]
#     return output_table, MOL_header

def multithreaded_project_order_status(session, sc, list, index):
    head, table = MOL_Order_Status(session, sc)
    list[index] = head, table, sc



@cel.task(bind = True)
def do_table_parsing(self, request_dict, session, sort_method):
    print(SHIPPING_THREAD_MAX)
    gc.collect()
    self.update_state(state='RUNNING')
    rows_to_print = []
    MOL_header = None
    start_time = time.time()
    search_meta_data = {}
    count = 0
    length_of_dict = len(request_dict)
    #print(psutil.virtual_memory())
    for each_input in request_dict.keys():
        each_data_point_meta_data = []
        self.update_state(state='RUNNING', meta={'done': count, 'total': length_of_dict})
        count += 1
        try:
            if isProjectOrder(each_input):
                item_data = each_input.split(':')
                each_data_point_meta_data.append('proj_search')

                cust_num = item_data[0].strip()
                proj_name = item_data[1].strip()

                possible_other_SCs = GetConfirmationNums(cust_num, session)
                project_SCs = GetProjectSCs(proj_name, possible_other_SCs, session)

                each_data_point_meta_data.extend(project_SCs)
                search_meta_data[each_input] = each_data_point_meta_data
                #print(time.time() - start_time)
                # for each_proj_SC in project_SCs:
                #     MOL_header, MOL_table = MOL_Order_Status(session, each_proj_SC)
                #     add_shipping_data(MOL_table, MOL_header, each_proj_SC, session)
                #     rows_to_print.extend(MOL_table)
                # threads = []
                # index = 0
                # table_outputs = [''] * len(project_SCs)
                # for each_proj_SC in project_SCs:
                #     process = Thread(target=multithreaded_project_order_status, args=[session, each_proj_SC, table_outputs, index])
                #     process.start()
                #     threads.append(process)
                #     index += 1
                # for each_thread in threads:
                #     each_thread.join()
                table_outputs = get_order_details(project_SCs, session, STATUS_REQUEST_THREADS)
                print(time.time() - start_time)
                for head, table, SC in table_outputs:
                    MOL_header = head
                    MOL_table = table
                    add_shipping_data(MOL_table, MOL_header, SC, session)
                    rows_to_print.extend(MOL_table)
                print(time.time() - start_time)
                continue
            FO = ""
            SC = None
            MOL_table = None
            if isFO(each_input):
                each_data_point_meta_data.append("single_fo_search")
                FO = each_input
                FO_Info = MOL_Search_FO(session, each_input)
                SC = FO_Info['Confirmation Number']

                if request_dict[each_input]:
                    if FO.startswith('4808'):
                        request_dict[each_input] = False
                        each_data_point_meta_data[0] = "fo_risk_proj_search"
                    MOL_header, MOL_table = MOL_Order_Status(session, SC)
                else:
                    MOL_header, MOL_table = MOL_Order_Status(session, SC, FO)
                each_data_point_meta_data.append(SC)
            else:
                each_data_point_meta_data.append("single_listid_search")
                SC = each_input
                table_outputs = get_order_details([SC], session, STATUS_REQUEST_THREADS)
                MOL_header, MOL_table, SC = table_outputs[0]
                for each_row in MOL_table:
                    #print(each_row)
                    if each_row['Order number'].startswith('4808'):
                        request_dict[each_input] = False
                        each_data_point_meta_data[0] = "sc_risk_proj_search"
                        break
            add_shipping_data(MOL_table, MOL_header, SC, session)
            rows_to_print.extend(MOL_table)
            if request_dict[each_input]:
                each_data_point_meta_data[0] = "advanced_proj_search"

                cust_num = GetCustomerNumber(SC, session)
                possible_other_SCs = GetConfirmationNums(cust_num, session)

                proj_name = GetProjectName(SC, session)

                project_SCs = GetProjectSCs(proj_name, possible_other_SCs, session, SC)

                each_data_point_meta_data.extend(project_SCs)
                each_data_point_meta_data.append(proj_name)
                each_data_point_meta_data.append(cust_num)

                table_outputs = get_order_details(project_SCs, session, STATUS_REQUEST_THREADS)
                for head, table, SC in table_outputs:
                    MOL_header = head
                    MOL_table = table
                    add_shipping_data(MOL_table, MOL_header, SC, session)
                    rows_to_print.extend(MOL_table)
                # for each_proj_SC in project_SCs:
                #     MOL_header, MOL_table = MOL_Order_Status(session, each_proj_SC)
                #     add_shipping_data(MOL_table, MOL_header, each_proj_SC, session)
                #     rows_to_print.extend(MOL_table)
            search_meta_data[each_input] = each_data_point_meta_data
        except (DatapointNotFound, IndexError):
            if isProjectOrder(each_input) or request_dict[each_input]:
                each_data_point_meta_data[0] = "No_Data_Found_Proj"
            else:
                each_data_point_meta_data[0] = "No_Data_Found"
            search_meta_data[each_input] = each_data_point_meta_data

    if MOL_header is None:
        self.update_state(
            state=states.FAILURE,
            meta={
                'exc_type': 'Invalid_Search',
                'exc_message': 'No search was able to pull data',
            })
        raise Ignore()

    output_table = [[""] * len(MOL_header) for i in range(len(rows_to_print))]

    if sort_method == '1':
        sort_by_unshipped(rows_to_print)
    elif sort_method == '2':
        sort_by_serial(rows_to_print)
    elif sort_method == '3':
        sort_by_tracking(rows_to_print)
    else:
        pass    # automatically sorted in FOs

    for each_row_value in range(len(rows_to_print)):
        for each_col_value in range(len(MOL_header)):
            output_table[each_row_value][each_col_value] = rows_to_print[each_row_value][MOL_header[each_col_value]]
    print(psutil.virtual_memory())
    del rows_to_print
    print(psutil.virtual_memory())
    return output_table, MOL_header, search_meta_data