#!/usr/bin/env python3
# -*- coding : utf-8 -*-
from blog2epub.crawlers.CrawlerBlogspot import *
from blog2epub.crawlers.CrawlerNrdblog import *

class Blog2Epub(object):
    """
    Main Blog2Epub class.
    """

    def __init__(self, params):
        self.crawler = self._selectCrawler(params)
        if self.crawler is None:
            raise Exception("No crawler detected")

    def _selectCrawler(self, params):
        if params['url'].find('.blogspot.') > -1:
            return CrawlerBlogspot(**params)
        if params['url'].find('nrdblog.cmosnet.eu') > -1:
            return CrawlerNrdblog(**params)
        return None

    def download(self):
        self.crawler.save()

