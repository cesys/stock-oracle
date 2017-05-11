import array
import json
import numpy
import os
import pdb
import pprint
import random
import sys
import time
import urllib2
from collections import OrderedDict
from datetime import date, timedelta
from deap import algorithms
from deap import base
from deap import creator
from deap import tools
from math import sqrt
from pyexcel_ods import get_data
from pyexcel_ods import save_data
from pyquery import PyQuery
from selenium import webdriver

# Constants
debug = True

delta_pos_y_stock_price = 21
pos_x_stock_name = 2
pos_y_stock_name = 0
pos_x_stock_variables = 0
start_pos_y_stock_data = 1
end_pos_y_stock_data = start_pos_y_stock_data + delta_pos_y_stock_price - 1

min_weight = -1.0
max_weight = +1.0

predictor_filename = 'predictor.txt'

# URI
#uri_nasdaq_earnings = "http://www.nasdaq.com/earnings/earnings-calendar.aspx?date=2017-May-08"
uri_nasdaq_earnings = "http://www.nasdaq.com/earnings/earnings-calendar.aspx?date=%s-%s-%s"
uri_ibd_investors = "http://research.investors.com/stock-checkup/nasdaq-%s.aspx"
uri_ibd_login = "https://myibd.investors.com/secure/signin.aspx?eurl=http%3A%2F%2Fwww.investors.com%2F"
ibd_username = "username"
ibd_password = "password"

# Global variables
weights_keys = dict()
checkup = dict()
poly = []
browser = None

def log_msg(message):
    global debug
    if debug:
        print message

def convert_icon_to_float(icon):
    if "Pass" in icon:
        return +1.0
    if "Neutral" in icon:
        return +0.0
    if "Fail" in icon:
        return -1.0
    return None

def convert_grade_to_float(grade):
    value = 0
    if "A" in grade:
        value = 1.0
    if "B" in grade:
        value = 2.0
    if "C" in grade:
        value = 3.0
    if "D" in grade:
        value = 4.0
    if "E" in grade:
        value = 5.0
    if "F" in grade:
        value = 6.0
    if "+" in grade:
        value = value - 0.5
    if "-" in grade:
        value = value + 0.5
    return value

def convert_percent_to_float(percent):
    if "%" in percent:
        return float(percent.replace("%", ""))
    return float(percent)

def convert_dollars_to_float(dollars):
    if "n/a" in dollars:
        return None
    om = 1
    if "K" in dollars:
        om = 1000
        dollars = dollars.replace("K", "")
    if "M" in dollars:
        om = 1000000
        dollars = dollars.replace("M", "")
    if "B" in dollars:
        om = 1000000000
        dollars = dollars.replace("B", "")
    if " USD" in dollars:
        return float(dollars.replace(" USD", "")) * om
    if "$" in dollars:
        return float(dollars.replace("$", "")) * om
    return dollars

def convert_volume_to_float(volume):
    volume = volume.replace(",", "")
    om = 1
    if "Mil" in volume:
        om = 1000000
        volume = volume.replace("Mil", "")
    #if "B" in dollars:
    #    om = 1000000000
    #    dollars = dollars.replace("B", "")
    return float(volume) * om

def pause():
    try:
        input("")
    except:
        pass

def get_value(db, y, x):
    try:
        ret = db[y][x]
        if ret == "":
            return None
        if isinstance(ret, basestring):
            return convert_dollars_to_float(ret)
        return ret
    except IndexError:
        return None

def mean_squared_error(y_actual, y_predicted):
    return sqrt(((numpy.asarray(y_actual) - numpy.asarray(y_predicted)) ** 2).mean())

def forecast(stock, optimal_weights, poly):
    forecast = -1.0
    try :
        forecast = numpy.polyval(poly, sum(stock[key] * optimal_weights.get(key, 0) for key in stock))
    except:
        log_msg("Error!")
    return forecast

def eval(individual):
    global checkup
    global weights_keys
    global poly
    i = 0
    weights = dict()
    # Random weights
    for key in weights_keys:
        weights[key] = individual[i]
        i = i + 1
    # Score
    xvalues = []
    yvalues = []
    for key, stock in checkup.iteritems():
        xvalues.append(sum(stock[0][key] * weights.get(key, 0) for key in stock[0]))
        yvalues.append(stock[1])
    # Linear regression
    poly = numpy.polyfit(xvalues, yvalues, 1)
    # Forecast
    forecast = list(map(lambda x: numpy.polyval(poly, x), xvalues))
    # Score
    rms = mean_squared_error(yvalues, forecast)
    return [rms]

def init_webdriver():
    global browser
    chromedriver = "./chromedriver"
    os.environ["webdriver.chrome.driver"] = chromedriver
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--mute-audio")
    driver = webdriver.Chrome(chromedriver, chrome_options=chrome_options)
    driver.get(uri_ibd_login)
    #time.sleep(5)  # Let the user actually see something!
    search_box = driver.find_element_by_id('UserName')
    search_box.send_keys(ibd_username)
    search_box = driver.find_element_by_id('Password')
    search_box.send_keys(ibd_password)
    driver.find_element_by_id('loginButton').click()
    time.sleep(5)  # Let the user actually see something!
    browser = driver

def load_stock_checkup(stock_name):
    log_msg("Loading stock checkup for " + stock_name)
    global browser
    stock = OrderedDict()
    browser.get(uri_ibd_investors % (stock_name))
    #time.sleep(10)
    page = browser.page_source
    #pdb.set_trace()
    #req = urllib2.Request(uri_ibd_investors % (stock))
    #response = urllib2.urlopen(req)
    #page = response.read()
    #with open('example.html', 'r') as myfile:
    #    page = myfile.read()#.replace('\n', '')
    #pdb.set_trace()
    pq = PyQuery(page)
    i = 0
    keys = ["Composite Rating",
            "Market in confirmed uptrend",
            "Industry Group Rank (1 to 197)",
            #"EPS Due Date",
            "EPS Rating",
            "EPS % Chg (Last Qtr)",
            #"Last 3 Qtrs Avg EPS Growth",
            "# Qtrs of EPS Acceleration",
            #"EPS Est % Chg (Current Qtr)",
            "Estimate Revisions",
            #"Last Quarter % Earnings Surprise",
            #"3 Yr EPS Growth Rate",
            "Consecutive Yrs of Annual EPS Growth",
            #"EPS Est % Chg for Current Year",
            "SMR Rating",
            "Sales % Chg (Last Qtr)",
            "3 Yr Sales Growth Rate",
            "Annual Pre-Tax Margin",
            #"Annual ROE",
            #"Debt/Equity Ratio",
            "Price",
            "RS Rating",
            "% Off 52 Week High",
            "Price vs. 50-Day Moving Average",
            #"50-Day Average Volume",
            "Market Capitalization",
            "Accumulation/Distribution Rating",
            "Up/Down Volume",
            #"% Change In Funds Owning Stock",
            "Qtrs Of Increasing Fund Ownership",
           ]
    while True:
        td = pq.find('td').eq(i)
        text = td.text()
        #pdb.set_trace()
        if text == "Composite Rating":
            i = i + 1
            stock[text] = int(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Market in confirmed uptrend":
            i = i + 2
            stock[text] = convert_icon_to_float(str(pq.find('td').eq(i).find('img')))
        if text == "Industry Group Rank (1 to 197)":
            i = i + 1
            stock[text] = int(pq.find('td').eq(i).text())
            i = i + 1
        if text == "EPS Due Date":
            i = i + 1
            ###stock[text] = str(pq.find('td').eq(i).text())
            i = i + 1
        if text == "EPS Rating":
            i = i + 1
            stock[text] = int(pq.find('td').eq(i).text())
            i = i + 1
        if text == "EPS % Chg (Last Qtr)":
            i = i + 1
            stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Last 3 Qtrs Avg EPS Growth":
            i = i + 1
            ###stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "# Qtrs of EPS Acceleration":
            i = i + 1
            stock[text] = int(pq.find('td').eq(i).text())
            i = i + 1
        if text == "EPS Est % Chg (Current Qtr)":
            i = i + 1
            ###stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Estimate Revisions":
            i = i + 2
            stock[text] = convert_icon_to_float(str(pq.find('td').eq(i).find('img')))
        if text == "Last Quarter % Earnings Surprise":
            i = i + 1
            ###stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "3 Yr EPS Growth Rate":
            i = i + 1
            ###stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Consecutive Yrs of Annual EPS Growth":
            i = i + 1
            stock[text] = int(pq.find('td').eq(i).text())
            i = i + 1
        if text == "EPS Est % Chg for Current Year":
            i = i + 1
            ###stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "SMR Rating":
            i = i + 1
            stock[text] = convert_grade_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Sales % Chg (Last Qtr)":
            i = i + 1
            stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "3 Yr Sales Growth Rate":
            i = i + 1
            stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Annual Pre-Tax Margin":
            i = i + 1
            stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Annual ROE":
            i = i + 1
            ###stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Debt/Equity Ratio":
            i = i + 1
            ###stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Price":
            i = i + 1
            stock[text] = convert_dollars_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "RS Rating":
            i = i + 1
            stock[text] = int(pq.find('td').eq(i).text())
            i = i + 1
        if text == "% Off 52 Week High":
            i = i + 1
            stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Price vs. 50-Day Moving Average":
            i = i + 1
            stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "50-Day Average Volume":
            i = i + 1
            ###stock[text] = convert_volume_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Market Capitalization":
            i = i + 1
            stock[text] = convert_dollars_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Accumulation/Distribution Rating":
            i = i + 1
            stock[text] = convert_grade_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Up/Down Volume":
            i = i + 1
            stock[text] = float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "% Change In Funds Owning Stock":
            i = i + 1
            ###stock[text] = convert_percent_to_float(pq.find('td').eq(i).text())
            i = i + 1
        if text == "Qtrs Of Increasing Fund Ownership":
            i = i + 1
            stock[text] = int(pq.find('td').eq(i).text())
            i = i + 1
        if text is None or text == "":
            break
        i = i + 1
    for key in keys:
        if key not in stock:
            raise Exception('Data not populated: ' + str(key))
    log_msg("Done loading stock checkup for " + stock_name)
    return stock

def load_stock_checkup_price_only(stock_name):
    log_msg("Loading stock checkup price only for " + stock_name)
    global browser
    stock = OrderedDict()
    browser.get(uri_ibd_investors % (stock_name))
    page = browser.page_source
    pq = PyQuery(page)
    i = 0
    keys = ["Price",
           ]
    #pdb.set_trace()
    while True:
        td = pq.find('td').eq(i)
        text = td.text()
        if text == "Price":
            i = i + 1
            stock[text] = convert_dollars_to_float(pq.find('td').eq(i).text())
            i = i + 1
        else:
            i = i + 2
        if text is None or text == "":
            break
        i = i + 1
    for key in keys:
        if key not in stock:
            raise Exception('Data not populated: ' + str(key))
    log_msg("Done loading stock checkup price only for " + stock_name)
    return stock

def load_earnings_calendar(date_str):
    log_msg("Loading earnings calendar")
    req = urllib2.Request(uri_nasdaq_earnings % (date_str[0], date_str[1], date_str[2]))
    response = urllib2.urlopen(req)
    page = response.read()
    pq = PyQuery(page)
    html_table = pq('table').filter('.USMN_EarningsCalendar').eq(0)
    trs = html_table.find('tr')
    ths = trs.eq(0).find('th')
    table_columns_names = []
    table_earnings = []
    # Head
    i = 0
    while True:
        text = ths.eq(i).text()
        if text is None or text == "":
            break
        table_columns_names.append(text)
        i = i + 1
    # Rows
    i = 1
    #pdb.set_trace()
    while True:
        ths = trs.eq(i)
        text = ths.text()
        if text is None or text == "":
            break
        j = 0
        row = dict()
        tds = ths.find('td')
        while True:
            text = tds.eq(j).text()
            if j == 4 or j == 7:
                text = convert_dollars_to_float(text)
            if j == 0:
                if 'weather_sun' in str(tds.eq(0).find('img')):
                    text = 'Before'
                if 'half_moon' in str(tds.eq(0).find('img')):
                    text = 'After'
            if text is None or text == "":
                break
            row[table_columns_names[j]] = text
            if j == 1:
                row['Name'] = text[text.rfind("(") + 1:text.rfind(")")]
                row['Size'] = convert_dollars_to_float(text[text.find("$"):])
            j = j + 1
        table_earnings.append(row)
        i = i + 1
    log_msg("Done loading earnings calendar")
    return table_earnings

def save_predictor(weights, poly):
    with open(predictor_filename, 'w') as outfile:
        json.dump(weights, outfile)
        outfile.write("\n")
        json.dump({"m":poly[0], "q":poly[1]}, outfile)

def load_predictor():
    with open(predictor_filename, 'r') as infile:
        weights = json.loads(infile.readline())
        poly_dict = json.loads(infile.readline())
        poly = [poly_dict["m"], poly_dict["q"]]
    return weights, poly

# def load_old_ods_sheet():
#     # Open DB
#     log_msg("Load stocks.ods")
#     data = get_data("stocks.ods")
#     db = data["db"]
#     # Load DB
#     last_stock = dict()
#     for x in range(start_x, end_y):
#         stock = dict()
#         for y in range (start_y, end_y):
#             if get_value(db, y, pos_x_data_name) is not None:
#                 if isinstance(get_value(db, y, x), basestring):
#                     print "Error! String in DB -> " + str(y) + " " + str(x) + " " + get_value(db, y, x)
#                     exit(1)
#                 stock[get_value(db, y, pos_x_data_name)] = get_value(db, y, x)
#         #pdb.set_trace()
#         last_stock = stock
#         if get_value(db, pos_y_stock_name, x) is not None:
#             checkup[get_value(db, pos_y_stock_name, x)] = [stock, 0, get_value(db, pos_y_stock_price, x)]
#
#     weights_keys = last_stock.keys()
#     num_of_variables = len(weights_keys)

def generate_checkups_sheet():
    global checkup
    # Load info from internet
    checkup_db = dict()
    tomorrow = date.today() + timedelta(1)
    tomorrow = "2017-05-11"  # TO BE REMOVED
    log_msg("Tomorrow's date: " + str(tomorrow))
    earnings_calendar = load_earnings_calendar(str(tomorrow).split("-"))
    candidates = []
    for stock in earnings_calendar:
        if 'Time' in stock and stock['Time'] == "Before" and 'Consensus EPS* Forecast' in stock:
            candidates.append((stock['Name'],stock['Consensus EPS* Forecast']))
    sorted_candidates = sorted(candidates, key=lambda candidate: candidate[1], reverse=True)
    #for i in range(1, 40 + 1):
    #for i in range(1, 40 + 1):
    i = 0
    for stock in sorted_candidates:
        #stock = sorted_candidates[i]
        stock_name = stock[0]
        try:
            checkup_db[stock_name] = load_stock_checkup(stock_name)
            i = i + 1
        except:
            print "Cannot load all fields!"
        if i == 60:
            break
    print checkup_db
    checkup_db_list = []
    for key, checkup_stock in checkup_db.iteritems():
        if "EPS Rating" in checkup_stock:
            checkup_db_list.append((key, checkup_stock["EPS Rating"]))
    checkup_db_list = sorted(checkup_db_list, key=lambda candidate: candidate[1], reverse=True)
    for tuple in checkup_db_list:
        print tuple

    # Save stock checkups to ods
    predictions = [0] * len(checkup_db)
    weights = None
    poly = None
    if os.path.isfile(predictor_filename):
        weights, poly = load_predictor()
        predictions = []
    data = OrderedDict()  # from collections import OrderedDict
    #data.update({"Checkups": [[1, 2, 3], [4, 5, 6]]}) # Example
    #pdb.set_trace()
    stocks_sheet = []
    stocks_keys = []
    for key, stock in checkup_db.iteritems():
        stocks_keys = stock.keys()
        stocks_sheet.append([key] + stock.values())
        if weights is not None:
            predictions.append(float(forecast(stock, weights, poly)))
    stocks_sheet_plus_keys = []
    head = [""] + stocks_keys
    stocks_sheet_plus_keys.append(head)
    stocks_sheet_plus_keys.append([""] * len(head))
    stocks_sheet_plus_keys = stocks_sheet_plus_keys + stocks_sheet
    print stocks_sheet_plus_keys
    sheet = map(list, zip(*stocks_sheet_plus_keys)) # Transpose
    print sheet
    sheet.append(["Price After Earnings"] + [""] + [0] * len(checkup_db))
    sheet.append(["My Stock Estimate After Earnings"] + [""] + predictions)
    sheet.append(["EPS Due Date"] + [""] + [str(tomorrow)] * len(checkup_db))
    print sheet
    data.update({"Checkups": sheet})
    save_data("checkups-%s.ods" % (str(tomorrow)), data)

def populate_checkups_sheet_with_price_after_earning():
    global checkup
    # Load info from internet
    yesterday = date.today() - timedelta(1)
    yesterday = "2017-05-09"  # TO BE REMOVED
    log_msg("Yesterday's date: " + str(yesterday))
    filename = "checkups-%s.ods" % (str(yesterday))
    data = get_data(filename)
    x = pos_x_stock_name
    while True:
        stock_name = ""
        try:
            stock_name = data["Checkups"][pos_y_stock_name][x]
        except IndexError:
            break
        if stock_name is None or stock_name == "":
            break
        data["Checkups"][pos_y_stock_name + delta_pos_y_stock_price][x] = load_stock_checkup_price_only(stock_name)["Price"]
        data["Checkups"][pos_y_stock_name + delta_pos_y_stock_price][x]
        x = x + 1
    save_data(filename, data)

def calculate_optimal_weights():
    global weights_keys
    global checkup
    global poly
    log_msg("Calculating optimal weights")
    # Open DB
    filename = "checkups.ods"
    data = get_data(filename)
    # Load DB
    last_stock = dict()
    x = pos_x_stock_name
    while True:
        stock = dict()
        stock_name = ""
        try:
            stock_name = data["Checkups"][pos_y_stock_name][x]
        except IndexError:
            break
        if stock_name is None or stock_name == "":
            break
        for y in range (start_pos_y_stock_data, end_pos_y_stock_data):
            stock[data["Checkups"][y][pos_x_stock_variables]] = data["Checkups"][y][x]
        #pdb.set_trace()
        last_stock = stock
        #target = (data["Checkups"][end_pos_y_stock_data][x] - stock["Price"]) / stock["Price"] * 100
        target = data["Checkups"][end_pos_y_stock_data][x]
        checkup[stock_name] = [stock, target]
        x = x + 1
    weights_keys = last_stock.keys()
    num_of_variables = len(weights_keys)

    # GA determine optial fit
    creator.create("FitnessMin", base.Fitness, weights=(-1.0,))
    #creator.create("Individual", array.array, typecode='f', fitness=creator.FitnessMin)
    creator.create("Individual", list, fitness=creator.FitnessMin)

    toolbox = base.Toolbox()

    # Attribute generator
    toolbox.register("attr_float", random.uniform, min_weight, max_weight)

    # Structure initializers
    toolbox.register("individual", tools.initRepeat, creator.Individual, toolbox.attr_float, num_of_variables)
    toolbox.register("population", tools.initRepeat, list, toolbox.individual)
    toolbox.register("evaluate", eval)
    toolbox.register("mate", tools.cxTwoPoint)
    toolbox.register("mutate", tools.mutFlipBit, indpb=0.05)
    toolbox.register("select", tools.selTournament, tournsize=3)

    pop = toolbox.population(n=4000) # Default = 300
    hof = tools.HallOfFame(1)
    stats = tools.Statistics(lambda ind: ind.fitness.values)
    stats.register("avg", numpy.mean)
    stats.register("std", numpy.std)
    stats.register("min", numpy.min)
    stats.register("max", numpy.max)

    pop, log = algorithms.eaSimple(pop, toolbox, cxpb=0.5, mutpb=0.4, ngen=40,
                                   stats=stats, halloffame=hof, verbose=True)
    print "\n"
    print "--------------------"
    i = 0
    optimal_weights = dict()
    for key in weights_keys:
        optimal_weights[key] = hof[0][i]
        i = i + 1
    pprint.pprint(optimal_weights)
    print poly
    save_predictor(optimal_weights, poly)

    # Value forecast
    # stock_name = "AGN"
    # print stock_name + " -> " + str(forecast(checkup[stock_name][0], optimal_weights, poly))
    # stock_name = "SRE"
    # print stock_name + " -> " + str(forecast(checkup[stock_name][0], optimal_weights, poly))
    # stock_name = "WRLD"
    # print stock_name + " -> " + str(forecast(checkup[stock_name][0], optimal_weights, poly))
    # stock_name = "TDG"
    # print stock_name + " -> " + str(forecast(checkup[stock_name][0], optimal_weights, poly))
    # stock_name = "HSIC"
    # print stock_name + " -> " + str(forecast(checkup[stock_name][0], optimal_weights, poly))

def main():
    init_webdriver()
    generate_checkups_sheet()
    #populate_checkups_sheet_with_price_after_earning()
    #calculate_optimal_weights()
    exit(0)

main()
