#coding=utf-8
import codecs
from datetime import datetime, timedelta
import urllib
import BeautifulSoup as BeautifulSoupModule
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
        # in this debug period, we apply a specified list of user_ids for test
        self.id_toCrawl_list   = set(['3756315403','1018794373','1023892974','1031682077','1031827884',\
                             '1016130663','1015699074','1016439911','1026341455','1028029113'])

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
                # get 1 id from the list toCrawl
                id_toCrawl = self.id_toCrawl_list.pop()

                trypage_url = QueryFactory.mainpage_query(id_toCrawl)
                mainpage_request = Request(url=trypage_url,callback=self.mainpage_parse,meta={'user_id':id_toCrawl})
                yield mainpage_request

            else:
                self.log('login failed: errno=%s, reason=%s' % (data.get('errno', ''), data.get('reason', '')))


    # parse mainpage_response
    def mainpage_parse(self,response):
        if response:
            sel = Selector(response)
            login_user = {}
            login_user['toCrawl_user_id']   =  response.meta['user_id']
            login_user['login_user_id']     =  self.get_property(response,"uid")
            login_user['page_id']           =  self.get_property(response,"page_id")
            login_user['pid']               =  self.get_property(response,"pid")
            print '\n',login_user,'\n'

            login_user_profile_url = QueryFactory.info_query(page_id=login_user['page_id'], pid=login_user['pid'])
            log.msg('  user toCrawl id: %s, user login id: %s' \
                    % (login_user['toCrawl_user_id'],login_user['login_user_id']), level=log.INFO)

            request = Request(url=login_user_profile_url,callback=self.user_info_parse,meta={'login_user':login_user})
            yield request

        else:
            yield self.start_requests()

    # parse user_info_page
    def user_info_parse(self,response):
        user_profile_translation = {
                        u"性别"      :    'sex',
                        u"简介"      :    'description',
                        u"注册时间"  :    'signed_time',
                        u"所在地"    :    'location',
                        u"生日"      :    'birthday',
                        
                        u"公司"      :    'company',

                        u"大学"      :    'university',

                        u"标签"      :    'personal_tags'
                       }

        if response:
            login_user = response.meta['login_user']
            user = UserProfileItem()
            # fulfill the user Item
            user['user_id']          =  self.get_property(response,"oid")
            user['screen_name']      =  self.get_property(response,"onick")

            user_tags_dict           =  self.get_userinfo_by_html(response)

            for property_name in user_profile_translation:
                user[user_profile_translation[property_name]] = user_tags_dict.get(property_name,'')

            print '\n\nUser Profile:\n'
            for user_item in dict(user).items():
                print '\t',user_item[0],' : ',user_item[1]

            print "\n\n"

            # url to get total number of weibos' pages
            user_weibo_page_url     =  QueryFactory.weibo_page_num_query(page_id = login_user['page_id'], page_num=1 )

            # first request to get the total number of user weibos' pages
            request = Request(url=user_weibo_page_url,callback=self.user_weibo_pages_num,meta={'login_user':login_user})
            yield request

        else:
            self.start_requests()

    # get weibo pages total number
    def user_weibo_pages_num(self,response):
        #inspect_response(response,self)
        if response:
            # pares the current js response
            self.user_weibo_parse(response)

            login_user       =  response.meta['login_user']
            # load response in json form
            html_block_soup  =  self.json_load_response(response)

            # get the tag containing the max num of page
            page_list_tag    =  html_block_soup.find('div',{'class':'W_pages_layer S-FIXED'})
            if page_list_tag:
                total_num_pages  =  int(re.search(r'\d+',page_list_tag.a.string).group(0))
            else:
                total_num_pages  =  1

            # warp weibo page urls to crawl
            weibo_page_urls       =  self.wrap_weibo_pages_urls( page_id=login_user['page_id'], num_page=total_num_pages )


            # test part weibo parser
            user_weibo_page_url   =  QueryFactory.weibo_page_num_query(page_id = login_user['page_id'], page_num=2 )

            # first request to get the total number of user weibos' pages
            request = Request(url=user_weibo_page_url,callback=self.user_weibo_parse,meta={'login_user':login_user})
            yield request

        else:
            self.start_requests()


    # get weibo contents
    def user_weibo_parse(self,response):
        #inspect_response(response,self)

        if response:
            login_user       =  response.meta['login_user']
            # load response in json form
            html_block_soup  =  self.json_load_response(response)

            i = 0
            for weibo in html_block_soup.findAll('div',{'mid':True,'class':'WB_feed_type SW_fun S_line2 '}):
                i +=1
                # load weibo contents
                weibo_contents_block   =   weibo.findAll('div',{'class':'WB_text','node-type':'feed_list_content'},limit=1)[0]
                if weibo_contents_block:
                    weibo_contents     =   weibo_contents_block.contents
                    for index in range(len(weibo_contents)):
                        content  =  weibo_contents[index]
                        if type(content)==BeautifulSoupModule.Tag:
                            if content.name=='a':
                                if content.string:
                                    weibo_contents[index]  =  content.string + ' '
                                else:
                                    weibo_contents[index]  =  ' '
                            else:
                                weibo_contents[index]  =  content.get('title','')
                        else:
                            weibo_contents[index]  =  content.strip()
                    weibo_contents    =  ''.join(weibo_contents)

                else:
                    weibo_contents = ''

                print '\n\n Weibo[',str(i),'] contents: ',weibo_contents,'\n'


                # load creatTime
                weibo_time_block  =  weibo.findAll('a',{'class':'S_link2 WB_time','node-type':'feed_list_item_date'},limit=1)[0]
                if weibo_time_block:
                    weibo_creat_time  =  weibo_time_block.get('title')
                else:
                    weibo_creat_time  =  ''
                print ' Weibo[',str(i),'] creat at: ',weibo_creat_time,'\n'


                # load sourceApp
                weibo_source_block  =  weibo.findAll('a',{'class':'S_link2','action-type':'app_source'},limit=1)[0]
                if weibo_source_block:
                    weibo_app_source  =  weibo_source_block.string
                else:
                    weibo_app_source  =  ''
                print ' Weibo[',str(i),'] app_source: ',weibo_app_source,'\n\n'


                # load retweeted weibo if exists
                weibo_retweet_block= weibo.findAll('div',{'node-type':'feed_list_forwardContent'},limit=1)[0]
                if weibo_retweet_block:
                    pass
                else:
                    retweet = ''
        else:
            self.start_requests()


    # load response in json form
    # use BeautifulSoup to extract
    def json_load_response(self,response):
        jsonresponse     =  json.loads(response.body_as_unicode())
        html_block       =  jsonresponse.get('data')
        html_block_soup  =  BeautifulSoup(html_block)
        return html_block_soup

    # get property value from the user homepage
    def get_property(self,response,property_name):
        selector = Selector(response)
        # regular expression to extract CONFIG proerty
        regex_term = re.compile(r"CONFIG\[\'"+property_name+r"\'\]=\'(.*)\'")
        # find the second script in head node which indicates properties
        return selector.xpath('/html/head/script/text()').re(regex_term)[0]

    # get user profile property value from the user infopage
    def get_userinfo_by_html(self,response):
        selector = Selector(response)
        tags_dict  =  {}

        # extract the html script block containing personal info
        basic_info_block = selector.xpath('/html/script/text()').re(r'(\{.*\"domid\"\:\"Pl_Official_LeftInfo__26\".*\})')[0]
        basic_info_block_html = json.loads(basic_info_block)['html']
        script_part_soup = BeautifulSoup(basic_info_block_html)

        # decompose the user profile html block into tags like 
        #     property_name     : u"生日"
        #     property_content  : u"1990年04月19日"
        for record_line in script_part_soup.findAll('div',{"class":"pf_item clearfix"}):
            property_name      =    record_line.find('div',{"class":"label S_txt2"}).string
            property_content   =    record_line.find('div',{"class":"con"})
            # return a list of tags when meeting tags info
            if property_content != None:
                if not property_content.string:
                    property_content =  record_line.find('div',{"class":"con"}).a.string
                    if not property_content:
                        tags_elements    = record_line.find('div',{"class":"con"}).findAll('span',{"node-type":"tag"})
                        property_content = ''
                        for tags_elem in tags_elements:
                            property_content = property_content + tags_elem.string + ' '
                    else:
                        property_content = property_content.strip()
                # return the property content of unicode
                else:
                    property_content  = property_content.string.strip()
                # set content empty if no property_content with class "con" is matched
            else:
                property_content  = ''

            tags_dict[property_name] = property_content

        return tags_dict

    # wrap weibo pages url by the user_id and the total num of weibo pages
    def wrap_weibo_pages_urls(self, page_id, num_page):
        weibo_urls = set()

        for page in range(num_page):
            weibo_urls=weibo_urls.union(QueryFactory.weibo_js_query( page_id=page_id,page_num=page+1))

        return weibo_urls

    # get the total number of user's weibos' pages
    def get_weibo_page_num_by_html(self,response):
        pass


