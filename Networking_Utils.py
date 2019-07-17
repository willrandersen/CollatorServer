import requests
import lxml.html
from bs4 import BeautifulSoup
import datetime

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

def getDSDict(FO):
    DS_URL = 'http://gemssearch.mot-solutions.com/fodetail.asp'
    payload = {'mode': 'onefo', 'fo': FO}
    with requests.Session() as session:
        r = session.get(DS_URL, data=payload)

    html_data = r.text
    html_data = html_data.replace("</div>", "")
    html_data = html_data.replace("<STRONG>", "")
    html_data = html_data.replace("</STRONG>", "")

    soup_parser = BeautifulSoup(html_data, 'html.parser')

    tables_list = soup_parser.find_all('table', class_='sortable')

    if len(tables_list) < 2:
        return {}

    basic_info_table = tables_list[0]
    label_list = basic_info_table.find_all('th')
    data_list = basic_info_table.find_all('td')
    basic_detail_dictionary = {}
    for data_point in range(0, len(label_list)):
        basic_detail_dictionary[label_list[data_point].get_text().strip()] = data_list[data_point].get_text().strip()


    second_info_table = tables_list[1]
    shipping_header_html_list = second_info_table.find_all('th')
    shipping_data_html_list = second_info_table.find_all('td')
    second_header_list = []

    for each_label in shipping_header_html_list:
        second_header_list.append(format_string(each_label.get_text()))

    DS_row_list = []
    datapoint_html_iterator = iter(shipping_data_html_list)

    for current_y in range(0, int(len(shipping_data_html_list) / len(shipping_header_html_list))):
        current_dict = {}
        for current_x in range(0, len(shipping_header_html_list)):
            current_dict[second_header_list[current_x]] = format_string(datapoint_html_iterator.__next__().get_text().strip())
        DS_row_list.append(current_dict)

    if len(tables_list) == 3:
        third_info_table = tables_list[2]
        shipping_header_html_list = third_info_table.find_all('th')
        shipping_data_html_list = third_info_table.find_all('td')
        third_header_list = []

        for each_label in shipping_header_html_list:
            third_header_list.append(format_string(each_label.get_text()))

        datapoint_html_iterator = iter(shipping_data_html_list)

        for current_y in range(0, int(len(shipping_data_html_list) / len(shipping_header_html_list))):
            current_dict = {}
            for current_x in range(0, len(shipping_header_html_list)):
                current_dict[third_header_list[current_x]] = format_string(
                    datapoint_html_iterator.__next__().get_text().strip())
            DS_row_list.append(current_dict)

    return DS_row_list

def MOL_Search_FO(session, FO):
    MOL_url_POST_Search = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/order_search_results.asp?FromPage=OS'

    search_payload = {'hAction': '', 'bAddressFlag': 'False', 'bUltAddressFlag': 'False',
                      "bFlagToDisplayUltForMotDef": 'False', 'hUsePickList': '', 'hUsePickSSID': '',
                      'SearchTypeDisplay': '', 'SearchValueDisplay': '', 'TypeOfOrder': '',
                      'lb_search_type': 'CustomerNumber',
                      'tb_custvalue': '', 'lb_ship_to_address': 'ALL', 'lb_search_number': 'FONumber',
                      'tb_searchnumber': FO,
                      'lb_date_type': 'PODATE', 'radio1': '0', 'lb_search_day': 1092,
                      'lb_order_status': 'ALL', 'lb_order_type': 'A', 'btn_search': 'Search'
                      }
    search_request = session.post(MOL_url_POST_Search, data=search_payload)
    html_search_text = search_request.text

    initial_search_parser = BeautifulSoup(html_search_text, 'html.parser')
    search_css_table_list = initial_search_parser.find_all('table', class_='cssTABLE')

    html_search_headers = search_css_table_list[0].find_all('th')
    html_search_all_entries = search_css_table_list[0].find_all('td')
    html_search_datapoints = html_search_all_entries[len(html_search_all_entries) - len(html_search_headers):len(html_search_all_entries)]

    parsed_search_dict = {}
    for x in range(len(html_search_headers)):
        parsed_search_dict[html_search_headers[x].get_text().strip()] = format_string(html_search_datapoints[x].get_text().strip())

    return parsed_search_dict

def MOL_Order_Status(session, SC, FO=''):
    MOL_url_POST_Order_Status = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/order_status_detail.asp'
    table_rows = []
    table_headers = []
    page = 1
    customer_name = ''
    ship_to_address = ''
    order_entry_date = ''
    while True:
        load_detail_params = {'OSRpage': 'yes', 'OrderKey': SC, 'System': 'COF', 'Page': page,
                              'ShowOptionsForLIG': 'All',
                              'SortField': 'a.LIG_NB', 'SortDirection': 'ASC', 'Toggle': 'yes', 'FO': FO,
                              'searchquote': ''}
        order_status_request = session.post(MOL_url_POST_Order_Status, params=load_detail_params)
        order_status_html = order_status_request.text
        order_status_html = order_status_html.replace("<FONT>", "")
        order_status_html = order_status_html.replace("</FONT>", "")

        order_status_parser = BeautifulSoup(order_status_html, 'html.parser')
        main_table_html = order_status_parser.find_all('table', id='tblDetails')[0]

        if page == 1:
            header_customer_html = order_status_parser.find_all('table', width="90%", border="0")[1]
            ship_to_address = format_string(header_customer_html.find_all('td', rowspan="3", valign="top")[1].get_text())
            customer_name = format_string(header_customer_html.find_all('td', align='left', valign='top')[1].get_text())

            header_table_html = order_status_parser.find_all('table', class_='cssTABLE')[0]  # , width="90%", border="0")[1]
            order_entry_date = format_string(header_table_html.find_all('td')[2].get_text())
            for x in main_table_html.find_all('th'):
                table_headers.append(x.get_text().strip())

        if len(main_table_html.find_all('tr', bgcolor='#FFFFFF')) == 0:
            break

        for each_row in main_table_html.find_all('tr', bgcolor='#FFFFFF'):
            row_data = {}
            html_element_list = each_row.find_all('td')
            for each_column in range(0, len(html_element_list)):
                row_data[table_headers[each_column]] = format_string(html_element_list[each_column].get_text().strip())
                if each_column == 12:
                    print(html_element_list[each_column].find_all('a'))
            table_rows.append(row_data)
        page += 1

    for each_MOL_row in table_rows:
        each_MOL_row['Order Entry Date'] = order_entry_date
        each_MOL_row['Shipping Address'] = ship_to_address
        each_MOL_row['Customer Name'] = customer_name

    table_headers.append('Customer Name')
    table_headers.insert(9, 'Order Entry Date')
    table_headers.insert(11, 'Shipping Address')

    return table_headers, table_rows


def MOL_Shipping_Data(session, SC, Line_Item):
    MOL_url_Post_Shipping_Details = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/Shipping_Info.asp'
    load_shipping_params = {'OrderKey' : SC, 'LIG' : Line_Item, 'System' : 'COF'}
    shipping_request = session.post(MOL_url_Post_Shipping_Details, params= load_shipping_params)
    shipping_detail_parser = BeautifulSoup(shipping_request.text, 'html.parser')

    ID_code_table_html = shipping_detail_parser.find_all('table', id='Table5')[0]
    serial_codes = []
    for each_code_row in ID_code_table_html.find_all('tr', bgcolor="#FFFFFF"):
        serial_codes.append(each_code_row.find_all('td')[0].get_text().strip())

    shipping_table_html = shipping_detail_parser.find_all('table', class_="cssBASETABLE")[0]
    data_row_html = shipping_table_html.find_all('tr', bgcolor='#FFFFFF')[0]
    data_entry_html_list = data_row_html.find_all('td')
    if len(data_entry_html_list) == 1:
        return '','', serial_codes

    shipping_carrier = data_entry_html_list[4].get_text().strip()
    shipping_number = data_entry_html_list[5]
    number_string = ''
    for each_number in shipping_number.find_all('font'):
        number_string += each_number.get_text().strip() + ', '
    return shipping_carrier, number_string[:-2], serial_codes


def GetCustomerNumber(SC, session):
    MOL_url_POST_Order_Status = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/order_status_detail.asp'
    MOL_url_POST_Search = 'https://businessonline.motorolasolutions.com/Member/OrderStatus/order_search_results.asp'

    load_detail_params = {'OSRpage': 'yes', 'OrderKey': SC, 'System': 'COF', 'CustEnterpriseId': ''}
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

    page = 1
    current_time = datetime.datetime.today()
    fromYear = current_time.year - 2
    fromDate = str(current_time.month) + '/' + str(current_time.day) + '/' + str(fromYear)
    table_empty = False
    initial_SC_spotted = False
    found_SCs = []
    while not initial_SC_spotted and not table_empty:
        table_empty = True
        search_params = {'TypeOfOrder': '', 'Cust': customer_number, 'CustType': 'CustomerNumber',
                         'EntName': customer_number, 'Search': '',
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
                    if current_SC == SC:
                        initial_SC_spotted = True
                        found_SCs.append(current_SC)
                        #print(current_order_number + '--' + current_SC)
                        break
                    if 'ONELINER' in current_order_number:
                        continue
                    #print(current_order_number + '--' + current_SC)
                    found_SCs.append(current_SC)
        page += 1
    return found_SCs