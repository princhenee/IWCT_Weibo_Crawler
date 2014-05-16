#coding=utf-8
import codecs
from datetime import datetime, timedelta
import urllib
from BeautifulSoup import BeautifulSoup
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
    '''
    This is the main project spider heritating scrapy.spider.Spider
    you can simply run it on your console under this project directory:
            *** $ scrapy crawl weibospider ***
    where 'weibospider' is the name of this spider
    make sure you get everything installed, see requirements.txt for detail

    the Spider operates following such sequence by default:
    * __init__  ---  start_requests  ---  lorgin_parse  ---  mainpage_parse *
    where module start_requests() is the first request intricated by Spider
    we override it here by our Weibo login url request,else it will run
    request from start_urls
    By assigning the callback argument in Request initialzation, we pass the 
    response of the request to the corresponding callback module.


    @params 
        name       :        the name of spider(obligated)
        weibo      :        an object of Weibo for authentification
        login      :        True/False status of login
        login_url  :        url to lorgin
        username   :        user name for login,usually email
        password   :        password corresponded
        start_urls :        list of urls to crawl by default Spider

    note that some params are loaded from file 'iwctcrawler.settings.py'

    see http://doc.scrapy.org/en/latest  for detail
    '''

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
                log.msg('user login displayname: %s, user login id: %s' % (screen_name,user_id), level=log.INFO)
                assert screen_name in self.username
                self.logined = True

                #mainpage_url = QueryFactory.mainpage_query(user_id)
                # in this debug period, we apply a specified user_id for test '3756315403'
                trypage_url = QueryFactory.mainpage_query('3756315403')
                id_toCrawl = '3756315403'
                mainpage_request = Request(url=trypage_url,callback=self.mainpage_parse,meta={'user_id':id_toCrawl})
                yield mainpage_request
            else:
                self.log('login failed: errno=%s, reason=%s' % (data.get('errno', ''), data.get('reason', '')))


    # parse mainpage_response
    def mainpage_parse(self,response):
        if response:
            sel = Selector(response)
            login_user = {}
            login_user['login_user_id']     =  self.get_property(response,"uid")
            login_user['page_id']           =  self.get_property(response,"page_id")
            login_user['pid']               =  self.get_property(response,"pid")
            print login_user
            login_user_profile_url = QueryFactory.info_query(login_user['page_id'],login_user['pid'])
            request = Request(url=login_user_profile_url,callback=self.login_user_info_parse,meta={'login_user':login_user})
            yield request
        else:
            yield self.start_requests()

    # parse login_user_info_parse
    def login_user_info_parse(self,response):
        #inspect_response(response,self)
        if response:
            login_user = response.meta['login_user']
            user = UserProfileItem()

            user['user_id']          =  self.get_property(response,"oid")
            user['screen_name']      =  self.get_property(response,"onick")

            self.get_userinfo_by_html(response)

            print user
            user_weibo_url = QueryFactory.weibo_query(login_user['page_id'],login_user['pid'])
            request = Request(url=user_weibo_url,callback=self.user_weibo_parse,meta={'user_item':user})
        else:
            self.start_requests()

    # parse weibo page
    def user_weibo_parse(self,response):
        pass

    # get property value from the user homepage
    def get_property(self,response,property_name):
        selector = Selector(response)
        # regular expression to extract CONFIG proerty
        regex_term = re.compile(r"CONFIG\[\'"+property_name+r"\'\]=\'(.*)\'")
        # find the second script in head node which indicates properties
        return selector.xpath('/html/head/script/text()').re(regex_term)[0]

    # get user profile property value from the user infopage
    def get_userinfo_by_html(self,response):
        #inspect_response(response,self)
        selector = Selector(response)

        basic_info_block = selector.xpath('/html/script/text()').re(r'(\{.*\"domid\"\:\"Pl_Official_LeftInfo__26\".*\})')[0]
        basic_info_block_html = json.loads(basic_info_block)['html']
        script_part_soup = BeautifulSoup(basic_info_block_html)

        print "\n\nHERE!!!!!!!!!!!!length:",len(script_part_soup.div),"\n\n"
        for xterm in script_part_soup.findAll('div',{"class":"pf_item clearfix"}):
            print '\t',xterm.contents


