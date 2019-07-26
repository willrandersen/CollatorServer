from bs4 import BeautifulSoup
from Task_Queue import *
from Networking_Utils import format_string
import time
from Parsing_Errors import DatapointNotFound

def first_page_thread(session, SC, list, index, FO=""):
    MOL_url_POST_Order_Status = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/order_status_detail.asp'
    table_rows = []
    table_headers = []
    timer = time.time()

    customer_name = ''
    ship_to_address = ''
    order_entry_date = ''

    load_detail_params = {'OSRpage': 'yes', 'OrderKey': SC, 'System': 'COF', 'Page': '1',
                          'ShowOptionsForLIG': 'All',
                          'SortField': 'a.LIG_NB', 'SortDirection': 'ASC', 'Toggle': 'yes', 'FO': FO,
                          'searchquote': ''}
    order_status_request = session.post(MOL_url_POST_Order_Status, params=load_detail_params)
    time_request = time.time()
    order_status_html = order_status_request.text
    order_status_html = order_status_html.replace("<FONT>", "")
    order_status_html = order_status_html.replace("</FONT>", "")

    order_status_parser = BeautifulSoup(order_status_html, 'html.parser')
    main_table_html = order_status_parser.find_all('table', id='tblDetails')[0]

    pages_in_report = 1
    page_table_list = order_status_parser.find_all('table', class_='pagingControls')
    if len(page_table_list) > 0:
        page_list_string = page_table_list[0].get_text().strip()
        pages_in_report = int(page_list_string[10:])
    print(SC + ' : ' + str(pages_in_report))

    header_customer_html = order_status_parser.find_all('table', width="90%", border="0")[1]
    ship_to_address = format_string(header_customer_html.find_all('td', rowspan="3", valign="top")[1].get_text())
    customer_name = format_string(header_customer_html.find_all('td', align='left', valign='top')[1].get_text())

    header_table_html = order_status_parser.find_all('table', class_='cssTABLE')[0]  # , width="90%", border="0")[1]
    order_entry_date = format_string(header_table_html.find_all('td')[2].get_text())
    for x in main_table_html.find_all('th'):
        table_headers.append(x.get_text().strip())

    for each_row in main_table_html.find_all('tr', bgcolor='#FFFFFF'):
        row_data = {}
        html_element_list = each_row.find_all('td')
        for each_column in range(0, len(html_element_list)):
            row_data[table_headers[each_column]] = format_string(html_element_list[each_column].get_text().strip())
            if each_column == 12:
                row_data['Has Serial Codes'] = len(html_element_list[each_column].find_all('a')) == 1
        table_rows.append(row_data)
    list[index] = (table_headers, table_rows, customer_name, ship_to_address, order_entry_date, pages_in_report)
    print('Request took : ' + str(time_request - timer) + ', Parsing: ' + str(time.time() - time_request))


def later_page_thread(session, SC, header, page, list, index, FO=""):
    table_rows = []
    timer = time.time()
    MOL_url_POST_Order_Status = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/order_status_detail.asp'
    load_detail_params = {'OSRpage': 'yes', 'OrderKey': SC, 'System': 'COF', 'Page': page,
                              'ShowOptionsForLIG': 'All',
                              'SortField': 'a.LIG_NB', 'SortDirection': 'ASC', 'Toggle': 'yes', 'FO': FO,
                              'searchquote': ''}
    order_status_request = session.post(MOL_url_POST_Order_Status, params=load_detail_params)
    time_request = time.time()
    order_status_html = order_status_request.text
    order_status_html = order_status_html.replace("<FONT>", "")
    order_status_html = order_status_html.replace("</FONT>", "")

    order_status_parser = BeautifulSoup(order_status_html, 'html.parser')
    main_table_html = order_status_parser.find_all('table', id='tblDetails')[0]
    for each_row in main_table_html.find_all('tr', bgcolor='#FFFFFF'):
        row_data = {}
        html_element_list = each_row.find_all('td')
        for each_column in range(0, len(html_element_list)):
            row_data[header[each_column]] = format_string(html_element_list[each_column].get_text().strip())
            if each_column == 12:
                row_data['Has Serial Codes'] = len(html_element_list[each_column].find_all('a')) == 1
                # print(len(html_element_list[each_column].find_all('a')) == 1)
        table_rows.append(row_data)
    list[index] = table_rows
    print('Request took : ' + str(time_request - timer) + ', Parsing: ' + str(time.time() - time_request))


def get_order_details(list_IDs, session, threads):
    timer = time.time()
    initial_tasks = []
    result_list = [''] * len(list_IDs)
    index = 0
    for each_val in list_IDs:
        next_task = Task(target=first_page_thread, args=[session, each_val, result_list, index])
        initial_tasks.append(next_task)
        index += 1
    full_run(initial_tasks, threads)
    for each_element in result_list:
        if each_element == '':
            raise DatapointNotFound('Out of bounds')
    IDs_to_tab_lists = {}
    print('Got first pages in ' + str(time.time() - timer))
    later_pages_tasks = []
    for each_index in range(len(list_IDs)):
        SC = list_IDs[each_index]

        results = result_list[each_index]
        header = results[0]
        pages = int(results[5])

        IDs_to_tab_lists[SC] = [''] * pages
        IDs_to_tab_lists[SC][0] = results[1]
        for index in range(2, pages + 1):
            requested_task = Task(target=later_page_thread, args=[session, SC, header, index, IDs_to_tab_lists[SC], index - 1])
            later_pages_tasks.append(requested_task)
    full_run(later_pages_tasks, threads)
    output_list = []
    for each_SC_index in range(len(list_IDs)):
        SC = list_IDs[each_SC_index]
        initial_results = result_list[0]

        header = list(initial_results[0])
        cust_name = initial_results[2]
        ship_address = initial_results[3]
        order_date = initial_results[4]

        header.append('Customer Name')
        header.insert(9, 'Order Entry Date')
        header.insert(11, 'Shipping Address')

        list_rows = []
        for each_list in IDs_to_tab_lists[SC]:
            for each_row in each_list:
                each_row['Order Entry Date'] = order_date
                each_row['Shipping Address'] = ship_address
                each_row['Customer Name'] = cust_name
            list_rows.extend(each_list)
        output_list.append((header, list_rows, SC))
    return output_list
