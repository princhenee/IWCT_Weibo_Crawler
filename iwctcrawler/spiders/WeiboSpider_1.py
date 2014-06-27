#coding=utf-8
import codecs
import urllib
import re, json
import redis
from datetime import datetime, timedelta
import BeautifulSoup as BeautifulSoupModule
from BeautifulSoup import BeautifulSoup
from lxml.html import tostring
from scrapy import log
from scrapy.conf import settings
from scrapy.exceptions import CloseSpider
from scrapy.http import Request
from scrapy.spider import Spider
from scrapy.contrib.spiders import CrawlSpider,Rule
from scrapy.selector import Selector
from scrapy.shell import inspect_response
from iwctcrawler.items import UserProfileItem
from iwctcrawler.query_construction import QueryFactory
from iwctcrawler.sina.weibo import Weibo
from iwctcrawler.sina import _epoch
from iwctcrawler.items import UserProfileItem,WeiboItem



class WeiboSpider(Spider):
    '''
    This is the main project spider heritating scrapy.spider.Spider
    you can simply run it on your console under this project directory:
            *** $ scrapy crawl weibospider ***
    where 'weibospider' is the name of this spider
    make sure you get everything installed, see requirements.txt for detail

    the Spider operates following such sequence:

    ***    __init__  -->  start_requests 
            -->  lorgin_parse  -->  mainpage_parse 
              -->   user_info_parse  -->  weibo_pages_num
                -->  weibo_parse       -->  close spider                ***

    where module start_requests() is the first request intricated by Spider
    we override it here by our Weibo login url request,else it will run
    request from start_urls
    By assigning the callback argument in Request initialzation, we pass the 
    response of the request to the corresponding callback module.


    @parameters
    -----------
        name       :        the name of spider(obligated)
        weibo      :        an object of Weibo for authentification
        login      :        True/False status of login
        login_url  :        url to lorgin
        username   :        user name for login,usually email
        password   :        password corresponded
        start_urls :        list of urls to crawl by default Spider



    @parsers
    --------
        login_parse       :        get login info and set cookies
                                          and request mainpage according to uid

        mainpage_parse    :        get page_id and pid for following urls
                                          and request user_info url

        user_info_parse   :        yield userprofile item
                                          and request buttom of 1st weibo page

        weibo_pages_num   :        get total number of weibos' pages
                                          and request all weibo pages urls

        weibo_parse       :        yield weibo item


    note that some params are loaded from file 'iwctcrawler.settings.py'

    see http://doc.scrapy.org/en/latest  for detail
    '''

    name = 'weibospider'
    allowed_domains = ['weibo.com']
    weibo = Weibo()

    # user account info
    username = settings.get('WEIBO_USER_NAME')
    password = settings.get('WEIBO_USER_PASSWORD')

    # default Redis Config from settings
    REDIS_HOST=settings.get('REDIS_HOST','localhost')
    REDIS_PORT=settings.get('REDIS_PORT',6379)

    # initialize login_url
    def __init__(self,name=None,*args,**kwargs):
        '''Initialize weibospider

        Parameters
        ----------
        login            :    login status (True/False)
        start_urls       :    default urls to start crawling
        login_url        :    url to login

        redis_server     :    redis server Connected
        ids_toCrawl_name :    name of toCrawl ids Queue
        ids_crawled_name :    name of crawled ids Queue
        ids_processing_name:  name of ids crawling now Queue
        ids_problem_name :    name of ids sucked Queue
        '''
        super(WeiboSpider,self).__init__(name,*args,**kwargs)
        self.login        =   False
        self.start_urls   =   []
        self.login_url    =   self.weibo.login(self.username, self.password)

        self.redis_server =   redis.Redis(self.REDIS_HOST,self.REDIS_PORT)
        self.ids_toCrawl_name      =   settings.get('REDIS_TOCRAWL_QUEUE'   ,'user_ids_toCrawl'   )
        self.ids_crawled_name      =   settings.get('REDIS_CRAWLED_QUEUE'   ,'user_ids_crawled'   )
        self.ids_processing_name   =   settings.get('REDIS_PROCESSING_QUEUE','user_ids_processing')
        self.ids_problem_name      =   settings.get('REDIS_PROBLEM_QUEUE'   ,'user_ids_problem'   )

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
                #assert screen_name in self.username
                self.logined = True

                # load first user_id toCrawl from the Queue
                id_toCrawl  = self.redis_server.rpop(self.ids_toCrawl_name)
                if id_toCrawl:
                    # push  user_id toCrawl into the Processing Queue
                    self.redis_server.lpush(self.ids_processing_name,id_toCrawl)

                    trypage_url = QueryFactory.mainpage_query(id_toCrawl)
                    mainpage_request = Request(url=trypage_url,callback=self.mainpage_parse,meta={'user_id':id_toCrawl})
                    yield mainpage_request

            else:
                self.log('login failed: errno=%s, reason=%s' % (data.get('errno', ''), data.get('reason', '')))


    # parse mainpage_response
    def mainpage_parse(self,response):
        #inspect_response(response,self)
        if response == None:
            yield self.start_requests()
            exit(1)

        sel = Selector(response)
        login_user = {}
        login_user['toCrawl_user_id']   =  response.meta['user_id']
        login_user['toCrawl_user_nick'] =  self.get_property(response,"onick")
        login_user['login_user_id']     =  self.get_property(response,"uid")
        login_user['page_id']           =  self.get_property(response,"page_id")
        login_user['domain']            =  self.get_property(response,"domain")

        # if uid's mainpage does note exist, pass to next user in queue
        if login_user['login_user_id'] is None or login_user['page_id'] is None or login_user['domain'] is None:
            log.msg(' user toCrawl id:%s does not exist! Please try next one' % login_user['toCrawl_user_id'],level=log.DEBUG)
            next_uid  =  self.forward_crawling_redis()
            if next_uid:
                self.redis_server.lpush(self.ids_problem_name,next_uid)
                self.redis_server.lrem(self.ids_processing_name,login_user['toCrawl_user_id'],num=-1)
                trypage_url        =   QueryFactory.mainpage_query(next_uid)
                mainpage_request   =   Request(url=trypage_url,callback=self.mainpage_parse,meta={'user_id':next_uid})
                yield mainpage_request
            else:
                log.msg(' Queue is empty, task to terminate.',level=log.INFO)
        else:
            print '\n',login_user,'\n'

            login_user_profile_url = QueryFactory.info_query(page_id=login_user['page_id'], domain=login_user['domain'])
            log.msg('  user toCrawl id: %s, user login id: %s' \
                    % (login_user['toCrawl_user_id'],login_user['login_user_id']), level=log.INFO)

            request = Request(url=login_user_profile_url,callback=self.user_info_parse,meta={'login_user':login_user})
            yield request

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

        if response == None:
            yield self.start_requests()
            exit(1)

        login_user = response.meta['login_user']
        user = UserProfileItem()
        # fulfill the user Item
        user['user_id']          =  login_user['toCrawl_user_id']
        user['screen_name']      =  login_user['toCrawl_user_nick']

        user_tags_dict           =  self.get_userinfo_by_html(response)

        for property_name in user_profile_translation:
            user[user_profile_translation[property_name]] = user_tags_dict.get(property_name,'')

        if user.get('signed_time'):
            user['signed_time']  =  datetime.strptime(user['signed_time'],'%Y-%m-%d')

        print '\n\n User Profile:\n'
        for user_item in dict(user).items():
            print '\t',user_item[0],' : ',user_item[1]

        print "\n\n"
        yield user

        # url to get total number of weibos' pages
        user_weibo_page_url     =  QueryFactory.weibo_page_num_query(domain = login_user['domain'], page_id = login_user['page_id'], page_num=1 )

        # first request to get the total number of user weibos' pages
        request = Request(url=user_weibo_page_url,callback=self.weibo_pages_num,meta={'login_user':login_user})
        yield request


    # get weibo pages total number
    def weibo_pages_num(self,response):
        #inspect_response(response,self)
        if response == None:
            yield self.start_requests()
            exit(1)

        # pares the current js response
        self.weibo_parse(response)

        login_user       =  response.meta['login_user']
        # load response in json form
        html_block_soup  =  self.json_load_response(response)

        # get the tag containing the max num of page
        page_list_tag    =  html_block_soup.find('div',{'action-type':'feed_list_page_morelist'})
        MAX_PAGE_NUM     =  50
        if page_list_tag:
            total_num_pages  =  int(re.search(r'\d+',page_list_tag.a.string).group(0))
            if total_num_pages > MAX_PAGE_NUM:
                total_num_pages   =   MAX_PAGE_NUM
        else:
            total_num_pages  =  1

        # warp weibo page urls to crawl
        weibo_page_urls       =  self.wrap_weibo_pages_urls(domain=login_user['domain'], page_id=login_user['page_id'], num_page=total_num_pages )

        print '\n\n Number of user weibos pages: ',total_num_pages,'\n\n'

        # test part weibo parser
        user_weibo_page_url   =  QueryFactory.weibo_js_query(domain = login_user['domain'], page_id = login_user['page_id'], page_num=2 )[0]

        # first request to get the total number of user weibos' pages
        #request = Request(url=user_weibo_page_url,callback=self.user_weibo_parse,meta={'login_user':login_user})
        #yield request


        # send requests contained in the weibo pages urls
        for page_url in weibo_page_urls:
            yield Request(url=page_url,callback=self.weibo_parse,meta={'login_user':login_user})

        # insert id crawled into redis
        self.redis_server.lrem(self.ids_processing_name,login_user['toCrawl_user_id'],num=-1)
        self.redis_server.lpush(self.ids_crawled_name  ,login_user['toCrawl_user_id'])

        # TODO
        next_uid  =  self.forward_crawling_redis()

        if next_uid:
            trypage_url = QueryFactory.mainpage_query(next_uid)
            mainpage_request = Request(url=trypage_url,callback=self.mainpage_parse,meta={'user_id':next_uid})
            yield mainpage_request
        else:
            log.msg(' Queue is empty, task to terminate.',level=log.INFO)

    # get weibo contents
    def weibo_parse(self,response):
        #inspect_response(response,self)

        if response == None:
            yield self.start_requests()
            exit(1)

        weibo_dicts_list  =  self.get_weibo_by_html(response)
        for weibo_item_dict in weibo_dicts_list:
            yield WeiboItem(weibo_item_dict)








    '''
    ################################################################################
    Following are auxiliary tools to help previous parsers
    ################################################################################
    '''

    # pass to next uid Crawl if queue is not empty
    def forward_crawling(self):
        # request for crawling the next uid in queue
        if len(self.id_toCrawl_list):
            id_toCrawl = self.id_toCrawl_list.pop()
            return id_toCrawl
        else:
            return None

    # pass to next uid Crawl if redis-queue is not empty
    def forward_crawling_redis(self):
        # request for crawling the next uid in queue
        next_uid   =   self.redis_server.rpop(self.ids_toCrawl_name)

        if next_uid:
            self.redis_server.lpush(self.ids_processing_name,next_uid)
            return next_uid
        else:
            return None

    # load response in json form and get the value of key:'data'
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
        regex_CONFIG = re.compile(r"CONFIG\[\'"+property_name+r"\'\]=\'(.*)\'")
        # find the second script in head node which indicates properties
        # when the uid's mainpage exists
        if selector.xpath('/html/head/script/text()').re(regex_CONFIG):
            return selector.xpath('/html/head/script/text()').re(regex_CONFIG)[0]
        else:
            return None

    # wrap weibo pages url by the user_id and the total num of weibo pages
    def wrap_weibo_pages_urls(self, domain,page_id, num_page):
        weibo_urls = set()

        for page in range(num_page):
            weibo_urls=weibo_urls.union(QueryFactory.weibo_js_query( domain=domain,page_id=page_id,page_num=page+1))

        return weibo_urls

    # extract link text from popularity issues block
    # get the number contained in the link(supports_link/comments_link/retweets_link)
    def get_num_from_block(self,block_name,action_type):
        link_module   =   block_name.findAll('a',{'action-type':action_type},limit=1)
        if link_module:
            link_raw   =   [x for x in link_module[0].contents if type(x) == BeautifulSoupModule.NavigableString]
            if link_raw:
                link   =   link_raw[0].strip()
            else:
                link   =   ''
        else:
            link   =   ''
        #print ' link here :  ',link,'\n'

        regex_for_link   =   re.compile(r"^.+(?P<number_in_link>\d+).+$")
        match_result     =   regex_for_link.match(link)
        if match_result:
            number_in_link   =  int(match_result.group('number_in_link'))
        else:
            number_in_link   =  0
        return number_in_link

    # convert all contents in a Content Tag into string
    def stringfy_content_tag(self,content_tag):
        if content_tag is None:
            return ''
        else:
            content_elems    =   []
            tag_contents     =   content_tag.contents
            for elem in tag_contents:
                if type(elem) is BeautifulSoupModule.Tag:
                    content_elems.append(self.stringfy_content_tag(elem))
                else:
                    content_elems.append(elem.strip())
            return ' '.join(content_elems)

    # get user profile property value from the user infopage
    def get_userinfo_by_html(self,response):
        selector = Selector(response)
        tags_dict  =  {}

        # extract the html script block containing personal info
        basic_info_block = selector.xpath('/html/script/text()').re(r'(\{.*\"domid\"\:\"Pl_Official_LeftInfo__(\d+)\".*\})')\
                        or selector.xpath('/html/script/text()').re(r'(\{.*\"domid\"\:\"Pl_Core_LeftTag__(\d+)\".*\})')
        if basic_info_block:
            basic_info_block_html = json.loads(basic_info_block[0])['html']
            script_part_soup = BeautifulSoup(basic_info_block_html)
        else:
            script_part_soup = BeautifulSoup('')


        # decompose the user profile html block into tags like 
        #     property_name     : u"生日"
        #     property_content  : u"1990年04月19日"
        for record_line in script_part_soup.findAll('div',{"class":"pf_item clearfix"}):
            property_name      =    record_line.find('div',{"class":"label S_txt2"})
            if property_name is None:
                property_name  =    'unknown'
                continue
            property_name  =    property_name.string

            property_content_tag   =    record_line.find('div',{"class":"con"})
            property_content       =    self.stringfy_content_tag(property_content_tag)

            tags_dict[property_name] = property_content

        return tags_dict


    # get the total number of user's weibos' pages
    def get_weibo_by_html(self,response):

        login_user       =  response.meta['login_user']
        ## load response in json form
        html_block_soup  =  self.json_load_response(response)

        weibo_dicts_list =  []
        i = 0
        for weibo in html_block_soup.findAll('div',{'mid':True,'class':'WB_feed_type SW_fun S_line2 '}):
            i +=1
            weibo_id   =   weibo.get('mid')
            #print '\n\n Weibo[',str(i),'] user_id: ',login_user['toCrawl_user_id'],'\n'
            #print ' Weibo[',str(i),'] weibo_id: ',weibo_id,'\n'

            ## load weibo contents
            weibo_contents_block   =   weibo.findAll('div',{'class':'WB_text','node-type':'feed_list_content'},limit=1)
            if weibo_contents_block == None:
                weibo_contents = ''
            else:
                weibo_contents     =   weibo_contents_block[0].contents
                for index in range(len(weibo_contents)):
                    content  =  weibo_contents[index]
                    if type(content)==BeautifulSoupModule.NavigableString:
                        weibo_contents[index]  =  content.strip()
                    elif content.name!='a':
                        weibo_contents[index]  =  content.get('title','')
                    elif content.string:
                        weibo_contents[index]  =  content.string + ' '
                    else:
                        weibo_contents[index]  =  ' '
                weibo_contents    =  ''.join(weibo_contents)


            #print ' Weibo[',str(i),'] contents: ',weibo_contents,'\n'


            ## load creatTime
            weibo_time_block  =  weibo.findAll('a',{'class':'S_link2 WB_time','node-type':'feed_list_item_date'},limit=1)
            if weibo_time_block:
                weibo_creat_time  =  weibo_time_block[0].get('title')
                weibo_creat_time  =  datetime.strptime(weibo_creat_time,'%Y-%m-%d %H:%M')
            else:
                weibo_creat_time  =  ''
            #print ' Weibo[',str(i),'] creat at: ',weibo_creat_time,'\n'


            ## load sourceApp
            weibo_source_block  =  weibo.findAll('a',{'class':'S_link2','action-type':'app_source'},limit=1)
            if weibo_source_block:
                weibo_app_source  =  weibo_source_block[0].string
            else:
                weibo_app_source  =  ''
            #print ' Weibo[',str(i),'] app_source: ',weibo_app_source,'\n'


            ## load retweeted weibo if exists
            isRetweet  =  int(weibo.get('isforward','0'))
            #print ' Weibo[',str(i),'] isRetweet: ',isRetweet,'\n'

            # this time the weibo is retweet
            if isRetweet:
                weibo_retweet_block= weibo.findAll('div',{'node-type':'feed_list_forwardContent'},limit=1)
                num_supports       =   num_comments        =   num_retweets          = 0
                # case when the original weibo of current retweet exists
                if weibo_retweet_block:
                    regex_for_user_id    =   re.compile(r'id=(?P<id_number>\d+)')
                    retweetFromUser_block=   weibo_retweet_block[0].findAll('a',{'node-type':'feed_list_originNick','class':'WB_name S_func3'},limit=1)[0]

                    retweetFromWeibo     =   weibo.get('omid','')
                    retweetFromUserId    =   regex_for_user_id.match(retweetFromUser_block.get('usercard')).group('id_number')
                    retweetFromUserNick  =   retweetFromUser_block.get('nick-name')
                # case when the original weibo of current retweet is deleted
                else:
                    retweetFromWeibo   =   retweetFromUserId   =   retweetFromUserNick   = ''

            # this time the weibo is original
            else:
                retweetFromWeibo   =   retweetFromUserId   =   retweetFromUserNick   = ''

                popularity_issues_block  =   weibo.findAll('div',{'class':'WB_handle'},limit=1)[0]

                num_supports       =     self.get_num_from_block(popularity_issues_block,'fl_like')
                num_comments       =     self.get_num_from_block(popularity_issues_block,'fl_comment')
                num_retweets       =     self.get_num_from_block(popularity_issues_block,'fl_forward') 

            #print ' Weibo[',str(i),'] retweetFromUser : ',retweetFromUserNick,'   ',retweetFromUserId,'\n'
            #print ' Weibo[',str(i),'] retweetFromWeibo: ',retweetFromWeibo   ,'\n'

            #print ' Weibo[',str(i),'] num_supports    : ',num_supports   ,'\n'
            #print ' Weibo[',str(i),'] num_comments    : ',num_comments   ,'\n'
            #print ' Weibo[',str(i),'] num_retweets    : ',num_retweets   ,'\n\n'

            weibo_dict  =   {
                                'user_id'               :      login_user['toCrawl_user_id'],
                                'weibo_id'              :      weibo_id,
                                'created_time'          :      weibo_creat_time,
                                'content'               :      weibo_contents,
                                'app_source'            :      weibo_app_source,

                                'isRetweet'             :      isRetweet,
                                'retweetFromUserId'     :      retweetFromUserId,
                                'retweetFromUserNick'   :      retweetFromUserNick,
                                'retweetFromWeibo'      :      retweetFromWeibo,

                                'num_supports'          :      num_supports,
                                'num_comments'          :      num_comments,
                                'num_retweets'          :      num_retweets

                                }

            weibo_dicts_list.append(weibo_dict)

        return weibo_dicts_list

