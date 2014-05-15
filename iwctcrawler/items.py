# Define here the models for your scraped items
#
# See documentation in:
# http://doc.scrapy.org/en/latest/topics/items.html

from scrapy.item import Item, Field

class UserProfileItem(Item):
    # define the fields for your item here like:
    # name = Field()
    user_id     =  Field()
    screen_name =  Field()
    description =  Field()
    created_at  =  Field()
    location    =  Field()
    province    =  Field()
    city        =  Field()
