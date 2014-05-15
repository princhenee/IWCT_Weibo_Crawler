#coding=utf-8
import codecs
from datetime import datetime, timedelta
import urllib
from scrapy import log
from scrapy.conf import settings
from scrapy.exceptions import CloseSpider
from scrapy.http import Request
from scrapy.spider import Spider
from scrapy.contrib.spiders import CrawlSpider,Rule
from scrapy.selector import Selector
from iwctcrawler.items import UserProfileItem
import re, json
from pyquery import PyQuery as pq
from iwctcrawler.query_construction import QueryFactory
from lxml.html import tostring
from iwctcrawler.sina.weibo import Weibo
from iwctcrawler.sina import _epoch
from scrapy.shell import inspect_response
from iwctcrawler.items import UserProfileItem,WeiboItem


# default Redis Config from settings
REDIS_HOST=settings.get('REDIS_HOST')
REDIS_PORT=settings.get('REDIS_PORT')

class WeiboSpider(Spider):
    name = 'weibospider'
    allowed_domains = ['weibo.com']
    weibo = Weibo()

    # user account info
    username = settings.get('WEIBO_USER_NAME')
    password = settings.get('WEIBO_USER_PASSWORD')

    # initialize login_url
    def __init__(self,name=None,*args,**kwargs):
        super(WeiboSpider,self).__init__(name,*args,**kwargs)
        self.login = False
        self.start_urls = []
        self.login_url = self.weibo.login(self.username, self.password)
        if self.login_url:
            self.start_urls.append(self.login_url)

    # override the start_requests method to request login_url
    def start_requests(self):
       return [Request(url=self.login_url,callback=self.login_parse)]

    # parse login_response
    def login_parse(self,response):
        if response.body.find('feedBackUrlCallBack') != -1:
            data = json.loads(re.search(r'feedBackUrlCallBack\((.*?)\)', response.body, re.I).group(1))
            userinfo = data.get('userinfo', '')
            if len(userinfo):
                user_id = userinfo.get('uniqueid')
                screen_name = userinfo.get('displayname')
                log.msg('user displayname: %s, user id: %s' % (screen_name,user_id), level=log.INFO)
                assert screen_name in self.username
                self.logined = True

                mainpage_url = QueryFactory.mainpage_query(user_id)
                trypage_url = QueryFactory.mainpage_query('3756315403')
                mainpage_request = Request(url=trypage_url,callback=self.user_parse)
                yield mainpage_request
            else:
                self.log('login failed: errno=%s, reason=%s' % (data.get('errno', ''), data.get('reason', '')))


    # parse mainpage_response
    def user_parse(self,response):
        inspect_response(response,self)
        if response:
            sel = Selector(response)
            user_item = UserProfileItem()
            user_item['user_id']  =  self.get_property(sel,"oid")
            user_item['page_id']  =  self.get_property(sel,"page_id")
            user_item['pid']      =  self.get_property(sel,"pid")
            user_item['screen_name']=self.get_property(sel,"nick")
            user_item['sex']      =  self.get_property(sel,"sex")
            print user_item
            yield user_item

    # get property value from the user profile homepage
    def get_property(self,selector,property_name):
        # regular expression to extract CONFIG proerty
        regex_term = re.compile(r"CONFIG\[\'"+property_name+r"\'\]=\'(.*)\'")
        # find the second script in head node which indicates properties
        return selector.xpath('/html/head/script/text()')[2].re(regex_term)[0]



