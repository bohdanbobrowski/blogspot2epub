 #!/usr/bin/env python3
# -*- coding : utf-8 -*-

import re
import json
from pocket import Pocket, PocketException
from datetime import datetime

from blog2epub.crawlers.Crawler import Dirs, Downloader
from blog2epub.crawlers.Crawler import Crawler, Article
from blog2epub.Book import Book

class CrawlerPocket(Crawler):

    POCKET_CONSUMER_KEY = '88465-089d74bb29edd7f9f1f5a210'
    POCKET_REDIRECT_URL = 'pocketapp88465:authorizationFinished'

    def __init__(self, pocket_token, pocket_username, **kwargs):
        super(CrawlerPocket, self).__init__(**kwargs)
        self.title = '{} pocket archive'.format(pocket_username)
        self.url = 'https://getpocket.com'
        self.file_name = '{}_pocket_archive'.format(pocket_username)
        self.dirs = Dirs(self.cache_folder, self.file_name)
        self.pocket_token = pocket_token
        self.pocket_username = pocket_username
        self.pocket = Pocket(self.POCKET_CONSUMER_KEY, self.pocket_token)

    def _crawl(self):
        p_data = self.pocket.get(state='all', count=10, detailType='complete', contentType='article')
        for art_id in p_data[0]['list']:
            art_in_list = p_data[0]['list'][art_id]
            if art_in_list['is_article']:
                self.article_counter += 1
                if art_in_list['resolved_title'] == '':
                    art_in_list['resolved_title'] = art_in_list['given_title']
                art = Article(art_in_list['resolved_url'], art_in_list['resolved_title'], self)
                art.date = datetime.fromtimestamp(int(art_in_list['time_added']))
                if art_in_list['has_image'] and 'top_image_url' in art_in_list:
                    art.downloader.download_image(art_in_list['top_image_url'])
                    art.images.append(art_in_list['top_image_url'])
                self.interface.print(str(len(self.articles) + 1) + '. ' + art.title)
                art.html = art.downloader.get_content(art.url)
                if self.language is None:
                    self._set_blog_language(art.html)
                art.get_tree()
                art.content = art_in_list['excerpt']
                art.comments = ''
                if self.start:
                    self.end = art.date
                else:
                    self.start = art.date
                self.articles.append(art)
        
    def save(self):
        self._crawl()
        self.book = Book(self)
        self.book.description = ''
        self.book.save()
        
