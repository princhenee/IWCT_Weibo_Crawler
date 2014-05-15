# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html

from scrapy.item import Item, Field

class UserProfileItem(Item):
    # define the fields for your item here like:
    # name = Field()
    user_id     =  Field()
    page_id     =  Field()             #indicate detailed page sequence 
    pid         =  Field()             #help construct url to visit
    screen_name =  Field()             #nickname
    sex         =  Field()
    description =  Field()
    created_at  =  Field()
    location    =  Field()
    province    =  Field()
    city        =  Field()

class WeiboItem(Item):
    user_id       =  Field()
    weibo_id      =  Field()
    created_time  =  Field()
    content       =  Field()
    at_people     =  Field()
