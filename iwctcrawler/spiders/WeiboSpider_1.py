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
from iwctcrawler.items import UserProfileItem
import re, json
from pyquery import PyQuery as pq
from lxml.html import tostring
from iwctcrawler.sina.weibo import Weibo
from iwctcrawler.sina import _epoch
from scrapy.shell import inspect_response


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
                log.msg('user displayname: %s, user id: %s' % (userinfo['displayname'],userinfo['uniqueid']), level=log.INFO)
                assert userinfo['displayname'] in self.username
                self.logined = True


