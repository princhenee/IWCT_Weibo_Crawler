#coding=utf-8
# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html

from scrapy.item import Item, Field

class UserProfileItem(Item):
    # define the fields for your item here like:
    # name = Field()

    user_id     =  Field()

    # 基本信息
    screen_name   =  Field()             #nickname
    sex           =  Field()
    description   =  Field()
    signed_time   =  Field()
    location      =  Field()
    birthday      =  Field()

    # 工作信息
    company       =  Field()

    # 教育信息
    university    =  Field()

    # 标签信息
    personal_tags =  Field()


class WeiboItem(Item):
    user_id       =  Field()
    weibo_id      =  Field()
    created_time  =  Field()
    content       =  Field()
    at_people     =  Field()
