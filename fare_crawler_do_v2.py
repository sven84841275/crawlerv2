import requests
import json
import execjs
import pandas as pd
import os
from matplotlib import pyplot as plt
import random
import time
import datetime
from requests import exceptions


# 请求的最大错误数，如超出则get_fare返回None值
connection_error_limit = 3


def create_token(dep_city, arr_city, flight_way="Oneway"):
    """
    调用create_token.js文件，生成加密的token码

    :param dep_city: <str> 起飞城市三字码
    :param arr_city: <str> 到达城市三字码
    :param flight_way: <str> 单多程
    :return: token: <str> token码
    """
    with open('create_token.js', 'r', encoding='utf-8') as f:
        jsstr = f.read()
    js = execjs.compile(jsstr)
    return js.call("getProductToken", dep_city, arr_city, flight_way)


def get_fare(dep_city, arr_city, dep_date, flight_way="Oneway", download_daily=False, allow_surrounding_cities=False):
    """
    获取当天的票价数据

    :param dep_city: <str> 起飞城市三字码
    :param arr_city: <str> 到达城市三字码
    :param dep_date: <str> 起飞日期，格式为“YYYY-MM-DD”
    :param flight_way: <str> 单/联程
    :param download_daily: <bool> 是否保存数据
    :param allow_surrounding_cities: <bool> 是否允许接收周边城市数据
    :return: fare_data: <dataframe> 票价数据
    """
    dep_city, arr_city = dep_city.lower(), arr_city.lower()  # 统一字符串格式为小写

    # step 1
    url = "https://flights.ctrip.com/itinerary/api/12808/products"

    # step 2
    headers = {
        "authority": "flights.ctrip.com",
        "method": "POST",
        "path": "/itinerary/api/12808/products",
        "scheme": "https",
        "accept": "*/*",
        "accept-encoding": "gzip,deflate,br",
        "accept-language": "zh-CN,zh;q=0.9",
        "content-length": "287",
        "content-type": "application/json",
        "origin": "https://flights.ctrip.com",
    }

    # headers字典中，新增referer键，值是动态生成的referer
    headers["referer"] = "https://flights.ctrip.com/itinerary/oneway/{}-{}?date={}".format(dep_city, arr_city, dep_date)

    # user-agent的list，请求时在这个list中随机选择一个user-agent
    agent_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.122 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/78.0.3904.108 Safari/537.36"]

    # post一同提交的data，注意在headers的content-type中，FORM-DATA或JSON，提交数据时的类型是不同的
    request_data = {"flightWay": flight_way,
            "classType": "ALL",
            "hasChild": False,
            "hasBaby": False,
            "searchIndex": "1",
            "airportParams": [{"dcity": dep_city, "acity": arr_city, "date": dep_date}],
            "token": create_token(dep_city, arr_city, flight_way)}  # 关键key token的获取

    # json.dumps是把字典打包成json格式
    # json.loads是把json格式读取成字典
    request_data = json.dumps(request_data)

    # step 9 当前错误计数器
    connection_error_count = 0
    while True:
        # step 10
        # 当前错误数大于最大错误数时，返回None值。
        if connection_error_count < connection_error_limit:
            try:
                # step 3
                headers["user-agent"] = random.choice(agent_list)
                response = requests.post(url, data=request_data, headers=headers, timeout=5)
                content = json.loads(response.content)  # json格式转成dict格式

                # step 5
                # 请求返回的json数据中，含有error信息，若不为None则表示有错误，此处处理的是能获取response情况下的错误
                if content["data"]["error"] is not None:  # 无错误是error是null值，在python中则用None，都是表示空值
                    print(content["data"]["error"]["msg"])  # 打印错误信息，当出现错误时，error字段里面含有msg的key，用于提示错误的详情
                    connection_error_count += 1
                    print("查询返回异常，正在重试，次数{}/{}".format(str(connection_error_count), str(connection_error_limit)))
                    time.sleep(5 + random.random() * random.randint(2, 3))
                    continue

                # 若无错误，跳出循环
                break

            # step 11
            # try,except主要处理没有response的错误，比如断网等情况
            except exceptions.Timeout:  # 在post时指定了timeout时间，超时则会执行timeout错误
                connection_error_count += 1
                print("连接超时，正在重试，次数{}/{}".format(str(connection_error_count), str(connection_error_limit)))
                time.sleep(5 + random.random() * random.randint(2, 3))

            except Exception as e:  # 非超时错误时的处理
                print(e)
                connection_error_count += 1
                print("连接出错，正在重试，次数{}/{}".format(str(connection_error_count), str(connection_error_limit)))
                time.sleep(5+random.random()*random.randint(2, 3))

        # 若尝试次数超过最大错误数，函数直接返回None
        else:
            print("连接出错且超过最大尝试次数，请检查网络或稍后再试！")
            return None

    # step 4 分析response的结构 发现航班数据是在 data —— routeList 里，以下是提取数据的过程
    route_list = content["data"]["routeList"]
    if route_list is None:
        print(dep_date, "无数据")
        return None
    fare_list = []
    print("开始提取" + dep_date + "数据")
    for route in route_list:
        legs = route["legs"]
        for leg in legs:
            try:
                # 如果该条数据没有flight的key，表示它不是航班，则直接跳过
                flight = leg["flight"]
            except KeyError as e:
                print("该数据不是航班数据，略过")
                continue
            airline_code = flight["airlineCode"]
            flight_number = flight["flightNumber"]
            print("正在提取{}航班数据".format(flight_number))
            dep_city_tlc = flight["departureAirportInfo"]["cityTlc"]
            arr_city_tlc = flight["arrivalAirportInfo"]["cityTlc"]

            # step 6
            if not allow_surrounding_cities:
                if dep_city_tlc.lower() != dep_city or arr_city_tlc.lower() != arr_city:
                    print("该航班属于周边城市，略过！")
                    continue

            # 此处我将机场三字码和航班楼直接拼接成一个字符串
            dep_airport = flight["departureAirportInfo"]["airportTlc"] + " " + flight["departureAirportInfo"]["terminal"]["name"]
            arr_airport = flight["arrivalAirportInfo"]["airportTlc"] + " " + flight["arrivalAirportInfo"]["terminal"]["name"]
            dep_time = flight["departureDate"]
            arr_time = flight["arrivalDate"]

            # step 7  同一个航班，有不同的舱位价格，因此这里需要嵌套一个for循环，来遍历舱位价格
            for cabin in leg["cabins"]:
                cabin_class = cabin["cabinClass"]
                cabin_area = cabin["classAreaCode"]
                price = cabin["price"]["price"]
                rate = cabin["price"]["rate"]
                seat_count = cabin["seatCount"]

                # step 8  以舱位、价格为数据的行，连同之前获取的航班、机场等一同追加到fare list里。
                # 注意在cabin遍历过程中append，舱位和价格是不同的，但是航班、机场等是相同的，这里的cabin都属于上面获取到的那个航班。
                fare_list.append((airline_code, flight_number, dep_airport, dep_time, arr_airport, arr_time, cabin_class, cabin_area, price, rate, seat_count))
                # fare_list = [("CZ", "3333", "CAN", ... , "350"), ("CZ", "3333", "CAN", ... , "450"), ...]

    # 提取数据完毕后，将fare_list转换成dataframe格式
    fare_data = pd.DataFrame(fare_list, columns=["航空公司", "航班号", "起飞机场", "起飞时间", "到达机场", "到达时间", "母舱位", "子舱位", "票价", "折扣", "剩余座位"])
    if download_daily:
        # step 12 保存在本地，并设置一些错误处理
        try:
            fare_data.to_excel("{}_{}_{}.xlsx".format(dep_city, arr_city, dep_date))
        except PermissionError:
            print("{}_{}_{}.xlsx 文件正被使用，保存失败".format(dep_city, arr_city, dep_date))
        except Exception as e:
            print("{}_{}_{}.xlsx 文件保存时发生错误：{}，保存失败".format(dep_city, arr_city, dep_date, e))
    return fare_data


def plot_lowest_theday(fare_data):
    """
    生成当日所有航班最低价格的柱状图

    :param fare_data: <dataframe> 当日航班票价的dataframe
    :return: 无
    """
    # 按航班筛选出某个航班票价最低的行
    lowest_price = fare_data.groupby(['航班号'])["票价"].min()
    # 再用dataframe的plot函数
    lowest_price.plot(kind="bar")
    plt.show()


# step 13
def make_date_list(start_date, end_date):
    """
    生成日期区间list

    :param start_date: <str> 起始日期，格式为“YYYY-MM-DD”
    :param end_date: <str> 终止日期，格式为“YYYY-MM-DD”
    :return: date_list: <list> 从起始日期开始到终止日期为止的所有日期（str，格式为“YYYY-MM-DD”）的list
    """
    date_list = []
    # 开始日期
    start_date = datetime.datetime.strptime(str(start_date), '%Y-%m-%d')
    # 截止日期
    end_date = datetime.datetime.strptime(str(end_date), '%Y-%m-%d')
    # 计算间隔天数 假设start_date为"2020-06-01"，end_date为"2020-06-03"
    day_delta = (end_date - start_date).days + 1
    # print(day_delta)  out: 3

    # 遍历间隔天数，用开始日期加天数来获取每一天的日期，最后追加到list中，返回list
    # print(range(day_delta))  out: range(0, 3)  也就是0,1,2
    for days in range(day_delta):
        # step 14
        the_date = (start_date + datetime.timedelta(days=days)).strftime('%Y-%m-%d')
        date_list.append(the_date)
    #  date_list： ['2020-06-01', '2020-06-02', '2020-06-03']
    return date_list


# step 15
def get_fare_stack(dep_city, arr_city, start_date, end_date, flight_way="Oneway", download_daily=False, download_stack=False, allow_surrounding_cities=False):
    """
    用于批量获取一个日期时间段的票价数据，在函数内部会调用get_fare函数，因此参数大部分是get_fare函数的参数，主要的不同在于日期，
    get_fare是一个日期，这里传入的日期一个是开始日期，一个是截止日期，通过调用make_date_list生成一个date_list

    :param dep_city: <str> 起飞城市三字码
    :param arr_city: <str> 到达城市三字码
    :param start_date: <str> 开始日期，格式为“YYYY-MM-DD”
    :param end_date: <str> 截止日期，格式为“YYYY-MM-DD”
    :param flight_way: <str> 单/联程
    :param download_daily: <bool> 是否下载每日数据
    :param download_stack: <bool> 是否下载日期区间整合数据
    :param allow_surrounding_cities: <bool> 是否允许接收周边城市数据
    :return: fare_stack: <dataframe> 日期区间整合数据
    """
    # step 17
    dep_city, arr_city = dep_city.lower(), arr_city.lower()  # 统一字符串格式，为小写
    date_list = make_date_list(start_date, end_date)  # 执行make_date_list函数，生成日期区间的list
    fare_stack = pd.DataFrame(None)  # 这里创建一个空的dataframe，用于堆放每天fare_data的dataframe，方便后面堆叠，同时也可以防止dataframe没有定义报错

    # step 18 遍历data_list
    for dep_date in date_list:

        # step 16 执行get_fare函数，正常情况返回的是dataframe，若出错则返回None，step21是对返回为None时的处理
        fare_data = get_fare(dep_city, arr_city, dep_date, flight_way, download_daily, allow_surrounding_cities=allow_surrounding_cities)

        # step 21 get_fare出错返回None时的处理
        if fare_data is None:
            # 如果fare_data为None，则表示在get_fare函数内部发生了请求错误，并且尝试了多次都无法解决，因此在批量爬取时不再作尝试，而是退出程序。
            print("{} 数据获取失败，程序中断！".format(dep_date))

            # 在退出程序之前，如果之前已经获取到了一部分日期的数据，在中途中断的，这里会保存之前已经获取到的数据，防止已获取数据丢失而重新爬取
            if fare_stack.shape[0] > 0:  # fare_stack是个二维数据，因此shape返回的是横纵坐标的长度，shape[0]就是行数。行数大于0，则表示之前已经堆叠了一部分日期的数据了
                break_date = datetime.datetime.strptime(dep_date, "%Y-%m-%d") - datetime.timedelta(days=1)  # 本次dep_date获取失败，正常数据就是停留在上一天，因此中断日期要减1天
                break_date = datetime.datetime.strftime(break_date, "%Y-%m-%d")
                try:
                    fare_stack.to_excel("{}_{}_{}_{}.xlsx".format(dep_city, arr_city, start_date, break_date))
                    print("已成功获取的{}至{}的数据已为您保存！".format(start_date, break_date))
                except PermissionError:
                    print("{}_{}_{}_{}.xlsx文件正被使用，保存失败".format(dep_city, arr_city, start_date, break_date))
                except Exception as e:
                    print("{}_{}_{}_{}.xlsx文件保存时发生错误：{}，保存失败".format(dep_city, arr_city, start_date, break_date, e))
                os._exit(0)

        # step 22 如果get_fare没有出错，但是没有这条航线的票价数据时（如某些航线不是每天都有航班），get_fare不会返回None，
        # 而是会返回0行的dataframe，虽然不影响后面的操作（程序不会报错），但是为了节省资源提高效率，还是跳过后续的操作，并且提醒用户。
        if fare_data.shape[0] == 0:
            print("未搜索到{}该航线的票价！".format(dep_date))
            continue

        # step 19 一切正常的情况下执行
        if fare_stack.shape[0] == 0:  # 判断fare_stack out:(10,20) 是不是第一次堆叠，如果是，直接赋值不需要堆叠
            fare_stack = fare_data
        else:
            fare_stack = pd.concat([fare_stack, fare_data], axis=0, join='outer')
        time.sleep(5+random.random()*random.randint(2, 3))
    if download_stack:  # 与单个fare_data相似地，如果需要将堆叠后的fare_stack保存在本地，则执行，并设置一些错误处理
        try:
            fare_stack.to_excel("{}_{}_{}_{}.xlsx".format(dep_city, arr_city, start_date, end_date))
        except PermissionError:
            print("{}_{}_{}_{}.xlsx文件正被使用，保存失败".format(dep_city, arr_city, start_date, end_date))
        except Exception as e:
            print("{}_{}_{}_{}.xlsx文件保存时发生错误：{}，保存失败".format(dep_city, arr_city, start_date, end_date, e))
    return fare_stack


# step 20
def plot_lowest_daily(fare_stack):
    """
    生成日期区间内每日最低票价的折线图

    :param fare_stack: <dataframe> 日期区间整合数据
    :return: 无
    """
    fare_stack[["日期", "时间"]] = fare_stack["起飞时间"].str.split(" ", expand=True)
    lowest_price = fare_stack.groupby(['日期'])["票价"].min()
    lowest_price.plot(kind="line")
    plt.show()


if __name__ == "__main__":
    fare_data = get_fare("can", "SHA", "2020-06-28", download_daily=True, allow_surrounding_cities=False)
    plot_lowest_theday(fare_data)
    # fare_stack = get_fare_stack("can", "SHA", "2020-06-08", "2020-06-12", download_daily=False, download_stack=True, allow_surrounding_cities=False)
    # plot_lowest_daily(fare_stack)
