#coding=utf-8
# Define your item pipelines here
#
# Don't forget to add your pipeline to the ITEM_PIPELINES setting
# See: http://doc.scrapy.org/en/latest/topics/item-pipeline.html

from items import UserProfileItem,WeiboItem
from scrapy.conf import settings
from scrapy import log
from pymongo import Connection as MongodbConnection


class IwctcrawlerPipeline(object):

    def __init__(self):
        connection        =   MongodbConnection(settings['MONGODB_SERVER'],settings['MONGODB_PORT'])
        self.data_base    =   connection[settings['MONGODB_DBNAME']]

    def process_item(self, item, spider):
        if isinstance(item,UserProfileItem):
            collection_name   =   settings['MONGODB_USER_COLLECTION']
            collection        =   self.data_base[collection_name]
            key_name          =   'user_id'
            key_value         =   item.get(key_name)
            # if item already exists --- update
            if self.item_existed(collection,key_name,key_value):
                collection.update({key_name:key_value},dict(item),upsert=True)
                self.log_message(collection_name,'updated',spider)

            # if item does not exist --- insert
            else:
                collection.insert(dict(item))
                self.log_message(collection_name,'inserted',spider)

        if isinstance(item,WeiboItem):
            collection_name   =   settings['MONGODB_WEIBO_COLLECTION']
            collection        =   self.data_base[collection_name]
            key_name          =   'weibo_id'
            key_value         =   item.get(key_name)
            # if item already exists --- update
            if self.item_existed(collection,key_name,key_value):
                collection.update({key_name:key_value},dict(item),upsert=True)
                self.log_message(collection_name,'updated',spider)

            # if item does not exist --- insert
            else:
                collection.insert(dict(item))
                self.log_message(collection_name,'inserted',spider)
        return item


    def item_existed(self,collection,key_name,key_value):
        result   =   collection.find_one({key_name:key_value})
        if result is None:
            return False
        else:
            return True

    def log_message(self,collection_name,status,spider):
        log.msg("Item "+status+" into Mongodb database %s/%s" %
                (settings['MONGODB_DBNAME'],collection_name),
                level = log.DEBUG, spider=spider)


