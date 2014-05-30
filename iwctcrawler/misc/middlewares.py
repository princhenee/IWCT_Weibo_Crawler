#coding=utf-8
from scrapy import log
from proxy import PROXIES
from agents import AGENTS

import random


"""
Custom proxy provider. 
"""
class CustomHttpProxyMiddleware(object):

    def process_request(self, request, spider):
        # TODO implement complex proxy providing algorithm
        p = random.choice(PROXIES)
        try:
            request.meta['proxy'] = "http://%s" % p['ip_port']
        except Exception, e:
            log.msg("Exception %s" % e, _level=log.CRITICAL)


"""
change request header nealy every time
"""
class CustomUserAgentMiddleware(object):
    def process_request(self, request, spider):
        agent = random.choice(AGENTS)
        request.headers['User-Agent'] = agent
