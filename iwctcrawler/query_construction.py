#coding=utf-8

class QueryFactory:
    
    @staticmethod
    def mainpage_query(user_id):
        return "http://weibo.com/u/%s" % user_id 

    @staticmethod
    def info_query(page_id,pid):
        return "http://weibo.com/p/%s/info?from=page_%s&mod=TAB#place" % (page_id,pid)

    @staticmethod
    def weibo_query(page_id,pid):
        return "http://weibo.com/p/%s/weibo?from=page_%s&mod=TAB#place" % (page_id,pid)


